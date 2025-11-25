"""
Authentication views for external businesses
"""

import logging
from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import ExternalBusiness, ExternalBusinessStatus
from .serializers import ExternalBusinessLoginSerializer, ExternalBusinessProfileSerializer

logger = logging.getLogger(__name__)


class ExternalBusinessLoginView(APIView):
    """
    Login endpoint for external businesses
    Creates JWT tokens for dashboard access
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """
        Login with email and password
        Returns JWT tokens and business info
        """
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response({"error": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get external business
            business = ExternalBusiness.objects.get(business_email=email, status=ExternalBusinessStatus.APPROVED)

            # Check if user account exists
            if not business.user:
                return Response({"error": "Please complete your account setup first"}, status=status.HTTP_400_BAD_REQUEST)

            # Authenticate user
            user = authenticate(username=business.user.username, password=password)
            if not user:
                return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token

            # Add business info to token
            access_token["business_id"] = business.id
            access_token["business_name"] = business.business_name
            access_token["plan"] = business.plan

            # Update last login
            business.last_login = timezone.now()
            business.save(update_fields=["last_login"])

            return Response(
                {
                    "access_token": str(access_token),
                    "refresh_token": str(refresh),
                    "business": ExternalBusinessProfileSerializer(business).data,
                    "expires_in": 3600,  # 1 hour
                }
            )

        except ExternalBusiness.DoesNotExist:
            return Response({"error": "Business not found or not approved"}, status=status.HTTP_404_NOT_FOUND)


class ExternalBusinessRefreshView(APIView):
    """
    Refresh JWT token for external businesses
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Refresh access token"""
        refresh_token = request.data.get("refresh_token")

        if not refresh_token:
            return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_token)
            access_token = refresh.access_token

            # Add business info to new token
            user = User.objects.get(id=refresh["user_id"])
            business = user.external_business

            access_token["business_id"] = business.id
            access_token["business_name"] = business.business_name
            access_token["plan"] = business.plan

            return Response({"access_token": str(access_token), "expires_in": 3600})

        except Exception as e:
            return Response({"error": "Invalid or expired refresh token"}, status=status.HTTP_401_UNAUTHORIZED)


class ExternalBusinessLogoutView(APIView):
    """
    Logout endpoint for external businesses
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Logout and blacklist refresh token
        """
        try:
            refresh_token = request.data.get("refresh_token")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            return Response({"message": "Successfully logged out"})

        except Exception:
            return Response({"message": "Logged out (token was invalid)"})


@api_view(["POST"])
@permission_classes([AllowAny])
def setup_account(request):
    """
    Setup user account for approved external business
    """
    api_key = request.data.get("api_key")
    password = request.data.get("password")
    confirm_password = request.data.get("confirm_password")

    if not api_key or not password:
        return Response({"error": "API key and password are required"}, status=status.HTTP_400_BAD_REQUEST)

    if password != confirm_password:
        return Response({"error": "Passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = ExternalBusiness.objects.get(api_key=api_key, status=ExternalBusinessStatus.APPROVED)

        if business.user:
            return Response({"error": "Account already set up"}, status=status.HTTP_400_BAD_REQUEST)

        # Create user account
        username = f"ext_business_{business.id}"
        user = User.objects.create_user(
            username=username,
            email=business.business_email,
            password=password,
            first_name=business.contact_person,
        )

        # Link user to business
        business.user = user
        business.save(update_fields=["user"])

        return Response(
            {
                "message": "Account setup successful. You can now login.",
                "username": username,
                "email": business.business_email,
            }
        )

    except ExternalBusiness.DoesNotExist:
        return Response({"error": "Invalid API key or business not approved"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([AllowAny])
def reset_password(request):
    """
    Reset password for external business
    """
    email = request.data.get("email")
    api_key = request.data.get("api_key")  # Additional verification

    if not email:
        return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = ExternalBusiness.objects.get(business_email=email, status=ExternalBusinessStatus.APPROVED)

        if api_key and business.api_key != api_key:
            return Response({"error": "Invalid API key"}, status=status.HTTP_400_BAD_REQUEST)

        # In a real implementation, send email with reset link
        # For now, we'll just return instructions

        return Response(
            {
                "message": "Password reset instructions sent to your email",
                "instructions": "Contact support with your API key to reset password",
            }
        )

    except ExternalBusiness.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def profile(request):
    """
    Get external business profile
    """
    try:
        business = request.user.external_business
        return Response(
            {
                "business": ExternalBusinessProfileSerializer(business).data,
                "user": {
                    "username": request.user.username,
                    "email": request.user.email,
                    "first_name": request.user.first_name,
                    "last_login": request.user.last_login,
                },
            }
        )

    except ExternalBusiness.DoesNotExist:
        return Response({"error": "External business not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change password for external business user
    """
    current_password = request.data.get("current_password")
    new_password = request.data.get("new_password")
    confirm_password = request.data.get("confirm_password")

    if not all([current_password, new_password, confirm_password]):
        return Response({"error": "All password fields are required"}, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_password:
        return Response({"error": "New passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)

    # Check current password
    if not request.user.check_password(current_password):
        return Response({"error": "Current password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

    # Change password
    request.user.set_password(new_password)
    request.user.save()

    return Response({"message": "Password changed successfully"})
