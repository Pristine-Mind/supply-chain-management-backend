from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers

from producer.models import City
from transport.serializers import TransporterCreateSerializer
from user.models import Contact

from .models import Role, UserProfile


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})
    password2 = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    location = serializers.PrimaryKeyRelatedField(queryset=City.objects.all(), required=False)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password2",
            "first_name",
            "last_name",
            "phone_number",
            "location",
            "latitude",
            "longitude",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        phone_number = validated_data.get("phone_number", None)
        latitude = validated_data.get("latitude", None)
        longitude = validated_data.get("longitude", None)
        location = validated_data.get("location", None)

        user = User.objects.create(
            username=validated_data["username"],
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            is_active=True,
        )
        user.set_password(validated_data["password"])
        user.save()
        # Create UserProfile instance
        UserProfile.objects.create(
            user=user,
            phone_number=phone_number,
            location=location,
            latitude=latitude,
            longitude=longitude,
        )
        return user


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = "__all__"


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True)


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    has_access_to_marketplace = serializers.BooleanField()
    error = serializers.CharField(required=False)
    role = serializers.CharField(required=False)


class BusinessRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})
    password2 = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    location = serializers.PrimaryKeyRelatedField(queryset=City.objects.all(), required=True)
    business_type = serializers.ChoiceField(choices=UserProfile.BusinessType.choices, required=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    registration_certificate = serializers.FileField(required=True)
    pan_certificate = serializers.FileField(required=True)
    profile_image = serializers.ImageField(required=False, allow_null=True)
    registered_business_name = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password2",
            "first_name",
            "last_name",
            "phone_number",
            "location",
            "business_type",
            "latitude",
            "longitude",
            "registration_certificate",
            "pan_certificate",
            "profile_image",
            "registered_business_name",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        phone_number = validated_data.pop("phone_number")
        location = validated_data.pop("location")
        business_type = validated_data.pop("business_type")
        latitude = validated_data.pop("latitude", None)
        longitude = validated_data.pop("longitude", None)
        registration_certificate = validated_data.pop("registration_certificate")
        pan_certificate = validated_data.pop("pan_certificate")
        profile_image = validated_data.pop("profile_image", None)
        registered_business_name = validated_data.pop("registered_business_name")

        user = User.objects.create(
            username=validated_data["username"],
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            is_active=True,
        )
        user.set_password(validated_data["password"])
        user.save()

        # Create UserProfile instance
        business_owner_role = Role.objects.get(code="business_owner")

        UserProfile.objects.create(
            user=user,
            phone_number=phone_number,
            location=location,
            business_type=business_type,
            registration_certificate=registration_certificate,
            pan_certificate=pan_certificate,
            profile_image=profile_image,
            registered_business_name=registered_business_name,
            latitude=latitude,
            longitude=longitude,
            has_access_to_marketplace=True,
            role=business_owner_role,
        )  # type: ignore
        return user


class PhoneNumberSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15, required=True)


class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15, required=True)
    otp = serializers.CharField(max_length=6, required=True)


class PhoneLoginSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15, required=True)
    otp = serializers.CharField(max_length=6, required=False)

    def validate_phone_number(self, value):
        if not UserProfile.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("No user found with this phone number.")
        return value


class TransporterRegistrationRequestSerializer(serializers.Serializer):
    username = RegisterSerializer().fields["username"]
    email = RegisterSerializer().fields["email"]
    password = RegisterSerializer().fields["password"]
    password2 = RegisterSerializer().fields["password2"]
    first_name = RegisterSerializer().fields["first_name"]
    last_name = RegisterSerializer().fields["last_name"]
    license_number = TransporterCreateSerializer().fields["license_number"]
    phone = TransporterCreateSerializer().fields["phone"]
    vehicle_type = TransporterCreateSerializer().fields["vehicle_type"]
    vehicle_number = TransporterCreateSerializer().fields["vehicle_number"]
    vehicle_capacity = TransporterCreateSerializer().fields["vehicle_capacity"]
    current_latitude = TransporterCreateSerializer().fields["current_latitude"]
    current_longitude = TransporterCreateSerializer().fields["current_longitude"]
    vehicle_image = TransporterCreateSerializer().fields["vehicle_image"]
    vehicle_documents = TransporterCreateSerializer().fields["vehicle_documents"]


class UserProfileDetailSerializer(serializers.ModelSerializer):
    """Serializer for UserProfile with additional user fields"""

    # User fields
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)

    # Profile picture URL
    profile_picture = serializers.SerializerMethodField()

    # Notification preferences as nested object
    notification_preferences = serializers.SerializerMethodField()

    # Phone field compatibility
    phone = serializers.CharField(source="phone_number", required=False, allow_blank=True)

    class Meta:
        model = UserProfile
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "date_joined",
            "phone",
            "phone_number",
            "profile_picture",
            "bio",
            "date_of_birth",
            "gender",
            "address",
            "city",
            "state",
            "zip_code",
            "country",
            "business_type",
            "registered_business_name",
            "notification_preferences",
        ]

    def get_profile_picture(self, obj):
        if obj.profile_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
        return None

    def get_notification_preferences(self, obj):
        return {
            "email_notifications": obj.email_notifications,
            "sms_notifications": obj.sms_notifications,
            "marketing_emails": obj.marketing_emails,
            "order_updates": obj.order_updates,
        }

    def update(self, instance, validated_data):
        # Handle user fields
        user_data = validated_data.pop("user", {})
        user = instance.user

        for attr, value in user_data.items():
            setattr(user, attr, value)
        user.save()

        # Handle notification preferences if provided
        notification_data = validated_data.pop("notification_preferences", {})
        for key, value in notification_data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)

        # Handle profile fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance


class UpdateNotificationPreferencesSerializer(serializers.ModelSerializer):
    """Serializer for updating notification preferences"""

    class Meta:
        model = UserProfile
        fields = ["email_notifications", "sms_notifications", "marketing_emails", "order_updates"]


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing password"""

    current_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)
    confirm_password = serializers.CharField()

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError("New passwords don't match")
        return data

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not authenticate(username=user.username, password=value):
            raise serializers.ValidationError("Current password is incorrect")
        return value


class UploadProfilePictureSerializer(serializers.Serializer):
    """Serializer for uploading profile picture"""

    profile_picture = serializers.ImageField()

    def validate_profile_picture(self, value):
        # Validate file size (5MB max)
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Image size should be less than 5MB")
        return value


class ShippingAddressSerializer(serializers.Serializer):
    """Serializer for shipping addresses (for future use)"""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=100)
    address_line_1 = serializers.CharField(max_length=255)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    zip_code = serializers.CharField(max_length=20)
    country = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=15, required=False, allow_blank=True)
    is_default = serializers.BooleanField(default=False)
