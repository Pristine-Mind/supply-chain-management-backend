from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Contact, UserProfile, PhoneOTP
from .serializers import (
    BusinessRegisterSerializer,
    ContactSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    RegisterSerializer,
    PhoneNumberSerializer,
    VerifyOTPSerializer,
    PhoneLoginSerializer,
)


@extend_schema_view(request=RegisterSerializer, responses=RegisterSerializer)
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
        user = authenticate(request, username=username, password=password)
        print(user, "user")
        if user is not None:
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
                }
            )
        else:
            return Response({"error": "Invalid Credentials"}, status=status.HTTP_400_BAD_REQUEST)


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
        serializer = PhoneLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone_number = serializer.validated_data["phone_number"]
        otp = serializer.validated_data.get("otp")

        # If OTP is provided, verify it
        if otp:
            is_valid, message = PhoneOTP.verify_otp(phone_number, otp)
            if not is_valid:
                return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

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
            return Response({"error": "No user found with this phone number."}, status=status.HTTP_404_NOT_FOUND)
