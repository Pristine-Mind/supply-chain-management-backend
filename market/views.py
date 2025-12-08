import logging

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import OuterRef, QuerySet, Subquery
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status, views, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
)
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from main.enums import GlobalEnumSerializer, get_enum_values
from market.models import (
    Bid,
    ChatMessage,
    Feedback,
    Notification,
    OrderTrackingEvent,
    UserInteraction,
)
from producer.models import MarketplaceProduct, MarketplaceProductReview
from producer.serializers import MarketplaceProductReviewSerializer

from .filters import BidFilter, ChatFilter, UserBidFilter
from .forms import ShippingAddressForm
from .models import (
    Bid,
    Cart,
    CartItem,
    ChatMessage,
    Delivery,
    DeliveryInfo,
    Feedback,
    MarketplaceOrder,
    MarketplaceOrderItem,
    MarketplaceSale,
    MarketplaceUserProduct,
    Notification,
    OrderStatus,
    Payment,
    ProductView,
    ShoppableVideo,
    UserFollow,
    VideoComment,
    VideoLike,
    VideoReport,
    VideoSave,
)
from .recommendation import VideoRecommendationService
from .serializers import (
    BidSerializer,
    BidUserSerializer,
    CartItemSerializer,
    CartSerializer,
    ChatMessageSerializer,
    CreateDeliveryFromSaleSerializer,
    CreateOrderSerializer,
    DeliveryInfoSerializer,
    DeliverySerializer,
    FeedbackSerializer,
    MarketplaceOrderSerializer,
    MarketplaceSaleSerializer,
    MarketplaceUserProductSerializer,
    NotificationSerializer,
    OrderTrackingEventSerializer,
    PurchaseSerializer,
    SellerBidSerializer,
    SellerProductSerializer,
    ShoppableVideoSerializer,
    UserFollowSerializer,
    VideoCommentSerializer,
    VideoLikeSerializer,
    VideoReportSerializer,
)
from .utils import sms_service


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_purchase(request):
    """
    API view to create a purchase and generate the payment URL for either eSewa or Khalti.
    """
    serializer = PurchaseSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        purchase_data = serializer.save()

        # Return the appropriate payment URL based on the payment method
        payment_method = request.data.get("payment_method", "esewa")  # Default to eSewa if not provided

        if payment_method == "esewa":
            payment_url = purchase_data.get("payment_url")
        elif payment_method == "khalti":
            payment_url = purchase_data.get("khalti_payment_url")
        else:
            return Response({"error": "Invalid payment method selected."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"purchase": PurchaseSerializer(purchase_data["purchase"]).data, "payment_url": payment_url},
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BidViewSet(viewsets.ModelViewSet):
    serializer_class = BidSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = BidFilter

    def get_queryset(self) -> QuerySet:
        return Bid.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bid = serializer.save()
        return Response(self.get_serializer(bid).data, status=status.HTTP_201_CREATED)


class UserBidViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BidUserSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = UserBidFilter

    def get_queryset(self) -> QuerySet:
        latest_bids = Bid.objects.filter(product=OuterRef("product")).order_by("-bid_date")
        queryset = Bid.objects.filter(id=Subquery(latest_bids.values("id")[:1]), bidder=self.request.user)
        return queryset


class ChatMessageViewSet(viewsets.ModelViewSet):
    queryset = ChatMessage.objects.all()
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ChatFilter

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chat_message = serializer.save()
        return Response(self.get_serializer(chat_message).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def highest_bidder(request, product_id):
    """
    Return whether the authenticated user is the highest bidder for a given product.
    """
    try:
        product = MarketplaceProduct.objects.get(id=product_id)
    except MarketplaceProduct.DoesNotExist:
        return Response({"error": "Product not found"}, status=404)

    highest_bid = Bid.objects.filter(product=product).order_by("-max_bid_amount").first()

    if highest_bid and highest_bid.bidder == request.user:
        return Response({"is_highest_bidder": True, "max_bid_amount": highest_bid.max_bid_amount})
    else:
        return Response({"is_highest_bidder": False})


@api_view(["GET"])
def verify_payment(request):
    # Get the transaction details from the query parameters
    transaction_id = request.GET.get("oid")  # eSewa's transaction ID (your transaction ID)
    ref_id = request.GET.get("refId")  # eSewa's reference ID

    # Fetch the corresponding Payment object using the transaction ID
    payment = get_object_or_404(Payment, transaction_id=transaction_id)

    # Verify the payment with eSewa
    verification_url = "https://uat.esewa.com.np/epay/transrec"
    payload = {
        "amt": payment.amount,  # The amount from the Payment model
        "scd": "EPAYTEST",  # eSewa Merchant ID for sandbox, replace with your live merchant ID in production
        "pid": payment.transaction_id,  # Your transaction ID (same as `oid`)
        "rid": ref_id,  # eSewa's reference ID (refId)
    }

    # Send a POST request to eSewa to verify the payment
    response = requests.post(verification_url, data=payload)

    # Check if the response contains "Success"
    if "Success" in response.text:
        # If the payment is verified, update the Payment status to 'completed'
        payment.status = "completed"
        payment.save()

        # Send SMS confirmation
        sms_service.send_payment_confirmation_sms(payment)

        return redirect("payment_confirmation", payment_id=payment.id)
    else:
        # If the verification failed, update the Payment status to 'failed'
        payment.status = "failed"
        payment.save()
        return HttpResponse("Payment Verification Failed")


@csrf_exempt
def payment_confirmation(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if payment.status == "completed":
        context = {"payment": payment, "message": "Your payment was successful. Please proceed to the shipping details."}
        return render(request, "payment_confirmation.html", context)
    else:
        return HttpResponse("Payment not verified")


@csrf_exempt
def shipping_address_form(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)

    if request.method == "POST":
        form = ShippingAddressForm(request.POST)
        if form.is_valid():
            shipping_address = form.save(commit=False)
            shipping_address.payment = payment
            shipping_address.save()

            # Send order confirmation SMS
            sms_service.send_order_status_sms(
                payment, "Your order has been confirmed and shipping details received. " "We will process your order soon!"
            )

            return render(
                request,
                "shipping_address_form.html",
                {
                    "form": form,
                    "payment": payment,
                    "order_success": True,
                },
            )
    else:
        form = ShippingAddressForm()

    return render(request, "shipping_address_form.html", {"form": form, "payment": payment})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_khalti_payment(request):
    """
    API view to verify Khalti payment using the payment token.
    """
    token = request.data.get("token")
    amount = request.data.get("amount")
    transaction_id = request.data.get("transaction_id")

    if not token or not amount or not transaction_id:
        return Response({"error": "Missing token, amount, or transaction ID."}, status=status.HTTP_400_BAD_REQUEST)

    url = "https://khalti.com/api/v2/payment/verify/"
    payload = {"token": token, "amount": amount}
    headers = {"Authorization": f"Key {settings.KHALTI_SECRET_KEY}"}

    response = requests.post(url, data=payload, headers=headers)
    if response.status_code == 200:
        try:
            payment = Payment.objects.get(transaction_id=transaction_id)
            payment.status = "completed"
            payment.save()

            # Send SMS confirmation
            sms_service.send_payment_confirmation_sms(payment)

            return redirect("payment_confirmation", payment_id=payment.id)
        except Payment.DoesNotExist:
            payment.status = "failed"
            payment.save()
            return Response({"error": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        payment.status = "failed"
        payment.save()
        return Response({"error": "Payment verification failed."}, status=status.HTTP_400_BAD_REQUEST)


class MarketplaceUserProductViewSet(viewsets.ModelViewSet):
    queryset = MarketplaceUserProduct.objects.filter(is_sold=False, is_verified=True)
    serializer_class = MarketplaceUserProductSerializer
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        return Response({"message": "Update action is not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def destroy(self, request, *args, **kwargs):
        return Response({"message": "Delete action is not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)


class ProductBidsView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        bids = Bid.objects.filter(product__id=product_id).order_by("-bid_date")
        serializer = BidUserSerializer(bids, many=True)
        return Response(serializer.data)


class UserBidsForProductView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        product = get_object_or_404(MarketplaceProduct, id=product_id)
        user_bids = Bid.objects.filter(bidder=request.user, product=product).order_by("-bid_date")

        bids_data = [
            {
                "bid_amount": bid.bid_amount,
                "max_bid_amount": bid.max_bid_amount,
                "bid_date": bid.bid_date,
                "id": bid.id,
            }
            for bid in user_bids
        ]

        return Response(bids_data)


class SellerProductsView(views.APIView):
    # permission_classes = [IsAuthenticated]

    def get(self, request):
        products = MarketplaceProduct.objects.filter(product__user=request.user).distinct()
        serialized_products = []
        for product in products:
            bids = Bid.objects.filter(product=product).order_by("-bid_amount")
            serialized_product = SellerProductSerializer(product).data
            serialized_product["bids"] = SellerBidSerializer(bids, many=True).data
            serialized_products.append(serialized_product)
        return Response(serialized_products)


class NotificationListView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user).order_by("-created_at")
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MarkNotificationAsReadView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)

        if notification.is_read:
            return Response({"detail": "Notification is already marked as read."}, status=status.HTTP_400_BAD_REQUEST)

        notification.is_read = True
        notification.save()

        return Response({"detail": "Notification marked as read."}, status=status.HTTP_200_OK)


class WithdrawBidView(views.APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, bid_id):
        bid = get_object_or_404(Bid, id=bid_id, bidder=request.user)
        serializer = BidSerializer()
        try:
            serializer.delete(bid)
        except serializers.ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Bid withdrawn successfully."}, status=status.HTTP_204_NO_CONTENT)


class GlobalEnumView(views.APIView):
    """
    Provide a single endpoint to fetch enum metadata
    """

    @extend_schema(responses=GlobalEnumSerializer)
    def get(self, _):
        """
        Return a list of all enums.
        """
        return Response(get_enum_values())


@api_view(["POST"])
@permission_classes([AllowAny])
def log_interaction(request):
    """
    Logs user interaction events.
    Expected JSON payload:
    {
      "event_type": "click",
      "data": { ... }  // Arbitrary event details
    }
    """
    event_type = request.data.get("event_type")
    data = request.data.get("data", {})

    if not event_type:
        return Response({"error": "Event type is required."}, status=400)

    user = request.user if request.user.is_authenticated else None

    UserInteraction.objects.create(user=user, event_type=event_type, data=data)
    return Response({"message": "Interaction logged successfully."})


class FeedbackViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing feedback on marketplace products.
    """

    serializer_class = FeedbackSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Feedback.objects.all()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ProductFeedbackView(views.APIView):
    """
    API view to get all feedback for a specific product.
    """

    permission_classes = [AllowAny]

    def get(self, request, product_id):
        try:
            product = MarketplaceProduct.objects.get(id=product_id)
            feedbacks = Feedback.objects.filter(product=product).order_by("-created_at")
            serializer = FeedbackSerializer(feedbacks, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except MarketplaceProduct.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)


class UserFeedbackView(views.APIView):
    """
    API view to get all feedback submitted by the authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        feedbacks = Feedback.objects.filter(user=request.user).order_by("-created_at")
        serializer = FeedbackSerializer(feedbacks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CartCreateView(generics.CreateAPIView):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        cart, created = Cart.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(cart)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class UserCartView(views.APIView):
    """Return the authenticated user's cart (create if missing) with items."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CartItemCreateView(generics.CreateAPIView):
    serializer_class = CartItemSerializer

    def create(self, request, *args, **kwargs):
        cart_id = self.kwargs["cart_id"]
        cart = get_object_or_404(Cart, id=cart_id)

        product = request.data.get("product")
        existing_item = CartItem.objects.filter(cart=cart, product=product).first()

        if existing_item:
            existing_item.quantity += request.data.get("quantity", 1)
            existing_item.save()
            serializer = self.get_serializer(existing_item)
        else:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(cart=cart)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CartItemUpdateView(generics.UpdateAPIView):
    serializer_class = CartItemSerializer
    lookup_field = "id"
    lookup_url_kwarg = "item_id"

    def get_queryset(self):
        cart_id = self.kwargs["cart_id"]
        return CartItem.objects.filter(cart_id=cart_id)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


class CartItemDeleteView(generics.DestroyAPIView):
    serializer_class = CartItemSerializer
    lookup_field = "id"
    lookup_url_kwarg = "item_id"

    def get_queryset(self):
        cart_id = self.kwargs["cart_id"]
        return CartItem.objects.filter(cart_id=cart_id)


class DeliveryCreateView(generics.CreateAPIView):
    queryset = Delivery.objects.all()
    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        """
        Create a delivery. Supports creation from cart, sale, marketplace_sale, or marketplace_order.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get the delivery source for logging
        delivery_source = None
        if serializer.validated_data.get("cart"):
            delivery_source = "cart"
        elif serializer.validated_data.get("sale"):
            delivery_source = "sale"
        elif serializer.validated_data.get("marketplace_sale"):
            delivery_source = "marketplace_sale"
        elif serializer.validated_data.get("marketplace_order"):
            delivery_source = "marketplace_order"

        self.perform_create(serializer)

        response_data = serializer.data
        response_data["message"] = f"Delivery created successfully from {delivery_source}"

        return Response(response_data, status=status.HTTP_201_CREATED)


class DeliveryViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing deliveries.
    Supports deliveries from carts, sales, marketplace sales, and marketplace orders.
    """

    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["delivery_status", "city", "state"]
    search_fields = ["customer_name", "phone_number", "tracking_number", "address"]
    ordering_fields = ["created_at", "estimated_delivery_date", "actual_delivery_date"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """
        Return deliveries based on user role and permissions.
        """
        user = self.request.user
        queryset = Delivery.objects.all()

        if not user.is_staff:
            # For non-staff users, show deliveries related to their sales or orders
            queryset = queryset.filter(
                models.Q(sale__user=user)  # Deliveries from their sales
                | models.Q(marketplace_sale__seller=user)  # Deliveries from their marketplace sales
                | models.Q(marketplace_sale__buyer=user)  # Deliveries from their purchases
                | models.Q(marketplace_order__customer=user)  # Deliveries from their orders
                | models.Q(cart__user=user)  # Deliveries from their cart
            ).distinct()

        return queryset

    @action(detail=True, methods=["patch"], url_path="update-status")
    def update_delivery_status(self, request, pk=None):
        """
        Update the delivery status and related information.
        """
        delivery = self.get_object()
        new_status = request.data.get("delivery_status")

        if not new_status:
            return Response({"error": "delivery_status is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate status transition
        valid_statuses = ["pending", "assigned", "picked_up", "in_transit", "delivered", "failed", "cancelled"]
        if new_status not in valid_statuses:
            return Response(
                {"error": f"Invalid status. Valid options: {valid_statuses}"}, status=status.HTTP_400_BAD_REQUEST
            )

        old_status = delivery.delivery_status
        delivery.delivery_status = new_status

        # Update actual delivery date if status is delivered
        if new_status == "delivered" and not delivery.actual_delivery_date:
            delivery.actual_delivery_date = timezone.now()

        # Update other fields if provided
        if "delivery_person_name" in request.data:
            delivery.delivery_person_name = request.data["delivery_person_name"]
        if "delivery_person_phone" in request.data:
            delivery.delivery_person_phone = request.data["delivery_person_phone"]
        if "tracking_number" in request.data:
            delivery.tracking_number = request.data["tracking_number"]

        delivery.save()

        serializer = self.get_serializer(delivery)
        return Response(
            {"message": f"Delivery status updated from {old_status} to {new_status}", "delivery": serializer.data}
        )

    @action(detail=False, methods=["get"], url_path="by-source/(?P<source_type>[^/.]+)/(?P<source_id>[^/.]+)")
    def get_by_source(self, request, source_type=None, source_id=None):
        """
        Get deliveries by source type and ID.
        source_type can be: cart, sale, marketplace_sale, marketplace_order
        """
        valid_sources = ["cart", "sale", "marketplace_sale", "marketplace_order"]
        if source_type not in valid_sources:
            return Response(
                {"error": f"Invalid source_type. Valid options: {valid_sources}"}, status=status.HTTP_400_BAD_REQUEST
            )

        filter_kwargs = {f"{source_type}_id": source_id}
        deliveries = self.get_queryset().filter(**filter_kwargs)

        serializer = self.get_serializer(deliveries, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="create-from-sale")
    def create_from_sale(self, request):
        """
        Create a delivery directly from a sale with simplified parameters.
        Uses CreateDeliveryFromSaleSerializer for validation and automatic shop_id handling.
        """
        serializer = CreateDeliveryFromSaleSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            try:
                delivery = serializer.save()
                delivery_serializer = self.get_serializer(delivery)
                return Response(
                    {"message": "Delivery created successfully from sale", "delivery": delivery_serializer.data},
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                return Response({"error": f"Failed to create delivery: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class MarketplaceSaleViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing marketplace sales.
    """

    serializer_class = MarketplaceSaleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Return sales for the current user, either as a buyer or seller.
        Admin users can see all sales.
        """
        user = self.request.user
        queryset = MarketplaceSale.objects.all()

        if not user.is_staff:
            queryset = queryset.filter(models.Q(buyer=user) | models.Q(seller=user)).distinct()

        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.lower())

        payment_status = self.request.query_params.get("payment_status")
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status.lower())

        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(sale_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(sale_date__lte=end_date)

        return queryset.order_by("-sale_date")

    def get_serializer_context(self):
        """Add the request to the serializer context."""
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @action(detail=True, methods=["post"])
    def mark_as_paid(self, request, pk=None):
        """Mark a sale as paid."""
        sale = self.get_object()
        payment_id = request.data.get("payment_id")
        payment_method = request.data.get("payment_method", "other")

        try:
            with transaction.atomic():
                sale.mark_as_paid(payment_id=payment_id, payment_method=payment_method)
                return Response({"status": "sale marked as paid"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def mark_as_delivered(self, request, pk=None):
        """Mark a sale as delivered."""
        sale = self.get_object()

        try:
            with transaction.atomic():
                sale.mark_as_delivered()
                return Response({"status": "sale marked as delivered"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def process_refund(self, request, pk=None):
        """Process a refund for a sale."""
        sale = self.get_object()
        amount = request.data.get("amount")
        reason = request.data.get("reason", "")

        try:
            with transaction.atomic():
                sale.process_refund(amount=amount, reason=reason)
                return Response({"status": "refund processed successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def perform_destroy(self, instance):
        """Override delete to use soft delete."""
        instance.delete()


@api_view(["POST"])
def log_product_view(request, pk):
    """
    Increment the basic counter and log a ProductView.
    """
    try:
        mp = MarketplaceProduct.objects.get(pk=pk)
    except MarketplaceProduct.DoesNotExist:
        return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

    mp.view_count += 1
    mp.save(update_fields=["view_count"])

    session_key = request.session.session_key or request.session.save() or request.session.session_key
    ProductView.objects.create(
        product=mp,
        user=request.user if request.user.is_authenticated else None,
        session_key=session_key,
        ip_address=request.META.get("REMOTE_ADDR", "")[:50],
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
    )

    return Response({"message": "Product view logged successfully."}, status=status.HTTP_200_OK)


class OrderTrackingEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Updated ViewSet for order tracking events supporting both order types.
    """

    serializer_class = OrderTrackingEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get tracking events for orders belonging to the authenticated user."""
        user = self.request.user

        # For staff users, show all events
        if user.is_staff:
            qs = OrderTrackingEvent.objects.all()
        else:
            # For regular users, show events for their orders only
            user_marketplace_sales = MarketplaceSale.objects.filter(models.Q(buyer=user) | models.Q(seller=user))
            user_marketplace_orders = MarketplaceOrder.objects.filter(customer=user)

            qs = OrderTrackingEvent.objects.filter(
                models.Q(marketplace_sale__in=user_marketplace_sales)
                | models.Q(marketplace_order__in=user_marketplace_orders)
            )

        # Filter by order if specified
        marketplace_order_id = self.request.query_params.get("marketplace_order") or self.request.query_params.get(
            "marketplace_order_id"
        )
        if marketplace_order_id:
            qs = qs.filter(marketplace_order_id=marketplace_order_id)

        marketplace_sale_id = self.request.query_params.get("marketplace_sale") or self.request.query_params.get(
            "marketplace_sale_id"
        )
        if marketplace_sale_id:
            qs = qs.filter(marketplace_sale_id=marketplace_sale_id)

        return qs.order_by("-created_at").distinct()


# def get_chatbot():
#     try:
#         return ChatBot(**settings.CHATTERBOT)
#     except Exception as e:
#         print(f"Error initializing chatbot: {str(e)}")
#         return None


# @api_view(["POST"])
# @permission_classes([AllowAny])
# def chat_api(request):
#     """
#     POST { "message": "Hello" }
#     → { "reply": "Hi there!" }
#     """
#     user_msg = request.data.get("message", "").strip()
#     if not user_msg:
#         return Response({"reply": "Please say something!"})

#     bot = get_chatbot()
#     if not bot:
#         return Response({"reply": "Chat service is currently unavailable. Please try again later."})

#     try:
#         bot_reply = bot.get_response(user_msg).text
#         return Response({"reply": bot_reply})
#     except Exception as e:
#         return Response({"reply": "I'm having trouble understanding. Could you rephrase that?"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="List customer's marketplace orders",
    description="Get a paginated list of orders for the authenticated customer with filtering options.",
    parameters=[
        {
            "name": "status",
            "description": "Filter by order status",
            "required": False,
            "type": "string",
            "enum": [
                "pending",
                "confirmed",
                "processing",
                "shipped",
                "in_transit",
                "delivered",
                "completed",
                "cancelled",
                "failed",
            ],
        },
        {
            "name": "payment_status",
            "description": "Filter by payment status",
            "required": False,
            "type": "string",
            "enum": ["pending", "paid", "failed", "refunded", "partially_refunded"],
        },
        {
            "name": "search",
            "description": "Search in order number, product names, or notes",
            "required": False,
            "type": "string",
        },
        {
            "name": "date_from",
            "description": "Filter orders created from this date (YYYY-MM-DD)",
            "required": False,
            "type": "string",
            "format": "date",
        },
        {
            "name": "date_to",
            "description": "Filter orders created until this date (YYYY-MM-DD)",
            "required": False,
            "type": "string",
            "format": "date",
        },
        {"name": "page", "description": "Page number for pagination", "required": False, "type": "integer"},
        {"name": "limit", "description": "Number of items per page", "required": False, "type": "integer"},
    ],
    responses={200: MarketplaceOrderSerializer(many=True)},
)
def my_marketplace_orders(request):
    """Get customer's marketplace orders with filtering."""
    from rest_framework.pagination import PageNumberPagination

    # Get base queryset for the authenticated user
    queryset = (
        MarketplaceOrder.objects.filter(customer=request.user)
        .select_related("delivery", "customer")
        .prefetch_related("items__product__product", "items__product__product__images", "tracking_events")
        .filter(is_deleted=False)
    )

    # Apply filters
    status = request.query_params.get("status")
    if status and status != "all":
        queryset = queryset.filter(order_status=status)

    payment_status = request.query_params.get("payment_status")
    if payment_status and payment_status != "all":
        queryset = queryset.filter(payment_status=payment_status)

    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(
            models.Q(order_number__icontains=search)
            | models.Q(items__product__product__name__icontains=search)
            | models.Q(notes__icontains=search)
        ).distinct()

    date_from = request.query_params.get("date_from")
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)

    date_to = request.query_params.get("date_to")
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    # Order by creation date (newest first)
    queryset = queryset.order_by("-created_at")

    # Pagination
    paginator = PageNumberPagination()
    paginator.page_size = int(request.query_params.get("limit", 10))
    page = paginator.paginate_queryset(queryset, request)

    if page is not None:
        serializer = MarketplaceOrderSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = MarketplaceOrderSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="Get marketplace order details",
    description="Retrieve detailed information about a specific marketplace order.",
    responses={200: MarketplaceOrderSerializer},
)
def marketplace_order_detail(request, pk):
    """Get marketplace order details."""
    try:
        order = (
            MarketplaceOrder.objects.select_related("delivery", "customer")
            .prefetch_related("items__product__product", "items__product__product__images", "tracking_events")
            .get(pk=pk, customer=request.user, is_deleted=False)
        )

        serializer = MarketplaceOrderSerializer(order)
        return Response(serializer.data)
    except MarketplaceOrder.DoesNotExist:
        return Response(
            {"error": "Order not found or you don't have permission to view it."}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="Cancel marketplace order",
    description="Cancel a pending or confirmed marketplace order.",
    request={
        "application/json": {
            "type": "object",
            "properties": {"cancellation_reason": {"type": "string", "description": "Reason for cancellation"}},
        }
    },
    responses={200: MarketplaceOrderSerializer},
)
def cancel_marketplace_order(request, pk):
    """Cancel a marketplace order."""
    try:
        order = MarketplaceOrder.objects.get(pk=pk, customer=request.user, is_deleted=False)

        if not order.can_cancel:
            return Response({"error": "This order cannot be cancelled."}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get("cancellation_reason", "")
        order.cancel_order(reason)

        serializer = MarketplaceOrderSerializer(order)
        return Response(serializer.data)
    except MarketplaceOrder.DoesNotExist:
        return Response(
            {"error": "Order not found or you don't have permission to cancel it."}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="Reorder marketplace order items",
    description="Create a reorder request for items from this marketplace order.",
    responses={
        200: {
            "description": "Success message with instructions",
            "content": {
                "application/json": {
                    "type": "object",
                    "properties": {"success": {"type": "boolean"}, "message": {"type": "string"}},
                }
            },
        }
    },
)
def reorder_marketplace_order(request, pk):
    """Reorder items from a marketplace order."""
    try:
        order = MarketplaceOrder.objects.prefetch_related("items").get(pk=pk, customer=request.user, is_deleted=False)

        # For now, return a success message instructing user to add items manually
        # In the future, this could automatically add items to cart
        return Response(
            {
                "success": True,
                "message": f"Please add the {order.items.count()} items from this order to your cart manually from the marketplace.",
            }
        )
    except MarketplaceOrder.DoesNotExist:
        return Response(
            {"error": "Order not found or you don't have permission to reorder it."}, status=status.HTTP_404_NOT_FOUND
        )


# New Views for Marketplace Orders
class MarketplaceOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for marketplace orders - supports listing and retrieving orders.
    """

    serializer_class = MarketplaceOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get orders for the authenticated user."""
        return (
            MarketplaceOrder.objects.filter(customer=self.request.user)
            .select_related("delivery", "customer")
            .prefetch_related("items__product__product", "items__product__product__images", "tracking_events")
            .filter(is_deleted=False)
        )

    @extend_schema(
        summary="List customer's orders",
        description="Get a paginated list of orders for the authenticated customer with filtering options.",
        parameters=[
            {
                "name": "status",
                "description": "Filter by order status",
                "required": False,
                "type": "string",
                "enum": [
                    "pending",
                    "confirmed",
                    "processing",
                    "shipped",
                    "in_transit",
                    "delivered",
                    "completed",
                    "cancelled",
                    "failed",
                ],
            },
            {
                "name": "payment_status",
                "description": "Filter by payment status",
                "required": False,
                "type": "string",
                "enum": ["pending", "paid", "failed", "refunded", "partially_refunded"],
            },
            {
                "name": "search",
                "description": "Search in order number, product names, or notes",
                "required": False,
                "type": "string",
            },
            {
                "name": "date_from",
                "description": "Filter orders created from this date (YYYY-MM-DD)",
                "required": False,
                "type": "string",
                "format": "date",
            },
            {
                "name": "date_to",
                "description": "Filter orders created until this date (YYYY-MM-DD)",
                "required": False,
                "type": "string",
                "format": "date",
            },
        ],
    )
    def list(self, request, *args, **kwargs):
        """List orders with filtering."""
        queryset = self.get_queryset()

        # Apply filters
        status = request.query_params.get("status")
        if status and status != "all":
            queryset = queryset.filter(order_status=status)

        payment_status = request.query_params.get("payment_status")
        if payment_status and payment_status != "all":
            queryset = queryset.filter(payment_status=payment_status)

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(order_number__icontains=search)
                | models.Q(items__product__product__name__icontains=search)
                | models.Q(notes__icontains=search)
            ).distinct()

        date_from = request.query_params.get("date_from")
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(summary="Get order details", description="Retrieve detailed information about a specific order.")
    def retrieve(self, request, *args, **kwargs):
        """Get order details."""
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @extend_schema(
        summary="Cancel order",
        description="Cancel a pending or confirmed order.",
        request={
            "application/json": {
                "type": "object",
                "properties": {"cancellation_reason": {"type": "string", "description": "Reason for cancellation"}},
            }
        },
    )
    def cancel(self, request, pk=None):
        """Cancel an order."""
        order = self.get_object()

        if not order.can_cancel:
            return Response({"error": "This order cannot be cancelled."}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get("cancellation_reason", "")
        try:
            order.cancel_order(reason)
            serializer = self.get_serializer(order)
            return Response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    @extend_schema(
        summary="Search order by order number",
        description="Find an order by its order number for tracking purposes.",
        parameters=[
            {
                "name": "order_number",
                "description": "The order number to search for",
                "required": True,
                "type": "string",
                "in": "query",
            }
        ],
        responses={
            200: MarketplaceOrderSerializer,
            404: {"description": "Order not found"},
        },
    )
    def search_by_order_number(self, request):
        """Search for an order by order number."""
        order_number = request.query_params.get("order_number")

        if not order_number:
            return Response({"error": "order_number parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = (
                MarketplaceOrder.objects.filter(customer=request.user, order_number=order_number, is_deleted=False)
                .select_related("delivery", "customer")
                .prefetch_related("items__product__product", "items__product__product__images", "tracking_events")
                .get()
            )

            serializer = self.get_serializer(order)
            return Response(serializer.data)

        except MarketplaceOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=["post"])
    @extend_schema(
        summary="Update order status",
        description="Update order status (for sellers/admin only).",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "order_status": {
                        "type": "string",
                        "description": "New order status",
                        "enum": ["confirmed", "processing", "shipped", "in_transit", "delivered", "completed"],
                    },
                    "message": {"type": "string", "description": "Status update message"},
                },
                "required": ["order_status"],
            }
        },
    )
    def update_status(self, request, pk=None):
        """Update order status (for sellers/admin)."""
        order = self.get_object()
        new_status = request.data.get("order_status")
        message = request.data.get("message", "")

        # Check permissions - only sellers of items in the order or admin can update
        user = request.user
        is_seller = order.items.filter(product__product__user=user).exists()
        is_admin = user.is_staff or user.is_superuser

        if not (is_seller or is_admin):
            return Response(
                {"error": "Permission denied. Only sellers or admin can update order status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate status transition
        if new_status not in [choice[0] for choice in OrderStatus.choices]:
            return Response({"error": "Invalid order status"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Update order status
            old_status = order.order_status
            order.order_status = new_status

            # Special handling for delivered status
            if new_status == OrderStatus.DELIVERED:
                order.delivered_at = timezone.now()

            order.save()

            # Create tracking event
            OrderTrackingEvent.objects.create(
                marketplace_order=order,
                status=new_status,
                message=message or f"Order status updated to {order.get_order_status_display()}",
                metadata={
                    "updated_by": user.username,
                    "previous_status": old_status,
                    "is_seller_update": is_seller,
                    "is_admin_update": is_admin,
                },
            )

            # Send notifications to customer and sellers
            from .models import Notification
            from .utils import notify_event

            try:
                # Notify customer
                status_display = order.get_order_status_display()
                customer_msg = f"📦 Your order #{order.order_number} status updated to: {status_display}"

                notify_event(
                    user=order.customer,
                    notif_type=Notification.Type.ORDER,
                    message=customer_msg,
                    via_in_app=True,
                    via_email=True,
                    email_addr=order.customer.email,
                    email_tpl="order_status_update.html",
                    email_ctx={"order": order, "old_status": old_status, "new_status": new_status},
                    via_sms=False,
                )

                # Notify sellers (except the one who updated)
                sellers = set()
                for item in order.items.all():
                    if hasattr(item.product, "product") and hasattr(item.product.product, "user"):
                        seller_user = item.product.product.user
                        if seller_user != user:  # Don't notify the seller who made the update
                            sellers.add(seller_user)

                for seller in sellers:
                    seller_msg = f"📦 Order #{order.order_number} status updated to: {status_display}"
                    notify_event(
                        user=seller,
                        notif_type=Notification.Type.ORDER,
                        message=seller_msg,
                        via_in_app=True,
                        via_email=True,
                        email_addr=seller.email,
                        email_tpl="seller_order_status_update.html",
                        email_ctx={"order": order, "old_status": old_status, "new_status": new_status},
                        via_sms=False,
                    )

            except Exception as e:
                logger.error(f"Error sending status update notifications: {str(e)}")

            serializer = self.get_serializer(order)
            return Response(
                {
                    "success": True,
                    "message": f"Order status updated to {order.get_order_status_display()}",
                    "order": serializer.data,
                }
            )

        except Exception as e:
            return Response({"error": f"Failed to update order status: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    @extend_schema(
        summary="Reorder items",
        description="Create a new order with the same items as this order.",
        responses={
            200: {
                "description": "Success message with instructions",
                "content": {
                    "application/json": {
                        "type": "object",
                        "properties": {"success": {"type": "boolean"}, "message": {"type": "string"}},
                    }
                },
            }
        },
    )
    def reorder(self, request, pk=None):
        """Reorder items from this order."""
        order = self.get_object()

        # For now, return a success message instructing user to add items manually
        # In the future, this could automatically add items to cart
        return Response(
            {
                "success": True,
                "message": f"Please add the {order.items.count()} items from this order to your cart manually from the marketplace.",
            }
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="Create order from cart",
    description="Create a new marketplace order from cart items.",
    request=CreateOrderSerializer,
    responses={201: MarketplaceOrderSerializer},
)
def create_order(request):
    """Create a new order from cart items."""
    serializer = CreateOrderSerializer(data=request.data, context={"request": request})

    if serializer.is_valid():
        try:
            order = serializer.save()
            response_serializer = MarketplaceOrderSerializer(order)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": f"Failed to create order: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MarketplaceProductReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet for MarketplaceProduct reviews.
    Allows authenticated users to create, read, update, and delete their own reviews.
    """

    serializer_class = MarketplaceProductReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter reviews based on the product parameter."""
        product_id = self.request.query_params.get("product_id")
        if product_id:
            return MarketplaceProductReview.objects.filter(product_id=product_id)
        return MarketplaceProductReview.objects.all()

    def perform_create(self, serializer):
        """Assign the authenticated user to the review."""
        serializer.save(user=self.request.user)

    def get_permissions(self):
        """Allow read access to all, but require authentication for write operations."""
        if self.action in ["list", "retrieve"]:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_object(self):
        """Ensure users can only access their own reviews for update/delete operations."""
        obj = super().get_object()

        # For update/delete operations, ensure user owns the review
        if self.action in ["update", "partial_update", "destroy"]:
            if obj.user != self.request.user:
                from rest_framework.exceptions import PermissionDenied

                raise PermissionDenied("You can only modify your own reviews.")

        return obj

    @action(detail=False, methods=["get"], url_path="my-reviews")
    def my_reviews(self, request):
        """Get all reviews created by the authenticated user."""
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        reviews = MarketplaceProductReview.objects.filter(user=request.user)
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="product/(?P<product_id>[^/.]+)")
    def product_reviews(self, request, product_id=None):
        """Get all reviews for a specific product."""
        try:
            product = MarketplaceProduct.objects.get(id=product_id)
        except MarketplaceProduct.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        reviews = MarketplaceProductReview.objects.filter(product=product)
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)


class ShoppableVideoViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Shoppable Videos (TikTok-style).
    """

    queryset = ShoppableVideo.objects.all().order_by("-created_at")
    serializer_class = ShoppableVideoSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ["list", "retrieve", "view"]:
            return [AllowAny()]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        """
        Get a personalized feed of videos using the recommendation engine.
        """
        user = request.user if request.user.is_authenticated else None

        # Get recommended videos
        service = VideoRecommendationService()
        videos = service.generate_feed(user, feed_size=10)

        # Serialize and return
        serializer = self.get_serializer(videos, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def like(self, request, pk=None):
        video = self.get_object()
        user = request.user

        like, created = VideoLike.objects.get_or_create(user=user, video=video)

        if not created:
            # If already liked, unlike it
            like.delete()
            video.likes_count = models.F("likes_count") - 1
            liked = False
        else:
            video.likes_count = models.F("likes_count") + 1
            liked = True

        video.save()
        video.refresh_from_db()

        return Response({"status": "success", "liked": liked, "likes_count": video.likes_count})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def save_video(self, request, pk=None):
        """
        Save or unsave a video.
        """
        video = self.get_object()
        user = request.user

        saved_video, created = VideoSave.objects.get_or_create(user=user, video=video)

        if not created:
            # If already saved, unsave it
            saved_video.delete()
            saved = False
        else:
            saved = True

        return Response({"status": "success", "saved": saved})

    @action(detail=True, methods=["post"], permission_classes=[AllowAny])
    def share(self, request, pk=None):
        """
        Track video shares.
        """
        video = self.get_object()
        video.shares_count = models.F("shares_count") + 1
        video.save()
        video.refresh_from_db()

        return Response({"status": "success", "shares_count": video.shares_count})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def add_to_cart(self, request, pk=None):
        """
        Directly add the video's product (or an additional product) to the user's cart.
        """
        video = self.get_object()
        user = request.user

        # Determine which product to add
        product_id = request.data.get("product_id")
        if product_id:
            # Verify the product is associated with the video
            if int(product_id) == video.product.id:
                product = video.product
            elif video.additional_products.filter(id=product_id).exists():
                product = video.additional_products.get(id=product_id)
            else:
                return Response({"error": "Product not found in this video"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Default to the main product
            product = video.product

        quantity = int(request.data.get("quantity", 1))
        if quantity < 1:
            return Response({"error": "Quantity must be at least 1"}, status=status.HTTP_400_BAD_REQUEST)

        # Get or create cart
        cart, _ = Cart.objects.get_or_create(user=user)

        # Add to cart logic (similar to CartItemCreateView)
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": quantity})

        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        # Log interaction
        UserInteraction.objects.create(
            user=user,
            event_type="add_to_cart_from_video",
            data={"video_id": video.id, "product_id": product.id, "quantity": quantity},
        )

        return Response(
            {"status": "success", "message": f"Added {product.product.name} to cart", "cart_item_count": cart.items.count()}
        )

    @action(detail=True, methods=["post"], permission_classes=[AllowAny])
    def view(self, request, pk=None):
        """
        Increment the view count for a video.
        """
        video = self.get_object()
        video.views_count = models.F("views_count") + 1
        video.save()
        video.refresh_from_db()
        return Response({"status": "success", "views_count": video.views_count})


class VideoCommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Video Comments.
    """

    queryset = VideoComment.objects.all().order_by("-created_at")
    serializer_class = VideoCommentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        video_id = self.request.query_params.get("video_id")
        if video_id:
            queryset = queryset.filter(video_id=video_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class VideoReportViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Video Reports.
    """

    queryset = VideoReport.objects.all().order_by("-created_at")
    serializer_class = VideoReportSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)


class UserFollowViewSet(viewsets.ModelViewSet):
    """
    ViewSet for User Follows.
    """

    queryset = UserFollow.objects.all().order_by("-created_at")
    serializer_class = UserFollowSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        user_id = self.request.query_params.get("user_id")
        if user_id:
            # Return followers of a specific user
            queryset = queryset.filter(following_id=user_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(follower=self.request.user)

    @action(detail=False, methods=["post"])
    def toggle_follow(self, request):
        """
        Toggle follow status for a user.
        """
        following_id = request.data.get("following_id")
        if not following_id:
            return Response({"error": "following_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        following_user = get_object_or_404(User, id=following_id)

        if following_user == request.user:
            return Response({"error": "You cannot follow yourself"}, status=status.HTTP_400_BAD_REQUEST)

        follow, created = UserFollow.objects.get_or_create(follower=request.user, following=following_user)

        if not created:
            follow.delete()
            return Response({"status": "unfollowed"})

        return Response({"status": "followed"})
