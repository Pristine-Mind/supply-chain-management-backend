import hashlib
import hmac
import json
import time

from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from ..models import APIUsageLog, ExternalBusiness
from ..utils import log_api_usage


class ExternalAPIUser:
    """
    Custom user-like object for external API authentication
    """

    def __init__(self, external_business):
        self.external_business = external_business
        self.id = None
        self.pk = None
        self.username = f"external_{external_business.business_name}"
        self.email = external_business.business_email
        self.is_authenticated = True
        self.is_active = True
        self.is_staff = False
        self.is_superuser = False

    def __str__(self):
        return f"ExternalAPIUser({self.external_business.business_name})"

    def has_perm(self, perm, obj=None):
        return False

    def has_perms(self, perm_list, obj=None):
        return False

    def has_module_perms(self, package_name):
        return False


class ExternalAPIAuthentication(BaseAuthentication):
    """
    Custom authentication for external API requests
    """

    def authenticate(self, request):
        api_key = request.META.get("HTTP_X_API_KEY")
        if not api_key:
            return None

        try:
            external_business = ExternalBusiness.objects.get(api_key=api_key, status="approved")

            # Set external_business on request for permission checks
            request.external_business = external_business

            # Return custom authenticated user object
            user = ExternalAPIUser(external_business)
            return (user, None)

        except ExternalBusiness.DoesNotExist:
            raise AuthenticationFailed("Invalid API key")


class ExternalAPIMiddleware(MiddlewareMixin):
    """
    Middleware for handling external API requests
    Handles authentication, rate limiting, and logging
    """

    def process_request(self, request):
        # Check if this is an external API request
        api_key = request.META.get("HTTP_X_API_KEY")
        if not api_key or not request.path.startswith("/api/external/"):
            return None

        try:
            # Get external business
            external_business = ExternalBusiness.objects.get(api_key=api_key, status="approved")

            # Set external business on request
            request.external_business = external_business

            # Record start time for response time calculation
            request.start_time = time.time()

        except ExternalBusiness.DoesNotExist:
            return JsonResponse({"error": "Invalid API key"}, status=401)

        return None

    def process_response(self, request, response):
        # Log API usage if this was an external API request
        if hasattr(request, "external_business") and hasattr(request, "start_time"):
            try:
                response_time = time.time() - request.start_time

                # Log the API usage
                log_api_usage(
                    external_business=request.external_business,
                    request=request,
                    response=response,
                    response_time=response_time,
                )
            except Exception as e:
                # Don't let logging errors affect the response
                pass

        return response


class WebhookValidationMiddleware:
    """
    Middleware to validate webhook signatures
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Validate webhook signature if this is a webhook request
        if request.path.startswith("/webhooks/external/"):
            if not self.validate_webhook_signature(request):
                return JsonResponse({"error": "Invalid webhook signature"}, status=401)

        response = self.get_response(request)
        return response

    def validate_webhook_signature(self, request):
        """
        Validate HMAC signature for webhook requests
        """
        signature = request.META.get("HTTP_X_WEBHOOK_SIGNATURE")
        if not signature:
            return False

        # Get webhook secret from request headers or business lookup
        webhook_secret = request.META.get("HTTP_X_WEBHOOK_SECRET")
        if not webhook_secret:
            return False

        try:
            # Calculate expected signature
            expected_signature = hmac.new(webhook_secret.encode("utf-8"), request.body, hashlib.sha256).hexdigest()

            # Compare signatures
            return hmac.compare_digest(signature, f"sha256={expected_signature}")
        except Exception:
            return False
