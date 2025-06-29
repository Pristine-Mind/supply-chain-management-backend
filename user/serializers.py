from rest_framework import serializers
from .models import UserProfile
from django.contrib.auth.models import User

from producer.models import City
from user.models import Contact


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})
    password2 = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    location = serializers.PrimaryKeyRelatedField(queryset=City.objects.all(), required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password", "password2", "first_name", "last_name", "phone_number", "location"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        phone_number = validated_data.pop("phone_number")
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
        UserProfile.objects.create(user=user, phone_number=phone_number, location=location)
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
