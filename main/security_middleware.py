import logging
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Middleware to add security headers to all responses.
    """

    def process_response(self, request, response):
        """Add security headers to response"""

        # HTTPS Security Headers
        if not settings.DEBUG:
            response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
            response["X-Content-Type-Options"] = "nosniff"
            response["X-Frame-Options"] = "DENY"
            response["X-XSS-Protection"] = "1; mode=block"
            response["Referrer-Policy"] = "strict-origin-when-cross-origin"

            # Content Security Policy
            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' https://khalti.com https://dev.khalti.com; "
                "frame-ancestors 'none';"
            )

        # API Security Headers
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"

        return response


class APIKeyValidationMiddleware(MiddlewareMixin):
    """
    Middleware to validate API keys for sensitive endpoints.
    """

    # Endpoints that require API key validation
    PROTECTED_ENDPOINTS = [
        "/admin/",
        "/api/v1/stats-dashboard/",
        "/api/export/",
    ]

    def process_request(self, request):
        """Validate API key for protected endpoints"""

        # Check if this is a protected endpoint
        if any(request.path.startswith(endpoint) for endpoint in self.PROTECTED_ENDPOINTS):
            api_key = request.META.get("HTTP_X_API_KEY")

            if not api_key:
                return JsonResponse({"error": "API key required for this endpoint", "code": "API_KEY_MISSING"}, status=401)

            # Validate API key (you can implement key storage in database/cache)
            valid_keys = getattr(settings, "VALID_API_KEYS", [])
            if api_key not in valid_keys:
                logger.warning(f"Invalid API key attempt from {self.get_client_ip(request)}: {api_key}")
                return JsonResponse({"error": "Invalid API key", "code": "API_KEY_INVALID"}, status=401)

        return None

    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class FileUploadSecurityMiddleware(MiddlewareMixin):
    """
    Middleware to validate file uploads for security.
    """

    # Allowed file extensions
    ALLOWED_EXTENSIONS = {
        "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".avif"],
        "documents": [".pdf", ".doc", ".docx", ".txt"],
        "data": [".csv", ".xlsx", ".xls"],
    }

    # Maximum file size (in bytes)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    def process_request(self, request):
        """Validate file uploads"""

        if request.method in ["POST", "PUT", "PATCH"] and request.FILES:
            for field_name, uploaded_file in request.FILES.items():
                # Check file size
                if uploaded_file.size > self.MAX_FILE_SIZE:
                    return JsonResponse(
                        {
                            "error": f"File {uploaded_file.name} is too large. Maximum size is 10MB.",
                            "code": "FILE_TOO_LARGE",
                        },
                        status=400,
                    )

                # Check file extension
                file_extension = self.get_file_extension(uploaded_file.name).lower()
                if not self.is_allowed_extension(file_extension):
                    return JsonResponse(
                        {"error": f"File type {file_extension} is not allowed.", "code": "FILE_TYPE_NOT_ALLOWED"}, status=400
                    )

                # Check for malicious content (basic check)
                if self.is_potentially_malicious(uploaded_file):
                    logger.warning(f"Potentially malicious file upload attempt: {uploaded_file.name}")
                    return JsonResponse(
                        {"error": "File contains potentially malicious content.", "code": "MALICIOUS_FILE_DETECTED"},
                        status=400,
                    )

        return None

    def get_file_extension(self, filename):
        """Extract file extension from filename"""
        return "." + filename.split(".")[-1] if "." in filename else ""

    def is_allowed_extension(self, extension):
        """Check if file extension is allowed"""
        all_allowed = []
        for category, extensions in self.ALLOWED_EXTENSIONS.items():
            all_allowed.extend(extensions)
        return extension in all_allowed

    def is_potentially_malicious(self, uploaded_file):
        """Basic check for potentially malicious files"""
        # Check for executable file signatures
        malicious_signatures = [
            b"MZ",  # Windows executable
            b"\x7fELF",  # Linux executable
            b"<script",  # Potential script injection
            b"<?php",  # PHP script
        ]

        # Read first 1024 bytes to check for malicious signatures
        chunk = uploaded_file.read(1024)
        uploaded_file.seek(0)  # Reset file pointer

        for signature in malicious_signatures:
            if signature in chunk:
                return True

        return False


class DataSanitizationMiddleware(MiddlewareMixin):
    """
    Middleware to sanitize input data for XSS and injection attacks.
    """

    def process_request(self, request):
        """Sanitize request data"""

        if request.method in ["POST", "PUT", "PATCH"]:
            # Sanitize JSON data
            if hasattr(request, "data") and request.data:
                request._body = self.sanitize_data(request.data)

        return None

    def sanitize_data(self, data):
        """Sanitize input data recursively"""
        if isinstance(data, dict):
            return {key: self.sanitize_data(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self.sanitize_data(item) for item in data]
        elif isinstance(data, str):
            return self.sanitize_string(data)
        else:
            return data

    def sanitize_string(self, text):
        """Sanitize string input"""
        # Remove potentially dangerous HTML/JS
        dangerous_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"vbscript:",
            r"onload\s*=",
            r"onerror\s*=",
            r"onclick\s*=",
        ]

        for pattern in dangerous_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)

        return text.strip()


class GeoLocationSecurityMiddleware(MiddlewareMixin):
    """
    Middleware to validate and secure geolocation data.
    """

    def process_request(self, request):
        """Validate geolocation data"""

        if request.method in ["POST", "PUT", "PATCH"]:
            data = getattr(request, "data", {})

            # Check for latitude/longitude values
            lat = data.get("latitude") or data.get("lat")
            lng = data.get("longitude") or data.get("lng") or data.get("lon")

            if lat is not None or lng is not None:
                if not self.is_valid_coordinates(lat, lng):
                    return JsonResponse(
                        {"error": "Invalid geographical coordinates", "code": "INVALID_COORDINATES"}, status=400
                    )

        return None

    def is_valid_coordinates(self, lat, lng):
        """Validate latitude and longitude values"""
        try:
            lat = float(lat) if lat is not None else None
            lng = float(lng) if lng is not None else None

            if lat is not None and (lat < -90 or lat > 90):
                return False

            if lng is not None and (lng < -180 or lng > 180):
                return False

            return True
        except (ValueError, TypeError):
            return False


class DatabaseQueryProtectionMiddleware(MiddlewareMixin):
    """
    Middleware to detect and prevent SQL injection attempts.
    """

    # Common SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"(--|#|\/\*|\*\/)",
        r"(\bOR\b.*=.*\bOR\b)",
        r"(\bAND\b.*=.*\bAND\b)",
        r"(\'\s*(OR|AND)\s*\'\s*=\s*\')",
        r"(\bUNION\b.*\bSELECT\b)",
    ]

    def process_request(self, request):
        """Check for SQL injection attempts"""

        if request.method in ["POST", "PUT", "PATCH", "GET"]:
            # Check query parameters
            for key, value in request.GET.items():
                if self.contains_sql_injection(value):
                    logger.warning(f"SQL injection attempt detected in GET parameter '{key}': {value}")
                    return JsonResponse({"error": "Malicious input detected", "code": "SQL_INJECTION_DETECTED"}, status=400)

            # Check POST data
            if hasattr(request, "data"):
                if self.check_data_for_sql_injection(request.data):
                    logger.warning(f"SQL injection attempt detected in POST data from {self.get_client_ip(request)}")
                    return JsonResponse({"error": "Malicious input detected", "code": "SQL_INJECTION_DETECTED"}, status=400)

        return None

    def contains_sql_injection(self, text):
        """Check if text contains SQL injection patterns"""
        if not isinstance(text, str):
            return False

        for pattern in self.SQL_INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def check_data_for_sql_injection(self, data):
        """Recursively check data for SQL injection"""
        if isinstance(data, dict):
            return any(self.check_data_for_sql_injection(value) for value in data.values())
        elif isinstance(data, list):
            return any(self.check_data_for_sql_injection(item) for item in data)
        elif isinstance(data, str):
            return self.contains_sql_injection(data)
        else:
            return False

    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip
