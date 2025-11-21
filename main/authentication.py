"""
Custom authentication classes for the supply chain management application.
"""

from rest_framework.authentication import SessionAuthentication


class CSRFExemptSessionAuthentication(SessionAuthentication):
    """
    Session authentication that doesn't enforce CSRF protection.
    This is useful for API endpoints that need session authentication
    but should be accessible from cross-origin requests.
    """

    def enforce_csrf(self, request):
        """
        Override to disable CSRF enforcement for API endpoints.
        """
        return  # To not perform the csrf check previously happening
