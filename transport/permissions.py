from rest_framework import permissions


class IsTransporterOwner(permissions.BasePermission):
    """
    Custom permission to only allow transporters to access their own data.
    """

    def has_object_permission(self, request, view, obj):
        # Check if the user is the owner of the transporter profile
        if hasattr(obj, "user"):
            return obj.user == request.user
        elif hasattr(obj, "transporter"):
            return obj.transporter.user == request.user
        return False


class IsDeliveryParticipant(permissions.BasePermission):
    """
    Custom permission to only allow delivery participants (buyer, seller, transporter)
    to access delivery data.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Admin can access all
        if user.is_staff:
            return True

        # Check if user is involved in this delivery
        if hasattr(obj, "marketplace_sale"):
            sale = obj.marketplace_sale
            if sale.buyer == user or sale.seller == user:
                return True

        # Check if user is the assigned transporter
        if hasattr(obj, "transporter") and obj.transporter:
            if hasattr(user, "transporter_profile"):
                return obj.transporter == user.transporter_profile

        return False


class CanRateDelivery(permissions.BasePermission):
    """
    Custom permission to only allow buyers and sellers to rate deliveries.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Only buyers and sellers can rate
        if hasattr(obj, "marketplace_sale"):
            sale = obj.marketplace_sale
            return sale.buyer == user or sale.seller == user

        return False
