import requests
from django.conf import settings
from django.db import models, transaction
from django.db.models import OuterRef, QuerySet, Subquery
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status, views, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
)
from rest_framework.response import Response

from main.enums import GlobalEnumSerializer, get_enum_values
from market.models import (
    Bid,
    ChatMessage,
    Feedback,
    Notification,
    OrderTrackingEvent,
    UserInteraction,
)
from producer.models import MarketplaceProduct

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
    Payment,
    ProductView,
)
from .serializers import (
    BidSerializer,
    BidUserSerializer,
    CartItemSerializer,
    CartSerializer,
    ChatMessageSerializer,
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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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
            user_marketplace_sales = MarketplaceSale.objects.filter(
                models.Q(buyer=user) | models.Q(seller=user)
            )
            user_marketplace_orders = MarketplaceOrder.objects.filter(customer=user)
            
            qs = OrderTrackingEvent.objects.filter(
                models.Q(marketplace_sale__in=user_marketplace_sales) |
                models.Q(marketplace_order__in=user_marketplace_orders)
            )
        
        # Filter by order if specified
        marketplace_order_id = self.request.query_params.get("marketplace_order") or self.request.query_params.get("marketplace_order_id")
        if marketplace_order_id:
            qs = qs.filter(marketplace_order_id=marketplace_order_id)
            
        marketplace_sale_id = self.request.query_params.get("marketplace_sale") or self.request.query_params.get("marketplace_sale_id")
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="List customer's marketplace orders",
    description="Get a paginated list of orders for the authenticated customer with filtering options.",
    parameters=[
        {
            'name': 'status',
            'description': 'Filter by order status',
            'required': False,
            'type': 'string',
            'enum': ['pending', 'confirmed', 'processing', 'shipped', 'in_transit', 'delivered', 'completed', 'cancelled', 'failed']
        },
        {
            'name': 'payment_status', 
            'description': 'Filter by payment status',
            'required': False,
            'type': 'string',
            'enum': ['pending', 'paid', 'failed', 'refunded', 'partially_refunded']
        },
        {
            'name': 'search',
            'description': 'Search in order number, product names, or notes',
            'required': False,
            'type': 'string'
        },
        {
            'name': 'date_from',
            'description': 'Filter orders created from this date (YYYY-MM-DD)',
            'required': False,
            'type': 'string',
            'format': 'date'
        },
        {
            'name': 'date_to', 
            'description': 'Filter orders created until this date (YYYY-MM-DD)',
            'required': False,
            'type': 'string',
            'format': 'date'
        },
        {
            'name': 'page',
            'description': 'Page number for pagination',
            'required': False,
            'type': 'integer'
        },
        {
            'name': 'limit',
            'description': 'Number of items per page',
            'required': False,
            'type': 'integer'
        }
    ],
    responses={200: MarketplaceOrderSerializer(many=True)}
)
def my_marketplace_orders(request):
    """Get customer's marketplace orders with filtering."""
    from rest_framework.pagination import PageNumberPagination
    
    # Get base queryset for the authenticated user
    queryset = MarketplaceOrder.objects.filter(
        customer=request.user
    ).select_related('delivery', 'customer').prefetch_related(
        'items__product__product', 
        'items__product__product__images',
        'tracking_events'
    ).filter(is_deleted=False)
    
    # Apply filters
    status = request.query_params.get('status')
    if status and status != 'all':
        queryset = queryset.filter(order_status=status)
        
    payment_status = request.query_params.get('payment_status')
    if payment_status and payment_status != 'all':
        queryset = queryset.filter(payment_status=payment_status)
        
    search = request.query_params.get('search')
    if search:
        queryset = queryset.filter(
            models.Q(order_number__icontains=search) |
            models.Q(items__product__product__name__icontains=search) |
            models.Q(notes__icontains=search)
        ).distinct()
        
    date_from = request.query_params.get('date_from')
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
        
    date_to = request.query_params.get('date_to')
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    # Order by creation date (newest first)
    queryset = queryset.order_by('-created_at')
    
    # Pagination
    paginator = PageNumberPagination()
    paginator.page_size = int(request.query_params.get('limit', 10))
    page = paginator.paginate_queryset(queryset, request)
    
    if page is not None:
        serializer = MarketplaceOrderSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = MarketplaceOrderSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="Get marketplace order details",
    description="Retrieve detailed information about a specific marketplace order.",
    responses={200: MarketplaceOrderSerializer}
)
def marketplace_order_detail(request, pk):
    """Get marketplace order details."""
    try:
        order = MarketplaceOrder.objects.select_related('delivery', 'customer').prefetch_related(
            'items__product__product', 
            'items__product__product__images',
            'tracking_events'
        ).get(pk=pk, customer=request.user, is_deleted=False)
        
        serializer = MarketplaceOrderSerializer(order)
        return Response(serializer.data)
    except MarketplaceOrder.DoesNotExist:
        return Response(
            {"error": "Order not found or you don't have permission to view it."},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="Cancel marketplace order",
    description="Cancel a pending or confirmed marketplace order.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'cancellation_reason': {
                    'type': 'string',
                    'description': 'Reason for cancellation'
                }
            }
        }
    },
    responses={200: MarketplaceOrderSerializer}
)
def cancel_marketplace_order(request, pk):
    """Cancel a marketplace order."""
    try:
        order = MarketplaceOrder.objects.get(pk=pk, customer=request.user, is_deleted=False)
        
        if not order.can_cancel:
            return Response(
                {"error": "This order cannot be cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reason = request.data.get('cancellation_reason', '')
        order.cancel_order(reason)
        
        serializer = MarketplaceOrderSerializer(order)
        return Response(serializer.data)
    except MarketplaceOrder.DoesNotExist:
        return Response(
            {"error": "Order not found or you don't have permission to cancel it."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="Reorder marketplace order items",
    description="Create a reorder request for items from this marketplace order.",
    responses={
        200: {
            'description': 'Success message with instructions',
            'content': {
                'application/json': {
                    'type': 'object',
                    'properties': {
                        'success': {'type': 'boolean'},
                        'message': {'type': 'string'}
                    }
                }
            }
        }
    }
)
def reorder_marketplace_order(request, pk):
    """Reorder items from a marketplace order."""
    try:
        order = MarketplaceOrder.objects.prefetch_related('items').get(
            pk=pk, customer=request.user, is_deleted=False
        )
        
        # For now, return a success message instructing user to add items manually
        # In the future, this could automatically add items to cart
        return Response({
            "success": True,
            "message": f"Please add the {order.items.count()} items from this order to your cart manually from the marketplace."
        })
    except MarketplaceOrder.DoesNotExist:
        return Response(
            {"error": "Order not found or you don't have permission to reorder it."},
            status=status.HTTP_404_NOT_FOUND
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
        return MarketplaceOrder.objects.filter(
            customer=self.request.user
        ).select_related('delivery', 'customer').prefetch_related(
            'items__product__product', 
            'items__product__product__images',
            'tracking_events'
        ).filter(is_deleted=False)

    @extend_schema(
        summary="List customer's orders",
        description="Get a paginated list of orders for the authenticated customer with filtering options.",
        parameters=[
            {
                'name': 'status',
                'description': 'Filter by order status',
                'required': False,
                'type': 'string',
                'enum': ['pending', 'confirmed', 'processing', 'shipped', 'in_transit', 'delivered', 'completed', 'cancelled', 'failed']
            },
            {
                'name': 'payment_status', 
                'description': 'Filter by payment status',
                'required': False,
                'type': 'string',
                'enum': ['pending', 'paid', 'failed', 'refunded', 'partially_refunded']
            },
            {
                'name': 'search',
                'description': 'Search in order number, product names, or notes',
                'required': False,
                'type': 'string'
            },
            {
                'name': 'date_from',
                'description': 'Filter orders created from this date (YYYY-MM-DD)',
                'required': False,
                'type': 'string',
                'format': 'date'
            },
            {
                'name': 'date_to', 
                'description': 'Filter orders created until this date (YYYY-MM-DD)',
                'required': False,
                'type': 'string',
                'format': 'date'
            }
        ]
    )
    def list(self, request, *args, **kwargs):
        """List orders with filtering."""
        queryset = self.get_queryset()
        
        # Apply filters
        status = request.query_params.get('status')
        if status and status != 'all':
            queryset = queryset.filter(order_status=status)
            
        payment_status = request.query_params.get('payment_status')
        if payment_status and payment_status != 'all':
            queryset = queryset.filter(payment_status=payment_status)
            
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(order_number__icontains=search) |
                models.Q(items__product__product__name__icontains=search) |
                models.Q(notes__icontains=search)
            ).distinct()
            
        date_from = request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
            
        date_to = request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get order details",
        description="Retrieve detailed information about a specific order."
    )
    def retrieve(self, request, *args, **kwargs):
        """Get order details."""
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    @extend_schema(
        summary="Cancel order",
        description="Cancel a pending or confirmed order.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'cancellation_reason': {
                        'type': 'string',
                        'description': 'Reason for cancellation'
                    }
                }
            }
        }
    )
    def cancel(self, request, pk=None):
        """Cancel an order."""
        order = self.get_object()
        
        if not order.can_cancel:
            return Response(
                {"error": "This order cannot be cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reason = request.data.get('cancellation_reason', '')
        try:
            order.cancel_order(reason)
            serializer = self.get_serializer(order)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    @extend_schema(
        summary="Reorder items",
        description="Create a new order with the same items as this order.",
        responses={
            200: {
                'description': 'Success message with instructions',
                'content': {
                    'application/json': {
                        'type': 'object',
                        'properties': {
                            'success': {'type': 'boolean'},
                            'message': {'type': 'string'}
                        }
                    }
                }
            }
        }
    )
    def reorder(self, request, pk=None):
        """Reorder items from this order."""
        order = self.get_object()
        
        # For now, return a success message instructing user to add items manually
        # In the future, this could automatically add items to cart
        return Response({
            "success": True,
            "message": f"Please add the {order.items.count()} items from this order to your cart manually from the marketplace."
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@extend_schema(
    summary="Create order from cart",
    description="Create a new marketplace order from cart items.",
    request=CreateOrderSerializer,
    responses={201: MarketplaceOrderSerializer}
)
def create_order(request):
    """Create a new order from cart items."""
    serializer = CreateOrderSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        try:
            order = serializer.save()
            response_serializer = MarketplaceOrderSerializer(order)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {"error": f"Failed to create order: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
