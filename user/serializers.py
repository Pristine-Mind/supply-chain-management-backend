from django.contrib.auth.models import User
from rest_framework import serializers

from producer.models import City
from user.models import Contact

from .models import UserProfile


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})
    password2 = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    location = serializers.PrimaryKeyRelatedField(queryset=City.objects.all(), required=True)
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
        phone_number = validated_data.pop("phone_number")
        latitude = validated_data.pop("latitude", None)
        longitude = validated_data.pop("longitude", None)
        location = validated_data.pop("location")

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
            has_access_to_marketplace=True,  # business users get marketplace access
        )
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
