import time
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from ..models import ExternalBusiness, RateLimitLog


class ExternalAPIRateLimit(MiddlewareMixin):
    """
    Rate limiting middleware for external API requests
    """

    def process_request(self, request):
        # Only apply rate limiting to external API requests
        if not hasattr(request, "external_business"):
            return None

        external_business = request.external_business
        client_ip = self.get_client_ip(request)

        # Check rate limits
        if self.is_rate_limited(external_business, client_ip, request):
            # Log the rate limit violation
            RateLimitLog.objects.create(
                external_business=external_business,
                request_ip=client_ip,
                endpoint=request.path,
                request_count=1,
                time_window="minute",
                blocked=True,
            )

            return JsonResponse(
                {
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {external_business.rate_limit_per_minute}/minute",
                    "retry_after": 60,
                },
                status=429,
            )

        # Record successful request
        self.record_request(external_business, client_ip, request)

        return None

    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

    def is_rate_limited(self, external_business, client_ip, request):
        """
        Check if request should be rate limited
        Uses Redis cache for performance
        """
        now = datetime.now()

        # Create cache keys
        minute_key = f"rate_limit:{external_business.id}:{client_ip}:{now.strftime('%Y%m%d%H%M')}"
        hour_key = f"rate_limit:{external_business.id}:{client_ip}:{now.strftime('%Y%m%d%H')}"

        # Get current counts
        minute_count = cache.get(minute_key, 0)
        hour_count = cache.get(hour_key, 0)

        # Check limits
        if minute_count >= external_business.rate_limit_per_minute:
            return True

        if hour_count >= external_business.rate_limit_per_hour:
            return True

        return False

    def record_request(self, external_business, client_ip, request):
        """Record successful request in cache"""
        now = datetime.now()

        # Create cache keys
        minute_key = f"rate_limit:{external_business.id}:{client_ip}:{now.strftime('%Y%m%d%H%M')}"
        hour_key = f"rate_limit:{external_business.id}:{client_ip}:{now.strftime('%Y%m%d%H')}"

        # Increment counters
        try:
            cache.set(minute_key, cache.get(minute_key, 0) + 1, 60)  # 1 minute TTL
            cache.set(hour_key, cache.get(hour_key, 0) + 1, 3600)  # 1 hour TTL
        except Exception:
            # Fallback to database logging if cache fails
            RateLimitLog.objects.create(
                external_business=external_business,
                request_ip=client_ip,
                endpoint=request.path,
                request_count=1,
                time_window="minute",
                blocked=False,
            )


class APIQuotaMiddleware(MiddlewareMixin):
    """
    Middleware to enforce API quotas based on subscription plans
    """

    def process_request(self, request):
        if not hasattr(request, "external_business"):
            return None

        external_business = request.external_business

        # Check if business can make requests
        can_create, message = external_business.can_create_delivery()

        # Only enforce quota for delivery creation requests
        if request.method == "POST" and "deliveries" in request.path and not can_create:

            return JsonResponse(
                {
                    "error": "Quota exceeded",
                    "message": message,
                    "current_plan": external_business.plan,
                    "upgrade_required": True,
                },
                status=403,
            )

        return None


class RequestSizeMiddleware(MiddlewareMixin):
    """
    Middleware to limit request size for external APIs
    """

    MAX_REQUEST_SIZE = getattr(settings, "EXTERNAL_API_MAX_REQUEST_SIZE", 1024 * 1024)  # 1MB

    def process_request(self, request):
        if not hasattr(request, "external_business"):
            return None

        # Check request size
        content_length = int(request.META.get("CONTENT_LENGTH", 0))

        if content_length > self.MAX_REQUEST_SIZE:
            return JsonResponse(
                {
                    "error": "Request too large",
                    "message": f"Request size ({content_length} bytes) exceeds maximum allowed ({self.MAX_REQUEST_SIZE} bytes)",
                    "max_size": self.MAX_REQUEST_SIZE,
                },
                status=413,
            )

        return None


class CORSMiddleware(MiddlewareMixin):
    """
    Custom CORS middleware for external API endpoints
    """

    def process_response(self, request, response):
        if hasattr(request, "external_business"):
            # Add CORS headers for external API requests
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key, X-Requested-With"
            response["Access-Control-Max-Age"] = "86400"

        return response


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers for API responses
    """

    def process_response(self, request, response):
        if request.path.startswith("/api/external/"):
            # Add security headers
            response["X-Content-Type-Options"] = "nosniff"
            response["X-Frame-Options"] = "DENY"
            response["X-XSS-Protection"] = "1; mode=block"
            response["Referrer-Policy"] = "strict-origin-when-cross-origin"

            # Remove server information
            if "Server" in response:
                del response["Server"]

        return response
