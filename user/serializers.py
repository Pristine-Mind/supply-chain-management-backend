from rest_framework import serializers
from .models import UserProfile
from django.contrib.auth.models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'first_name', 'last_name', 'phone_number']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        phone_number = validated_data.pop('phone_number')
        user = User.objects.create(
            username=validated_data['username'],
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            is_active=True
        )
        user.set_password(validated_data['password'])
        user.save()
        # Create UserProfile instance
        UserProfile.objects.create(
            user=user,
            phone_number=phone_number
        )
        return user
