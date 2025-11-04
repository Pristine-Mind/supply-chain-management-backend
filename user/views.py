from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from transport.serializers import (
    TransporterCreateSerializer,
    TransporterSerializer,
)

from .models import Contact, PhoneOTP, UserProfile
from .serializers import (
    BusinessRegisterSerializer,
    ChangePasswordSerializer,
    ContactSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    PhoneLoginSerializer,
    PhoneNumberSerializer,
    RegisterSerializer,
    TransporterRegistrationRequestSerializer,
    UpdateNotificationPreferencesSerializer,
    UploadProfilePictureSerializer,
    UserProfileDetailSerializer,
    VerifyOTPSerializer,
)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "message": "User Created Successfully. Now perform Login to get your token",
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_exempt, name="dispatch")
class LoginAPIView(APIView):
    @extend_schema(request=LoginSerializer, responses=LoginResponseSerializer)
    @permission_classes([AllowAny])
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        # Get client IP address
        ip_address = self.get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        # Import here to avoid circular import
        from .models import LoginAttempt

        # Check if user is currently locked out
        if username and LoginAttempt.is_user_locked(username, max_attempts=3, minutes=15):
            remaining_time = LoginAttempt.get_lockout_time_remaining(username, minutes=15)
            return Response(
                {
                    "error": "Account temporarily locked due to too many failed login attempts.",
                    "retry_after": remaining_time,
                    "locked_until": (timezone.now() + timedelta(seconds=remaining_time)).isoformat(),
                },
                status=status.HTTP_423_LOCKED,
            )

        # Check if IP is blocked
        if LoginAttempt.is_ip_blocked(ip_address, max_attempts=10, minutes=15):
            return Response(
                {
                    "error": "Too many failed login attempts from this IP address. Please try again later.",
                    "retry_after": 900,  # 15 minutes
                    "blocked_until": (timezone.now() + timedelta(minutes=15)).isoformat(),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Attempt authentication
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Successful login - create token and return user info
            token, created = Token.objects.get_or_create(user=user)

            try:
                user_profile = user.user_profile
                has_access_to_marketplace = user_profile.has_access_to_marketplace
            except UserProfile.DoesNotExist:
                has_access_to_marketplace = False

            return Response(
                {
                    "token": token.key,
                    "has_access_to_marketplace": has_access_to_marketplace,
                    "business_type": user_profile.business_type if hasattr(user_profile, "business_type") else None,
                    "shop_id": user_profile.shop_id if hasattr(user_profile, "shop_id") else None,
                    "role": user_profile.role.code if hasattr(user_profile, "role") else None,
                }
            )
        else:
            # Failed login - record the attempt
            LoginAttempt.record_failed_attempt(ip_address=ip_address, username=username, user_agent=user_agent)

            # Check how many failed attempts this makes
            failed_attempts = LoginAttempt.get_failed_attempts_for_user(username, minutes=15) if username else 0
            ip_failed_attempts = LoginAttempt.get_failed_attempts_for_ip(ip_address, minutes=15)

            # Customize error message based on attempt count
            if failed_attempts >= 3:
                remaining_time = LoginAttempt.get_lockout_time_remaining(username, minutes=15)
                return Response(
                    {
                        "error": "Account temporarily locked due to too many failed login attempts.",
                        "retry_after": remaining_time,
                        "attempts_remaining": 0,
                    },
                    status=status.HTTP_423_LOCKED,
                )
            elif failed_attempts >= 2:
                return Response(
                    {
                        "error": "Invalid credentials. Warning: Account will be locked after one more failed attempt.",
                        "attempts_remaining": 1,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            elif ip_failed_attempts >= 8:
                return Response(
                    {
                        "error": "Invalid credentials. Warning: IP address will be blocked after a few more failed attempts.",
                        "attempts_remaining": 10 - ip_failed_attempts,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            else:
                return Response(
                    {"error": "Invalid Credentials", "attempts_remaining": 3 - failed_attempts},
                    status=status.HTTP_400_BAD_REQUEST,
                )

    def get_client_ip(self, request):
        """Get the client's IP address from the request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class LogoutAPIView(APIView):
    def post(self, request):
        request.user.auth_token.delete()
        return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)


# class PretrainedChatbotAPIView(APIView):
#     def __init__(self, **kwargs):
#         super().__init__(**kwargs)
#         # Load the pre-trained DialoGPT model and tokenizer from the local directory
#         model_path = "/code/chatbot_model"  # Path where the model and tokenizer are stored
#         self.tokenizer = AutoTokenizer.from_pretrained(model_path)
#         self.model = AutoModelForCausalLM.from_pretrained(model_path)

#     def post(self, request):
#         user_message = request.data.get("message", "")
#         if not user_message:
#             return Response({"error": "No message provided"}, status=status.HTTP_400_BAD_REQUEST)

#         response_message = self.generate_response(user_message)
#         return Response({"reply": response_message}, status=status.HTTP_200_OK)

#     def generate_response(self, user_message):
#         # Encode the user's message
#         input_ids = self.tokenizer.encode(user_message + self.tokenizer.eos_token, return_tensors="pt")

#         # Generate a response using the model
#         chat_history_ids = self.model.generate(
#             input_ids,
#             max_length=1000,
#             pad_token_id=self.tokenizer.eos_token_id,
#             num_return_sequences=1,
#             temperature=0.7,  # Adding some randomness to responses
#         )

#         # Decode the model output to text
#         response = self.tokenizer.decode(chat_history_ids[:, input_ids.shape[-1] :][0], skip_special_tokens=True)
#         return response


class ContactCreateView(generics.CreateAPIView):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer


class BusinessRegisterView(APIView):
    """
    API endpoint for registering a new business user.

    POST: Creates a User and associated UserProfile with business details.
    """

    serializer_class = BusinessRegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"detail": "Business user created successfully."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RequestOTPView(APIView):
    """
    Request an OTP for phone number verification
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PhoneNumberSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone_number = serializer.validated_data["phone_number"]

        # Generate and save OTP
        phone_otp = PhoneOTP.generate_otp_for_phone(phone_number)

        # In production, you would send the OTP via SMS here
        # For now, we'll return it in the response for testing
        return Response({"message": "OTP sent successfully", "otp": phone_otp.otp})  # Remove this in production


class VerifyOTPView(APIView):
    """
    Verify an OTP for a phone number
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone_number = serializer.validated_data["phone_number"]
        otp = serializer.validated_data["otp"]

        is_valid, message = PhoneOTP.verify_otp(phone_number, otp)

        if not is_valid:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": message})


class PhoneLoginView(APIView):
    """
    Login with phone number and OTP
    """

    permission_classes = [AllowAny]

    def post(self, request):
        # Get client IP address
        ip_address = self.get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        # Import here to avoid circular import
        from .models import LoginAttempt

        # Check if IP is blocked
        if LoginAttempt.is_ip_blocked(ip_address, max_attempts=10, minutes=15):
            return Response(
                {
                    "error": "Too many failed login attempts from this IP address. Please try again later.",
                    "retry_after": 900,  # 15 minutes
                    "blocked_until": (timezone.now() + timedelta(minutes=15)).isoformat(),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = PhoneLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone_number = serializer.validated_data["phone_number"]
        otp = serializer.validated_data.get("otp")

        # Check if user is currently locked out (using phone number as identifier)
        if LoginAttempt.is_user_locked(phone_number, max_attempts=3, minutes=15):
            remaining_time = LoginAttempt.get_lockout_time_remaining(phone_number, minutes=15)
            return Response(
                {
                    "error": "Account temporarily locked due to too many failed login attempts.",
                    "retry_after": remaining_time,
                    "locked_until": (timezone.now() + timedelta(seconds=remaining_time)).isoformat(),
                },
                status=status.HTTP_423_LOCKED,
            )

        # If OTP is provided, verify it
        if otp:
            is_valid, message = PhoneOTP.verify_otp(phone_number, otp)
            if not is_valid:
                # Record failed attempt
                LoginAttempt.record_failed_attempt(
                    ip_address=ip_address, username=phone_number, user_agent=user_agent  # Use phone number as username
                )

                # Check how many failed attempts this makes
                failed_attempts = LoginAttempt.get_failed_attempts_for_user(phone_number, minutes=15)
                ip_failed_attempts = LoginAttempt.get_failed_attempts_for_ip(ip_address, minutes=15)

                # Customize error message based on attempt count
                if failed_attempts >= 3:
                    remaining_time = LoginAttempt.get_lockout_time_remaining(phone_number, minutes=15)
                    return Response(
                        {
                            "error": "Account temporarily locked due to too many failed login attempts.",
                            "retry_after": remaining_time,
                            "attempts_remaining": 0,
                        },
                        status=status.HTTP_423_LOCKED,
                    )
                elif failed_attempts >= 2:
                    return Response(
                        {
                            "error": f"{message}. Warning: Account will be locked after one more failed attempt.",
                            "attempts_remaining": 1,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        {"error": message, "attempts_remaining": 3 - failed_attempts}, status=status.HTTP_400_BAD_REQUEST
                    )

        try:
            # Get the user profile with this phone number
            user_profile = UserProfile.objects.get(phone_number=phone_number)
            user = user_profile.user

            # Get or create auth token
            token, created = Token.objects.get_or_create(user=user)

            return Response(
                {
                    "token": token.key,
                    "has_access_to_marketplace": user_profile.has_access_to_marketplace,
                    "business_type": user_profile.business_type if hasattr(user_profile, "business_type") else None,
                    "shop_id": user_profile.shop_id if hasattr(user_profile, "shop_id") else None,
                }
            )

        except UserProfile.DoesNotExist:
            # Record failed attempt for non-existent user
            LoginAttempt.record_failed_attempt(ip_address=ip_address, username=phone_number, user_agent=user_agent)
            return Response({"error": "No user found with this phone number."}, status=status.HTTP_404_NOT_FOUND)

    def get_client_ip(self, request):
        """Get the client's IP address from the request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class TransporterRegistrationAPIView(generics.CreateAPIView):
    """
    API endpoint for registering a new transporter (creates both User and Transporter)
    """

    serializer_class = TransporterRegistrationRequestSerializer

    @extend_schema(
        request=TransporterRegistrationRequestSerializer,
        responses={201: TransporterSerializer},
        description="Register a new transporter (creates both User and Transporter profile). Request body must include user and transporter fields.",
    )
    def post(self, request, *args, **kwargs):
        user_fields = [
            "username",
            "email",
            "password",
            "password2",
            "first_name",
            "last_name",
        ]
        user_data = {k: v for k, v in request.data.items() if k in user_fields}
        transporter_fields = [
            "license_number",
            "vehicle_type",
            "vehicle_number",
            "vehicle_capacity",
            "phone",
            "current_latitude",
            "current_longitude",
            "vehicle_image",
            "vehicle_documents",
        ]
        transporter_data = {k: v for k, v in request.data.items() if k in transporter_fields}

        user_serializer = RegisterSerializer(data=user_data)
        if not user_serializer.is_valid():
            return Response(user_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        user = user_serializer.save()
        print(user, "user")
        transporter_data["user"] = user.id
        serializer = TransporterCreateSerializer(data=transporter_data, context={"request": request})
        if not serializer.is_valid():
            user.delete()
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        transporter = serializer.save(user=user)
        return Response(TransporterSerializer(transporter).data, status=status.HTTP_201_CREATED)


# User Profile Management APIs


class ProfileView(APIView):
    """
    API view for user profile management
    GET: Retrieve current user profile
    PUT/PATCH: Update user profile
    """

    def get(self, request):
        """Get current user profile"""
        try:
            profile = request.user.user_profile
        except UserProfile.DoesNotExist:
            # Create profile if it doesn't exist
            profile = UserProfile.objects.create(user=request.user)

        serializer = UserProfileDetailSerializer(profile, context={"request": request})
        return Response({"success": True, "data": serializer.data})

    def put(self, request):
        """Update user profile (full update)"""
        try:
            profile = request.user.user_profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)

        serializer = UserProfileDetailSerializer(profile, data=request.data, context={"request": request}, partial=False)

        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "Profile updated successfully", "data": serializer.data})

        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        """Update user profile (partial update)"""
        try:
            profile = request.user.user_profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)

        serializer = UserProfileDetailSerializer(profile, data=request.data, context={"request": request}, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "Profile updated successfully", "data": serializer.data})

        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name="dispatch")
class ChangePasswordView(APIView):
    """API view for changing password"""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, responses={200: {"description": "Password changed successfully"}})
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data["new_password"])
            user.save()

            return Response({"success": True, "message": "Password changed successfully"})

        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class UploadProfilePictureView(APIView):
    """API view for uploading profile picture"""

    def post(self, request):
        serializer = UploadProfilePictureSerializer(data=request.data)

        if serializer.is_valid():
            try:
                profile = request.user.userprofile
            except UserProfile.DoesNotExist:
                profile = UserProfile.objects.create(user=request.user)

            # Delete old profile image if exists
            if profile.profile_image:
                profile.profile_image.delete()

            profile.profile_image = serializer.validated_data["profile_picture"]
            profile.save()

            # Return updated profile data
            profile_serializer = UserProfileDetailSerializer(profile, context={"request": request})

            return Response(
                {"success": True, "message": "Profile picture uploaded successfully", "data": profile_serializer.data}
            )

        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class UpdateNotificationPreferencesView(APIView):
    """API view for updating notification preferences"""

    def patch(self, request):
        try:
            profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)

        serializer = UpdateNotificationPreferencesSerializer(profile, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()

            # Return updated notification preferences
            return Response(
                {
                    "success": True,
                    "message": "Notification preferences updated successfully",
                    "data": {
                        "email_notifications": profile.email_notifications,
                        "sms_notifications": profile.sms_notifications,
                        "marketing_emails": profile.marketing_emails,
                        "order_updates": profile.order_updates,
                    },
                }
            )

        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class DeleteAccountView(APIView):
    """API view for account deletion"""

    def delete(self, request):
        password = request.data.get("password")

        if not password:
            return Response(
                {"success": False, "error": "Password is required for account deletion"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Verify password
        if not authenticate(username=request.user.username, password=password):
            return Response({"success": False, "error": "Invalid password"}, status=status.HTTP_400_BAD_REQUEST)

        # Delete user account (this will cascade delete profile)
        request.user.delete()

        return Response({"success": True, "message": "Account deleted successfully"})
