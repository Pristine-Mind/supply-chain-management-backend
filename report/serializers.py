from rest_framework import serializers
from .models import WeeklyBusinessHealthDigest, CustomerRFMSegment


class WeeklyBusinessHealthDigestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklyBusinessHealthDigest
        fields = "__all__"


class CustomerRFMSegmentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.username", read_only=True)

    class Meta:
        model = CustomerRFMSegment
        fields = "__all__"
