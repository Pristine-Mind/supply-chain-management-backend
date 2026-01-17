import logging
import random
from decimal import Decimal

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import models, transaction
from django.db.models import (
    Avg,
    Case,
    Count,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page, never_cache
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status, views, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import (
    AllowAny,
    IsAdminUser,
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
from market.utils import notify_event
from producer.models import MarketplaceProduct, MarketplaceProductReview
from producer.serializers import (
    MarketplaceProductReviewSerializer,
    MarketplaceProductSerializer,
)

from .filters import BidFilter, ChatFilter, UserBidFilter
from .forms import ShippingAddressForm
from .locks import lock_manager, view_manager
from .models import (
    AffiliateClick,
    Bid,
    Cart,
    CartItem,
    ChatMessage,
    Coupon,
    Delivery,
    DeliveryInfo,
    Feedback,
    MarketplaceOrder,
    MarketplaceOrderItem,
    MarketplaceSale,
    MarketplaceUserProduct,
    Negotiation,
    NegotiationHistory,
    Notification,
    OrderStatus,
    Payment,
    ProductChatMessage,
    ProductTag,
    ProductView,
    SellerChatMessage,
    ShoppableVideo,
    ShoppableVideoCategory,
    ShoppableVideoItem,
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
    CouponSerializer,
    CreateDeliveryFromSaleSerializer,
    CreateOrderSerializer,
    DeliverySerializer,
    FeedbackSerializer,
    MarketplaceOrderSerializer,
    MarketplaceSaleSerializer,
    MarketplaceUserProductSerializer,
    NegotiationLockSerializer,
    NegotiationReleaseLockSerializer,
    NegotiationSerializer,
    NotificationSerializer,
    OrderTrackingEventSerializer,
    ProductChatMessageSerializer,
    ProductTagSerializer,
    PurchaseSerializer,
    SellerBidSerializer,
    SellerChatMessageSerializer,
    SellerProductSerializer,
    ShoppableVideoCategorySerializer,
    ShoppableVideoItemSerializer,
    ShoppableVideoSerializer,
    UserFollowSerializer,
    VideoCommentSerializer,
    VideoReportSerializer,
)
from .services import PDF_AVAILABLE, InvoiceGenerationService
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


class SellerChatMessageViewSet(viewsets.ModelViewSet):
    serializer_class = SellerChatMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        other_user_id = self.request.query_params.get("user_id")
        show_unread = self.request.query_params.get("unread") == "true"

        base_qs = SellerChatMessage.objects.select_related("sender", "target_user").order_by("-timestamp")

        if other_user_id:
            # Specific conversation: messages where user is sender OR recipient
            other_user = User.objects.get(id=other_user_id)
            qs = base_qs.filter(
                models.Q(sender=user, target_user=other_user) | models.Q(sender=other_user, target_user=user)
            )
        else:
            # All conversations involving current user
            qs = base_qs.filter(models.Q(sender=user) | models.Q(target_user=user)).distinct(
                "target_user__id", "sender__id"
            )[
                :50
            ]  # Limit to recent convos

        if show_unread:
            qs = qs.filter(models.Q(target_user=user) & ~models.Q(is_read=True))

        return qs

    def create(self, request, *args, **kwargs):
        # Ensure target_user exists and isn't self
        target_id = request.data.get("target_user")
        if not target_id or int(target_id) == request.user.id:
            return Response(
                {"error": "Valid target_user required and cannot message yourself"}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chat_message = serializer.save(sender=request.user)
        return Response(self.get_serializer(chat_message).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        # Auto-mark as read when recipient views/updates
        if serializer.instance.target_user == self.request.user:
            serializer.instance.is_read = True
        serializer.save()


class ProductChatMessageViewSet(viewsets.ModelViewSet):
    """Chats attached directly to the base `Product` model (producer.Product)."""

    serializer_class = ProductChatMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ProductChatMessage.objects.select_related("sender", "product").all().order_by("-timestamp")
        product_id = self.request.query_params.get("product_id")
        if product_id:
            qs = qs.filter(product_id=product_id)
        else:
            # restrict to messages where the user is sender or owner of the product
            qs = qs.filter(models.Q(sender=user) | models.Q(product__user=user))
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chat = serializer.save()
        return Response(self.get_serializer(chat).data, status=status.HTTP_201_CREATED)


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


class DistributorPermissionMixin:
    """Mixin to handle distributor permission checks efficiently"""

    def check_distributor_permission(self, user):
        """
        Check if user is a distributor with proper error handling
        Returns: (is_distributor: bool, error_response: Response|None)
        """
        if not user or not user.is_authenticated:
            return False, Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        profile = getattr(user, "user_profile", None)

        if not profile:
            return False, Response({"error": "User profile not found"}, status=status.HTTP_403_FORBIDDEN)

        is_distributor = False
        if hasattr(profile, "is_distributor"):
            try:
                # Handle both method and property
                is_distributor = (
                    profile.is_distributor() if callable(profile.is_distributor) else bool(profile.is_distributor)
                )
            except (TypeError, AttributeError) as e:
                logger.warning(f"Error checking distributor status for user {user.id}: {e}")
                is_distributor = False

        if not is_distributor:
            return False, Response({"error": "User is not a distributor"}, status=status.HTTP_403_FORBIDDEN)

        return True, None


class DistributorProfileView(DistributorPermissionMixin, views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Check permissions
        is_distributor, error_response = self.check_distributor_permission(request.user)
        if not is_distributor:
            return error_response

        # Use select_related and prefetch_related for optimized queries
        # Aggregate all metrics in a single query using annotations
        products = (
            MarketplaceProduct.objects.filter(product__user=request.user)
            .select_related("product")
            .annotate(
                views_count=Count("views", distinct=True),
                total_sold=Sum("order_items__quantity"),
                avg_rating=Avg("reviews__rating"),
            )
            .distinct()
        )

        # Build product list with pre-aggregated data
        product_list = [
            {
                "id": product.id,
                "name": getattr(product.product, "name", None) or str(product),
                "views": product.views_count or 0,
                "total_sold": int(product.total_sold or 0),
                "avg_rating": round(float(product.avg_rating or 0), 2),
            }
            for product in products
        ]

        # Single efficient query for orders count with proper filtering
        orders_count = MarketplaceOrder.objects.filter(items__product__product__user=request.user).distinct().count()

        return Response({"products": product_list, "orders_count": orders_count})


class DistributorOrdersView(DistributorPermissionMixin, views.APIView):
    permission_classes = [IsAuthenticated]

    # Cache results for 60 seconds to reduce DB load
    @method_decorator(cache_page(60))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request):
        # Check permissions
        is_distributor, error_response = self.check_distributor_permission(request.user)
        if not is_distributor:
            return error_response

        # Optimized query with selective prefetching
        # Only fetch items that belong to this seller
        seller_items_prefetch = Prefetch(
            "items",
            queryset=MarketplaceOrderItem.objects.select_related("product__product").filter(
                product__product__user=request.user
            ),
            to_attr="seller_items_list",
        )

        queryset = (
            MarketplaceOrder.objects.filter(items__product__product__user=request.user)
            .select_related("delivery", "customer")
            .prefetch_related(seller_items_prefetch)
            .distinct()
            .order_by("-created_at")[:50]
        )

        orders = []
        for order in queryset:
            # Use pre-filtered items from prefetch
            seller_items = order.seller_items_list

            if not seller_items:
                continue  # Skip orders with no seller items (edge case)

            items_for_seller = [
                {
                    "id": item.id,
                    "product_id": item.product.id,
                    "product_name": getattr(item.product.product, "name", None) or str(item.product),
                    "quantity": item.quantity or 0,
                    "unit_price": float(item.unit_price or 0),
                    "total_price": float(item.total_price or 0),
                }
                for item in seller_items
            ]

            # Calculate seller's subtotal for this order
            seller_subtotal = sum(float(item.total_price or 0) for item in seller_items)

            orders.append(
                {
                    "id": order.id,
                    "order_number": order.order_number or f"ORD-{order.id}",
                    "customer": getattr(order.customer, "username", "Unknown") if order.customer else "Guest",
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "order_status": order.order_status or "pending",
                    "payment_status": order.payment_status or "pending",
                    "seller_items": items_for_seller,
                    "seller_subtotal": round(seller_subtotal, 2),
                    "total_amount": float(order.total_amount or 0),
                }
            )

        return Response(orders)


class DistributorOrderInvoiceView(DistributorPermissionMixin, views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        # Check permissions
        is_distributor, error_response = self.check_distributor_permission(request.user)
        if not is_distributor:
            return error_response

        # Validate pk
        if not pk or not str(pk).isdigit():
            return Response({"error": "Invalid order ID"}, status=status.HTTP_400_BAD_REQUEST)

        # Optimized query with prefetch
        try:
            order = MarketplaceOrder.objects.prefetch_related("items__product__product").select_related("invoice").get(pk=pk)
        except MarketplaceOrder.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        except (ValueError, TypeError) as e:
            logger.error(f"Error fetching order {pk}: {e}")
            return Response({"error": "Invalid order ID"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify seller has items in this order
        seller_items = [item for item in order.items.all() if getattr(item.product.product, "user", None) == request.user]

        if not seller_items:
            return Response(
                {"error": "You don't have permission to view invoice for this order"}, status=status.HTTP_403_FORBIDDEN
            )

        # Get or create invoice
        invoice = getattr(order, "invoice", None)

        try:
            # Create invoice if it doesn't exist
            if not invoice:
                try:
                    invoice = InvoiceGenerationService.create_invoice_from_marketplace_order(order)
                except Exception as e:
                    logger.error(f"Error creating invoice for order {pk}: {e}")
                    return Response({"error": "Failed to create invoice"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Generate PDF if needed and available
            if not invoice.pdf_file:
                try:
                    if PDF_AVAILABLE:
                        InvoiceGenerationService.generate_invoice_pdf(invoice)
                    else:
                        return Response(
                            {"message": "Invoice created but PDF generation not available", "invoice_id": invoice.id}
                        )
                except Exception as e:
                    logger.error(f"Error generating PDF for invoice {invoice.id}: {e}")
                    return Response({"message": "Invoice exists but PDF generation failed", "invoice_id": invoice.id})

            # Return PDF file
            if invoice.pdf_file:
                try:
                    pdf_path = invoice.pdf_file.path
                    if not pdf_path or not hasattr(invoice.pdf_file, "path"):
                        return Response({"message": "Invoice PDF path not available", "invoice_id": invoice.id})

                    # Check file exists before opening
                    import os

                    if not os.path.exists(pdf_path):
                        logger.error(f"PDF file not found at path: {pdf_path}")
                        return Response({"error": "Invoice PDF file not found"}, status=status.HTTP_404_NOT_FOUND)

                    return FileResponse(
                        open(pdf_path, "rb"), content_type="application/pdf", filename=f"invoice_{order.order_number}.pdf"
                    )
                except (IOError, OSError) as e:
                    logger.error(f"Error reading PDF file for invoice {invoice.id}: {e}")
                    return Response({"error": "Failed to read invoice PDF"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({"message": "Invoice generated but PDF not available", "invoice_id": invoice.id})

        except Exception as e:
            logger.error(f"Unexpected error processing invoice for order {pk}: {e}")
            return Response({"error": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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

    queryset = (
        ShoppableVideo.objects.select_related("uploader", "creator_profile", "category", "product", "product__product")
        .prefetch_related("items", "additional_products")
        .filter(is_active=True)
        .order_by("-created_at")
    )
    serializer_class = ShoppableVideoSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ["list", "retrieve", "view"]:
            return [AllowAny()]
        return super().get_permissions()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.user.is_authenticated:
            pass
        return context

    def list(self, request, *args, **kwargs):
        """
        Get a personalized feed of videos using the recommendation engine,
        or filter by category if category ID is provided.
        """
        category_id = request.query_params.get("category")
        user = request.user if request.user.is_authenticated else None

        session_interests = request.session.get("video_session_interests", {"categories": {}, "tags": {}})

        if category_id:
            cat_id_str = str(category_id)
            session_interests["categories"][cat_id_str] = session_interests["categories"].get(cat_id_str, 0) + 1
            request.session["video_session_interests"] = session_interests
            videos = self.get_queryset().filter(category_id=category_id)
        else:
            service = VideoRecommendationService()
            videos = service.generate_feed(user, feed_size=100, session_interests=session_interests)

        liked_ids = set()
        saved_ids = set()
        if user:
            video_ids = [v.id for v in videos]
            liked_ids = set(VideoLike.objects.filter(user=user, video_id__in=video_ids).values_list("video_id", flat=True))
            saved_ids = set(VideoSave.objects.filter(user=user, video_id__in=video_ids).values_list("video_id", flat=True))

        page = self.paginate_queryset(videos)
        if page is not None:
            serializer = self.get_serializer(
                page, many=True, context={"request": request, "liked_ids": liked_ids, "saved_ids": saved_ids}
            )
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(
            videos, many=True, context={"request": request, "liked_ids": liked_ids, "saved_ids": saved_ids}
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="more-like-this")
    def more_like_this(self, request, pk=None):
        """Return videos similar to the one being viewed."""
        service = VideoRecommendationService()
        videos = service.get_similar_videos(pk)

        user = request.user if request.user.is_authenticated else None
        liked_ids = set()
        saved_ids = set()
        if user:
            video_ids = [v.id for v in videos]
            liked_ids = set(VideoLike.objects.filter(user=user, video_id__in=video_ids).values_list("video_id", flat=True))
            saved_ids = set(VideoSave.objects.filter(user=user, video_id__in=video_ids).values_list("video_id", flat=True))

        serializer = self.get_serializer(
            videos, many=True, context={"request": request, "liked_ids": liked_ids, "saved_ids": saved_ids}
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="also-watched")
    def also_watched(self, request, pk=None):
        """Collaborative filtering: People who watched this also watched..."""
        service = VideoRecommendationService()
        videos = service.get_social_proof_videos(pk)

        user = request.user if request.user.is_authenticated else None
        liked_ids = set()
        saved_ids = set()
        if user:
            video_ids = [v.id for v in videos]
            liked_ids = set(VideoLike.objects.filter(user=user, video_id__in=video_ids).values_list("video_id", flat=True))
            saved_ids = set(VideoSave.objects.filter(user=user, video_id__in=video_ids).values_list("video_id", flat=True))

        serializer = self.get_serializer(
            videos, many=True, context={"request": request, "liked_ids": liked_ids, "saved_ids": saved_ids}
        )
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="feed/following", permission_classes=[IsAuthenticated])
    def following_feed(self, request):
        """Return a feed composed of videos from creators the user follows."""
        user = request.user
        following_ids = UserFollow.objects.filter(follower=user).values_list("following_id", flat=True)
        qs = self.get_queryset().filter(uploader__id__in=following_ids)

        # Optimized engagement fetch
        video_ids = list(qs.values_list("id", flat=True)[:100])  # Limit for optimization
        liked_ids = set(VideoLike.objects.filter(user=user, video_id__in=video_ids).values_list("video_id", flat=True))
        saved_ids = set(VideoSave.objects.filter(user=user, video_id__in=video_ids).values_list("video_id", flat=True))

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(
                page, many=True, context={"request": request, "liked_ids": liked_ids, "saved_ids": saved_ids}
            )
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(
            qs, many=True, context={"request": request, "liked_ids": liked_ids, "saved_ids": saved_ids}
        )
        return Response(serializer.data)

    def perform_create(self, serializer):
        uploader = self.request.user if self.request.user.is_authenticated else None
        serializer.save(uploader=uploader)

    @action(detail=True, methods=["post"], url_path="add-item")
    def add_item(self, request, pk=None):
        """Add an item (image/video) to a collection/carousel."""
        video = self.get_object()

        # Check if it's a collection
        if video.content_type != "COLLECTION":
            return Response({"error": "Items can only be added to COLLECTION type content."}, status=400)

        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=400)

        order = request.data.get("order", 0)
        item = ShoppableVideoItem.objects.create(video=video, file=file, order=order)
        return Response(ShoppableVideoItemSerializer(item).data, status=201)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def like(self, request, pk=None):
        video = self.get_object()
        user = request.user

        like, created = VideoLike.objects.get_or_create(user=user, video=video)

        if not created:
            # If already liked, unlike it
            like.delete()
            ShoppableVideo.objects.filter(pk=video.pk).update(likes_count=models.F("likes_count") - 1)
            liked = False
        else:
            ShoppableVideo.objects.filter(pk=video.pk).update(likes_count=models.F("likes_count") + 1)
            liked = True

        video.refresh_from_db()

        return Response({"status": "success", "liked": liked, "likes_count": video.likes_count})

    @action(detail=True, methods=["post"], url_path="track-interaction", permission_classes=[AllowAny])
    def track_interaction(self, request, pk=None):
        """
        Track detailed user interactions like 'watch_time', 'dwell_time', or 'cta_click'.
        Supports both authenticated and anonymous session-based tracking.
        """
        video = self.get_object()
        event_type = request.data.get("event_type", "video_view")
        dwell_time = request.data.get("dwell_time")

        user = request.user if request.user.is_authenticated else None

        # Log the interaction for the recommendation engine
        interaction = UserInteraction.objects.create(
            user=user, video=video, event_type=event_type, dwell_time=dwell_time, data=request.data.get("extra_data", {})
        )

        # Update session-level interests for real-time reactivity
        session_interests = request.session.get("video_session_interests", {"categories": {}, "tags": {}})

        # Boost category in current session
        if video.category:
            cat_id = str(video.category.id)
            session_interests["categories"][cat_id] = session_interests["categories"].get(cat_id, 0) + 1

        # Boost tags in current session
        if video.tags:
            for tag in video.tags:
                session_interests["tags"][tag] = session_interests["tags"].get(tag, 0) + 1

        request.session["video_session_interests"] = session_interests

        return Response({"status": "captured", "interaction_id": interaction.id})

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
        ShoppableVideo.objects.filter(pk=video.pk).update(shares_count=models.F("shares_count") + 1)
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

    @action(detail=True, methods=["get", "post"], url_path="product-tags")
    def product_tags(self, request, pk=None):
        """Get or set structured product tags for this video/post.

        GET: anyone can list tags.
        POST: uploader or staff can replace tags for the content.
        """
        video = self.get_object()
        if request.method == "GET":
            tags = video.product_tags.all()
            serializer = ProductTagSerializer(tags, many=True)
            return Response(serializer.data)

        # POST - require authentication and owner/staff
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        if request.user != video.uploader and not request.user.is_staff:
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data.get("product_tags") or []
        if not isinstance(payload, list):
            return Response({"detail": "product_tags must be a list"}, status=status.HTTP_400_BAD_REQUEST)

        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(video)

        created_objs = []
        try:
            with transaction.atomic():
                ProductTag.objects.filter(content_type=ct, object_id=video.pk).delete()
                for item in payload:
                    pid = item.get("product_id")
                    if not pid:
                        raise ValueError("product_id is required for each tag")
                    try:
                        product = MarketplaceProduct.objects.get(pk=pid)
                    except MarketplaceProduct.DoesNotExist:
                        raise ValueError(f"product_id {pid} not found")

                    created = ProductTag.objects.create(
                        content_type=ct,
                        object_id=video.pk,
                        product=product,
                        x=item.get("x", 0.0),
                        y=item.get("y", 0.0),
                        width=item.get("width"),
                        height=item.get("height"),
                        timecode=item.get("timecode"),
                        label=item.get("label", ""),
                        merchant_url=item.get("merchant_url"),
                        affiliate_meta=item.get("affiliate_meta", {}),
                    )
                    created_objs.append(created)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": "Validation error", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ProductTagSerializer(created_objs, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[AllowAny])
    def view(self, request, pk=None):
        """
        Increment the view count for a video.
        """
        video = self.get_object()
        ShoppableVideo.objects.filter(pk=video.pk).update(views_count=models.F("views_count") + 1)
        video.refresh_from_db()

        # Also increment uploader's creator profile views_count if present
        try:
            # We use an update on the queryset to avoid triggering validation/save hooks
            from producer.models import CreatorProfile

            CreatorProfile.objects.filter(user=video.uploader).update(views_count=models.F("views_count") + 1)
        except Exception:
            pass
        return Response({"status": "success", "views_count": video.views_count})


class ShoppableVideoCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Shoppable Video Categories.
    """

    queryset = ShoppableVideoCategory.objects.filter(is_active=True).order_by("order", "name")
    serializer_class = ShoppableVideoCategorySerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve", "creators", "videos"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    @action(detail=True, methods=["get"])
    def creators(self, request, pk=None):
        """Return list of creators who have videos in this category."""
        category = self.get_object()
        from producer.models import CreatorProfile
        from producer.serializers import CreatorProfileSerializer

        creator_ids = ShoppableVideo.objects.filter(category=category, is_active=True).values_list(
            "creator_profile_id", flat=True
        )
        # Also include creators linked via uploader
        uploader_ids = ShoppableVideo.objects.filter(category=category, is_active=True).values_list("uploader_id", flat=True)

        qs = CreatorProfile.objects.filter(
            Q(id__in=creator_ids) | Q(user_id__in=uploader_ids) | Q(video_categories=category)
        ).distinct()

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = CreatorProfileSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)

        serializer = CreatorProfileSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def videos(self, request, pk=None):
        """Return list of videos in this category."""
        category = self.get_object()
        qs = ShoppableVideo.objects.filter(category=category, is_active=True).order_by("-created_at")

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = ShoppableVideoSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)

        serializer = ShoppableVideoSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def follow_creator(request, pk):
    """Follow/unfollow a creator by user id (alias endpoint).

    Returns current follower_count.
    """
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        return Response({"error": "You cannot follow yourself"}, status=status.HTTP_400_BAD_REQUEST)

    follow, created = UserFollow.objects.get_or_create(follower=request.user, following=target)
    if not created:
        # Unfollow
        follow.delete()
        # decrement follower_count if CreatorProfile exists
        try:
            cp = target.creator_profile
            cp.follower_count = models.F("follower_count") - 1
            cp.save()
            cp.refresh_from_db()
            count = cp.follower_count
        except Exception:
            count = UserFollow.objects.filter(following=target).count()
        return Response({"status": "unfollowed", "follower_count": count})

    # created follow
    try:
        cp = target.creator_profile
        cp.follower_count = models.F("follower_count") + 1
        cp.save()
        cp.refresh_from_db()
        count = cp.follower_count
    except Exception:
        count = UserFollow.objects.filter(following=target).count()

    # emit a notification/event if needed
    try:
        Notification.objects.create(
            user=target, notification_type="new_follower", message=f"{request.user.username} started following you"
        )
    except Exception:
        pass

    return Response({"status": "followed", "follower_count": count})


@api_view(["GET"])
@permission_classes([AllowAny])
@never_cache
def affiliate_redirect(request):
    """Resolve an affiliate redirect and log an AffiliateClick, then 302 redirect.

    Query params supported:
    - click_id: UUID of an existing AffiliateClick (if pre-created)
    - post_id + product_id: to resolve ProductTag and its merchant_url/affiliate_meta
    """
    click_id = request.query_params.get("click_id")
    post_id = request.query_params.get("post_id")
    product_id = request.query_params.get("product_id")

    # If click_id provided, try to fetch
    if click_id:
        try:
            ac = AffiliateClick.objects.get(id=click_id)
            # update request info
            ac.ip_address = request.META.get("REMOTE_ADDR")
            ac.user_agent = request.META.get("HTTP_USER_AGENT", "")
            ac.user = request.user if request.user.is_authenticated else ac.user
            ac.save()
            return redirect(ac.redirect_url)
        except AffiliateClick.DoesNotExist:
            return Response({"error": "click_id not found"}, status=status.HTTP_404_NOT_FOUND)

    # Else resolve from post_id and product_id
    if not (post_id and product_id):
        return Response({"error": "post_id and product_id required"}, status=status.HTTP_400_BAD_REQUEST)

    # Find a ProductTag for this content
    tags = ProductTag.objects.filter(object_id=post_id, product_id=product_id).order_by("id")
    if not tags.exists():
        # fallback: redirect to internal product detail
        try:
            mp = MarketplaceProduct.objects.get(id=product_id)
            internal = request.build_absolute_uri(reverse("marketplace-detail", args=[mp.id]))
            return redirect(internal)
        except Exception:
            return Response({"error": "product tag or product not found"}, status=status.HTTP_404_NOT_FOUND)

    tag = tags.first()
    redirect_url = tag.merchant_url or None
    if not redirect_url:
        # fallback to marketplace product page
        try:
            mp = MarketplaceProduct.objects.get(id=product_id)
            redirect_url = request.build_absolute_uri(reverse("marketplace-detail", args=[mp.id]))
        except Exception:
            return Response({"error": "no redirect available"}, status=status.HTTP_404_NOT_FOUND)

    # Log AffiliateClick
    ac = AffiliateClick.objects.create(
        user=request.user if request.user.is_authenticated else None,
        product_id=product_id,
        content_type=ContentType.objects.get_for_model(tag.content_object),
        object_id=tag.object_id,
        redirect_url=redirect_url,
        affiliate_meta=tag.affiliate_meta or {},
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )

    return redirect(redirect_url)


class NegotiationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for handling buyer-seller price and quantity negotiations.
    Now with distributed locking and price masking.
    """

    serializer_class = NegotiationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter negotiations for the authenticated user."""
        user = self.request.user
        queryset = (
            Negotiation.objects.filter(Q(buyer=user) | Q(seller=user))
            .select_related("buyer", "seller", "product", "last_offer_by", "lock_owner")
            .prefetch_related("history")
        )

        status_val = self.request.query_params.get("status")
        if status_val:
            queryset = queryset.filter(status=status_val.upper())

        product_id = self.request.query_params.get("product_id")
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        return queryset

    def get_serializer_context(self):
        """Add request to serializer context for price masking."""
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def perform_create(self, serializer):
        """Create negotiation with initial view permissions."""
        negotiation = serializer.save()

        # Grant initial view permissions to both parties
        view_manager.grant_view_permission(
            negotiation.id, negotiation.buyer_id, float(negotiation.proposed_price), duration=3600
        )
        view_manager.grant_view_permission(
            negotiation.id, negotiation.seller_id, float(negotiation.proposed_price), duration=3600
        )

        logger.info(f"Negotiation {negotiation.id} created with initial view permissions")

    @action(detail=False, methods=["get"])
    @extend_schema(
        summary="Get active negotiation",
        description="Retrieves the current active negotiation for a specific product between the requester and product owner.",
        parameters=[
            {"name": "product", "description": "Product ID", "required": True, "type": "integer", "in": "query"},
        ],
    )
    def active(self, request):
        product_id = request.query_params.get("product")
        if not product_id:
            return Response({"error": "Product ID is required"}, status=400)

        user = request.user
        negotiation = (
            Negotiation.objects.filter(
                Q(buyer=user) | Q(seller=user),
                product_id=product_id,
                status__in=[Negotiation.Status.PENDING, Negotiation.Status.COUNTER_OFFER, Negotiation.Status.LOCKED],
            )
            .order_by("-updated_at")
            .first()
        )

        if not negotiation:
            return Response({"detail": "No active negotiation found"}, status=status.HTTP_404_NOT_FOUND)

        # Check for expiration on the fly
        if negotiation.mark_as_expired():
            # Clean up any locks
            lock_data = lock_manager.get_lock_owner(negotiation.id)
            if lock_data:
                lock_manager.release_lock(negotiation.id, lock_data["user_id"], lock_data["lock_id"])
            return Response({"detail": "The negotiation for this product has expired"}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(negotiation)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    @extend_schema(
        summary="Acquire negotiation lock",
        description="Acquire a lock to make a counter offer. Only one user can hold the lock at a time.",
        request=NegotiationLockSerializer,
        responses={200: NegotiationLockSerializer},
    )
    def acquire_lock(self, request, pk=None):
        """Acquire a lock for making a counter offer."""
        negotiation = get_object_or_404(self.get_queryset(), pk=pk)

        # Check if negotiation is in a final state
        if negotiation.status in [Negotiation.Status.ACCEPTED, Negotiation.Status.REJECTED]:
            return Response({"error": "Cannot acquire lock on a closed negotiation"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = NegotiationLockSerializer(data=request.data, context={"request": request, "negotiation": negotiation})

        if serializer.is_valid():
            result = serializer.save()
            return Response(result)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    @extend_schema(
        summary="Release negotiation lock",
        description="Release a held lock before making an offer.",
        request=NegotiationReleaseLockSerializer,
        responses={200: NegotiationReleaseLockSerializer},
    )
    def release_lock(self, request, pk=None):
        """Release a held negotiation lock."""
        negotiation = get_object_or_404(self.get_queryset(), pk=pk)

        serializer = NegotiationReleaseLockSerializer(
            data=request.data, context={"request": request, "negotiation": negotiation}
        )

        if serializer.is_valid():
            result = serializer.save()
            return Response(result)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    @extend_schema(summary="Check lock status", description="Check the current lock status of a negotiation.")
    def lock_status(self, request, pk=None):
        """Get current lock status of a negotiation."""
        negotiation = get_object_or_404(self.get_queryset(), pk=pk)

        lock_data = lock_manager.get_lock_owner(pk)
        current_user_id = str(request.user.id)

        response_data = {
            "is_locked": negotiation.is_locked,
            "lock_owner_id": lock_data.get("user_id") if lock_data else None,
            "lock_acquired_at": lock_data.get("acquired_at") if lock_data else None,
            "lock_expires_at": negotiation.lock_expires_at.isoformat() if negotiation.lock_expires_at else None,
            "current_user_has_lock": lock_data.get("user_id") == current_user_id if lock_data else False,
            "can_acquire_lock": self._can_acquire_lock(negotiation, request.user),
        }

        return Response(response_data)

    def _can_acquire_lock(self, negotiation, user):
        """Check if user can acquire lock on this negotiation."""
        # Check if negotiation is in a valid state
        if negotiation.status in [Negotiation.Status.ACCEPTED, Negotiation.Status.REJECTED]:
            return False

        # Check if already locked by another user
        if negotiation.is_locked:
            is_owner, _ = lock_manager.check_lock_ownership(negotiation.id, user.id)
            return is_owner  # Can only "acquire" if already owner (for renewal)

        # Check if it's user's turn
        return user.id != negotiation.last_offer_by_id

    def _check_and_acquire_lock(self, negotiation, user):
        """
        Helper method to check lock status and acquire if needed.
        Returns (success, lock_id, error_message)
        """
        # Check if negotiation is locked
        if negotiation.is_locked:
            # Check if user owns the lock
            is_owner, lock_data = lock_manager.check_lock_ownership(negotiation.id, user.id)
            if not is_owner:
                return False, None, "Negotiation is currently locked by another user"
            return True, lock_data.get("lock_id"), None
        else:
            # Try to acquire lock
            lock_id = lock_manager.acquire_lock(negotiation.id, user.id, timeout=300)
            if not lock_id:
                return False, None, "Failed to acquire lock for negotiation"
            return True, lock_id, None

    def _validate_counter_offer(self, negotiation, user, proposed_price, proposed_quantity, message):
        """Validate counter offer with locking."""
        # Check if it's user's turn
        if negotiation.last_offer_by == user:
            return False, "It is not your turn to make an offer"

        # Check lock status and acquire if needed
        success, lock_id, error_msg = self._check_and_acquire_lock(negotiation, user)
        if not success:
            return False, error_msg

        try:
            # Convert to Decimal for comparison
            p_price = Decimal(str(proposed_price))
            p_qty = int(proposed_quantity)
            listed_price = Decimal(str(negotiation.product.discounted_price or negotiation.product.listed_price))

            # Counter-offer validation
            if p_price > listed_price:
                return False, f"Counter-offer price cannot exceed listed price ({listed_price})"

            # Floor price (50% of listed price)
            floor_price = listed_price * Decimal("0.5")
            if p_price < floor_price:
                return False, f"Counter-offer price is too low. Minimum allowed is {floor_price}"

            if negotiation.product.min_order and p_qty < negotiation.product.min_order:
                return False, f"Quantity cannot be less than minimum order ({negotiation.product.min_order})"

            if p_qty > negotiation.product.product.stock:
                return False, f"Quantity exceeds available stock ({negotiation.product.product.stock})"

            # Price must be different from current
            if p_price == negotiation.proposed_price:
                return False, "New price must be different from the current price"

            return True, lock_id

        except Exception as e:
            return False, str(e)

    def partial_update(self, request, *args, **kwargs):
        """Handle status updates and counter-offers with locking support."""
        instance = self.get_object()
        user = request.user
        data = request.data
        status_val = data.get("status")
        proposed_price = data.get("proposed_price")
        proposed_quantity = data.get("proposed_quantity")
        message = data.get("message", "")

        # 0. Check if negotiation is already in a final state
        if instance.status in [Negotiation.Status.ACCEPTED, Negotiation.Status.REJECTED]:
            return Response(
                {"error": "This negotiation has already been closed and cannot be modified."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 0.1 Check product availability
        if not instance.product.is_available:
            # Release any locks
            lock_data = lock_manager.get_lock_owner(instance.id)
            if lock_data:
                lock_manager.release_lock(instance.id, lock_data["user_id"], lock_data["lock_id"])

            return Response(
                {"error": "The product is no longer available for negotiation."}, status=status.HTTP_400_BAD_REQUEST
            )

        # 0.2 Check B2B verification status
        try:
            if not instance.buyer.user_profile.b2b_verified:
                # Release any locks
                lock_data = lock_manager.get_lock_owner(instance.id)
                if lock_data:
                    lock_manager.release_lock(instance.id, lock_data["user_id"], lock_data["lock_id"])

                return Response(
                    {"error": "Buyer is not B2B verified. Negotiation cannot proceed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception:
            return Response({"error": "Buyer profile not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Handle ACCEPTED status
        if status_val == Negotiation.Status.ACCEPTED:
            is_last_offer_by_me = instance.last_offer_by == user
            if is_last_offer_by_me:
                return Response({"error": "You cannot accept your own offer"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if stock is still sufficient before accepting
            if instance.product.product.stock < instance.proposed_quantity:
                return Response(
                    {"error": f"Insufficient stock ({instance.product.product.stock}) to accept this quantity."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Release any active locks
            lock_data = lock_manager.get_lock_owner(instance.id)
            if lock_data:
                lock_manager.release_lock(instance.id, lock_data["user_id"], lock_data["lock_id"])

            # Clear view permissions
            view_manager.revoke_view_permission(instance.id, instance.buyer_id)
            view_manager.revoke_view_permission(instance.id, instance.seller_id)

            # Update negotiation
            instance.status = Negotiation.Status.ACCEPTED
            instance.lock_owner = None
            instance.lock_expires_at = None
            instance.save()

            # Create history record for acceptance
            NegotiationHistory.objects.create(
                negotiation=instance,
                offer_by=user,
                price=instance.proposed_price,
                quantity=instance.proposed_quantity,
                message="Offer accepted" + (f": {message}" if message else ""),
            )

            # Notify the other party
            target_user = instance.buyer if user == instance.seller else instance.seller
            notify_event(
                user=target_user,
                notif_type=Notification.Type.MARKETPLACE,
                message=f"Negotiation offer for {instance.product.product.name} has been ACCEPTED by {user.username}",
                via_in_app=True,
            )

            return Response(self.get_serializer(instance).data)

        # Handle REJECTED status
        if status_val == Negotiation.Status.REJECTED:
            # Release any active locks
            lock_data = lock_manager.get_lock_owner(instance.id)
            if lock_data:
                lock_manager.release_lock(instance.id, lock_data["user_id"], lock_data["lock_id"])

            # Clear view permissions
            view_manager.revoke_view_permission(instance.id, instance.buyer_id)
            view_manager.revoke_view_permission(instance.id, instance.seller_id)

            # Update negotiation
            instance.status = Negotiation.Status.REJECTED
            instance.lock_owner = None
            instance.lock_expires_at = None
            instance.save()

            is_withdrawal = instance.last_offer_by == user
            msg = f"Offer withdrawn: {message}" if is_withdrawal else f"Offer rejected: {message}"

            NegotiationHistory.objects.create(
                negotiation=instance,
                offer_by=user,
                price=instance.proposed_price,
                quantity=instance.proposed_quantity,
                message=msg,
            )

            # Notify the other party
            target_user = instance.buyer if user == instance.seller else instance.seller
            notify_event(
                user=target_user,
                notif_type=Notification.Type.MARKETPLACE,
                message=f"Negotiation for {instance.product.product.name} has been {'WITHDRAWN' if is_withdrawal else 'REJECTED'} by {user.username}",
                via_in_app=True,
            )

            return Response(self.get_serializer(instance).data)

        # Handle COUNTER_OFFER
        if status_val == Negotiation.Status.COUNTER_OFFER or proposed_price or proposed_quantity:
            if not proposed_price or not proposed_quantity:
                return Response(
                    {"error": "Price and quantity are required for a counter offer"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Validate counter offer with locking
            is_valid, result = self._validate_counter_offer(instance, user, proposed_price, proposed_quantity, message)

            if not is_valid:
                return Response({"error": result}, status=status.HTTP_400_BAD_REQUEST)

            lock_id = result  # The lock_id from successful validation

            try:
                # Convert to Decimal
                p_price = Decimal(str(proposed_price))
                p_qty = int(proposed_quantity)

                # Update negotiation with lock
                instance.status = Negotiation.Status.COUNTER_OFFER
                instance.proposed_price = p_price
                instance.proposed_quantity = p_qty
                instance.last_offer_by = user
                instance.lock_owner = user
                instance.lock_expires_at = timezone.now() + timezone.timedelta(seconds=300)
                instance.save()

                # Create history entry
                NegotiationHistory.objects.create(
                    negotiation=instance,
                    offer_by=user,
                    price=p_price,
                    quantity=p_qty,
                    message=message,
                )

                # Update view permissions - only the other party can see the new price
                other_party = instance.buyer if user == instance.seller else instance.seller
                view_manager.update_view_permission_on_counter(instance.id, user.id, float(p_price))

                # Release lock after making counter offer
                if lock_id:
                    lock_manager.release_lock(instance.id, user.id, lock_id)

                # Reset lock fields in model
                instance.lock_owner = None
                instance.lock_expires_at = None
                instance.save(update_fields=["lock_owner", "lock_expires_at"])

                # Notify the other party
                notify_event(
                    user=other_party,
                    notif_type=Notification.Type.MARKETPLACE,
                    message=f"New counter-offer received for {instance.product.product.name} from {user.username}",
                    via_in_app=True,
                )

                return Response(self.get_serializer(instance).data)

            except Exception as e:
                logger.error(f"Error making counter offer: {e}")

                # Release lock on error
                if lock_id:
                    try:
                        lock_manager.release_lock(instance.id, user.id, lock_id)
                    except Exception as lock_error:
                        logger.error(f"Error releasing lock: {lock_error}")

                return Response(
                    {"error": f"Error making counter offer: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # Handle other updates (if any)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @extend_schema(
        summary="Force release lock",
        description="Force release a lock (admin/seller only when lock is stuck)",
        responses={200: {"message": "Lock released successfully"}},
    )
    def force_release_lock(self, request, pk=None):
        """Force release a lock (admin/seller only)."""
        negotiation = get_object_or_404(self.get_queryset(), pk=pk)
        user = request.user

        # Only seller or admin can force release
        if user != negotiation.seller and not user.is_staff:
            return Response({"error": "Only the seller or admin can force release locks"}, status=status.HTTP_403_FORBIDDEN)

        # Get current lock owner
        lock_data = lock_manager.get_lock_owner(pk)

        if not lock_data:
            return Response({"message": "No active lock found"})

        # Force release the lock
        lock_manager.release_lock(pk, lock_data["user_id"], lock_data.get("lock_id", ""))

        # Update negotiation model
        negotiation.lock_owner = None
        negotiation.lock_expires_at = None
        if negotiation.status == Negotiation.Status.LOCKED:
            negotiation.status = Negotiation.Status.COUNTER_OFFER
        negotiation.save()

        return Response({"message": "Lock force released successfully", "previous_lock_owner": lock_data.get("user_id")})

    @action(detail=True, methods=["post"])
    @extend_schema(
        summary="Extend lock",
        description="Extend the current lock duration",
        request={"type": "object", "properties": {"additional_seconds": {"type": "integer"}}},
        responses={200: {"message": "Lock extended successfully"}},
    )
    def extend_lock(self, request, pk=None):
        """Extend the current lock duration."""
        negotiation = get_object_or_404(self.get_queryset(), pk=pk)
        user = request.user

        # Check if user owns the lock
        is_owner, lock_data = lock_manager.check_lock_ownership(negotiation.id, user.id)
        if not is_owner:
            return Response({"error": "You don't own the lock on this negotiation"}, status=status.HTTP_403_FORBIDDEN)

        additional_seconds = request.data.get("additional_seconds", 300)

        # Extend lock in Redis
        lock_key = f"negotiation:{negotiation.id}:lock"
        self.redis_client.expire(lock_key, additional_seconds)

        # Extend user lock
        user_lock_key = f"negotiation:{negotiation.id}:lock:{user.id}"
        self.redis_client.expire(user_lock_key, additional_seconds)

        # Update model
        negotiation.lock_expires_at = timezone.now() + timezone.timedelta(seconds=additional_seconds)
        negotiation.save(update_fields=["lock_expires_at"])

        return Response(
            {
                "message": "Lock extended successfully",
                "new_expires_at": negotiation.lock_expires_at.isoformat(),
                "additional_seconds": additional_seconds,
            }
        )


class RelatedProductsView(views.APIView):
    """
    API endpoint to show 4 related products when viewing a single product.
    Incorporates randomization for variety.
    """

    permission_classes = [AllowAny]

    @extend_schema(responses={200: MarketplaceProductSerializer(many=True)})
    def get(self, request, product_id):
        current_mp = (
            MarketplaceProduct.objects.select_related(
                "product__category", "product__subcategory", "product__sub_subcategory", "product__brand"
            )
            .filter(id=product_id)
            .first()
        )

        if not current_mp:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        base = current_mp.product

        relevance_score = Case(
            When(product__sub_subcategory=base.sub_subcategory, then=Value(10)),
            When(product__subcategory=base.subcategory, then=Value(5)),
            When(product__category=base.category, then=Value(2)),
            When(product__brand=base.brand, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )

        # Get a larger pool for variety
        pool_size = 12
        related_products = (
            MarketplaceProduct.objects.filter(is_available=True)
            .exclude(id=current_mp.id)
            .annotate(relevance=relevance_score)
            .filter(relevance__gt=0)
            .select_related("product", "product__category")
            .order_by("-relevance", "-view_count", "-rank_score")[:pool_size]
        )

        pool = list(related_products)
        random.shuffle(pool)
        results = pool[:4]

        if len(results) < 4:
            already_included = [p.id for p in results] + [current_mp.id]
            backfill_needed = 4 - len(results)

            backfill_pool = (
                MarketplaceProduct.objects.filter(is_available=True)
                .exclude(id__in=already_included)
                .order_by("-view_count", "-rank_score")[:pool_size]
            )
            bp_list = list(backfill_pool)
            random.shuffle(bp_list)
            results.extend(bp_list[:backfill_needed])

        serializer = MarketplaceProductSerializer(results, many=True, context={"request": request})
        return Response(serializer.data)


class MoreFromSellerView(views.APIView):
    """
    API endpoint to show 4 more products from the same seller.
    Includes randomization for variety.
    """

    permission_classes = [AllowAny]

    @extend_schema(responses={200: MarketplaceProductSerializer(many=True)})
    def get(self, request, product_id):
        current_mp = MarketplaceProduct.objects.filter(id=product_id).select_related("product__user").first()

        if not current_mp:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        seller = current_mp.product.user
        if not seller:
            return Response([], status=status.HTTP_200_OK)

        pool_size = 12
        more_products = (
            MarketplaceProduct.objects.filter(product__user=seller, is_available=True)
            .exclude(id=current_mp.id)
            .select_related("product")
            .order_by("-view_count")[:pool_size]
        )

        pool = list(more_products)
        random.shuffle(pool)
        results = pool[:4]

        serializer = MarketplaceProductSerializer(results, many=True, context={"request": request})
        return Response(serializer.data)


class CouponViewSet(viewsets.ModelViewSet):

    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    lookup_field = "code"

    def get_permissions(self):
        if self.action == "validate":
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def _get_cart_total(self, cart):
        total_data = cart.items.aggregate(
            total=Sum(
                F("quantity")
                * models.functions.Coalesce(
                    "product__discounted_price", "product__listed_price", output_field=models.DecimalField()
                )
            )
        )
        return total_data["total"] or Decimal("0.00")

    @action(detail=False, methods=["post"])
    def validate(self, request):
        """Validate a coupon code for the current user and cart."""
        code = request.data.get("code")
        cart_id = request.data.get("cart_id")

        if not code or not cart_id:
            return Response({"error": "Both coupon code and cart_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        coupon = Coupon.objects.filter(code__iexact=code.strip()).first()

        if not coupon:
            return Response({"valid": False, "message": "Invalid coupon code"}, status=status.HTTP_404_NOT_FOUND)

        cart = get_object_or_404(Cart, id=cart_id, user=request.user)

        items_total = self._get_cart_total(cart)

        if items_total <= 0:
            return Response({"valid": False, "message": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, message = coupon.is_valid(request.user, items_total)

        if not is_valid:
            return Response({"valid": False, "message": message}, status=status.HTTP_200_OK)

        discount = coupon.calculate_discount(items_total)
        return Response(
            {
                "valid": True,
                "message": "Coupon applied successfully",
                "data": {
                    "original_amount": str(items_total),
                    "discount_amount": str(discount),
                    "final_amount": str(items_total - discount),
                    "coupon_code": coupon.code,
                    "discount_type": coupon.discount_type,
                },
            },
            status=status.HTTP_200_OK,
        )
