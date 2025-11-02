import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from main.manager import set_current_shop
from user.models import LoginAttempt, UserProfile

logger = logging.getLogger(__name__)


class ShopIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user and request.user.is_authenticated:
            try:
                user_profile = UserProfile.objects.filter(user=request.user).first()
                if user_profile:
                    set_current_shop(user_profile.shop_id)
                    logger.debug(f"Shop ID set to: {user_profile.shop_id}")
                else:
                    set_current_shop(None)
                    logger.debug("User profile not found, setting shop to None.")
            except Exception as e:
                set_current_shop(None)
                logger.warning(f"Exception in middleware: {e}")
        else:
            set_current_shop(None)
            logger.debug("User not authenticated, setting shop to None.")

        response = self.get_response(request)
        return response


class EnsureSessionKeyMiddleware(MiddlewareMixin):
    """
    Guarantees request.session.session_key exists by saving the session
    if needed. Add this *above* your view middleware in settings.
    """

    def process_request(self, request):
        # touch session so session_key is created
        if not request.session.session_key:
            request.session.save()


"""
Rate limiting middleware for login protection and general API rate limiting.
Implements sliding window algorithm for better rate limiting accuracy.
"""


class RateLimitMiddleware(MiddlewareMixin):
    """
    Middleware to implement sliding window rate limiting for login protection.

    Features:
    - Sliding window rate limiting by IP address
    - Configurable limits for different endpoints
    - Special protection for login endpoints
    - Cache-based sliding window implementation
    """

    # Rate limit configurations
    DEFAULT_RATE_LIMITS = {
        "/api/login/": {"requests": 5, "window": 300},  # 5 requests per 5 minutes for login
        "default": {"requests": 100, "window": 60},  # 100 requests per minute for other endpoints
    }

    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)

    def process_request(self, request):
        """
        Process incoming request for rate limiting.
        """
        # Get client IP address
        ip_address = self.get_client_ip(request)

        # Get the path to check rate limits
        path = request.path

        # Check if this is a login endpoint
        is_login_endpoint = any(login_path in path for login_path in ["/api/login/"])

        # If it's a login endpoint, check if IP is already blocked by LoginAttempt model
        if is_login_endpoint:
            if LoginAttempt.is_ip_blocked(ip_address, max_attempts=10, minutes=15):
                return JsonResponse(
                    {
                        "error": "Too many failed login attempts from this IP address. Please try again later.",
                        "retry_after": 900,  # 15 minutes in seconds
                        "blocked_until": (timezone.now() + timedelta(minutes=15)).isoformat(),
                    },
                    status=429,
                )

        # Apply sliding window rate limiting
        if self.is_rate_limited(ip_address, path):
            rate_limit_info = self.get_rate_limit_for_path(path)
            return JsonResponse(
                {
                    "error": "Rate limit exceeded. Too many requests.",
                    "retry_after": rate_limit_info["window"],
                    "limit": rate_limit_info["requests"],
                    "window": rate_limit_info["window"],
                },
                status=429,
            )

        return None

    def get_client_ip(self, request):
        """
        Get the client's IP address from the request.
        Handles X-Forwarded-For header for proxied requests.
        """
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

    def get_rate_limit_for_path(self, path):
        """
        Get rate limit configuration for a specific path.
        """
        for route, config in self.DEFAULT_RATE_LIMITS.items():
            if route != "default" and route in path:
                return config
        return self.DEFAULT_RATE_LIMITS["default"]

    def is_rate_limited(self, ip_address, path):
        """
        Check if the IP address is rate limited using sliding window algorithm.
        """
        rate_limit_config = self.get_rate_limit_for_path(path)
        max_requests = rate_limit_config["requests"]
        window_seconds = rate_limit_config["window"]

        # Create cache key for this IP and path
        cache_key = f"rate_limit:{ip_address}:{path}"

        # Get current time
        now = time.time()

        # Get existing requests from cache
        requests = cache.get(cache_key, [])

        # Remove requests outside the current window (sliding window)
        cutoff_time = now - window_seconds
        requests = [req_time for req_time in requests if req_time > cutoff_time]

        # Check if we've exceeded the limit
        if len(requests) >= max_requests:
            return True

        # Add current request timestamp
        requests.append(now)

        # Update cache with TTL equal to window size
        cache.set(cache_key, requests, timeout=window_seconds)

        return False

    def process_response(self, request, response):
        """
        Add rate limit headers to response.
        """
        ip_address = self.get_client_ip(request)
        path = request.path
        rate_limit_config = self.get_rate_limit_for_path(path)

        # Add rate limit headers
        response["X-RateLimit-Limit"] = str(rate_limit_config["requests"])
        response["X-RateLimit-Window"] = str(rate_limit_config["window"])

        # Calculate remaining requests
        cache_key = f"rate_limit:{ip_address}:{path}"
        requests = cache.get(cache_key, [])
        now = time.time()
        cutoff_time = now - rate_limit_config["window"]
        current_requests = len([req_time for req_time in requests if req_time > cutoff_time])

        remaining = max(0, rate_limit_config["requests"] - current_requests)
        response["X-RateLimit-Remaining"] = str(remaining)

        # Add reset time (when the window resets)
        if requests:
            oldest_request = min([req_time for req_time in requests if req_time > cutoff_time], default=now)
            reset_time = int(oldest_request + rate_limit_config["window"])
            response["X-RateLimit-Reset"] = str(reset_time)

        return response


class LoginProtectionMiddleware(MiddlewareMixin):
    """
    Specialized middleware for login endpoint protection.
    Works alongside RateLimitMiddleware for enhanced security.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)

    def process_response(self, request, response):
        """
        Clean up expired login attempts periodically.
        Only runs on login-related endpoints to avoid performance impact.
        """
        path = request.path
        is_login_endpoint = any(login_path in path for login_path in ["/api/login/"])

        if is_login_endpoint:
            # Periodically clean up expired attempts (run cleanup ~5% of the time)
            import random

            if random.random() < 0.05:  # 5% chance
                try:
                    LoginAttempt.clear_expired_attempts(minutes=15)
                except Exception:
                    # Silently handle any database errors during cleanup
                    pass

        return response
