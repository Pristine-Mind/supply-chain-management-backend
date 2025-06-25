from django.db.models.query import QuerySet
import requests

from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.conf import settings
from django.db.models import Subquery, OuterRef
from django.views.decorators.csrf import csrf_exempt

from rest_framework import viewsets, status, views, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.decorators import api_view, permission_classes
from rest_framework import serializers
from drf_spectacular.utils import extend_schema

from market.models import Bid, ChatMessage, Notification, UserInteraction, Feedback
from producer.models import MarketplaceProduct
from .serializers import (
    PurchaseSerializer,
    BidSerializer,
    ChatMessageSerializer,
    MarketplaceUserProductSerializer,
    BidUserSerializer,
    SellerProductSerializer,
    SellerBidSerializer,
    NotificationSerializer,
    FeedbackSerializer,
    DeliverySerializer,
    CartSerializer,
    CartItemSerializer,
)
from .filters import ChatFilter, BidFilter, UserBidFilter
from .models import Payment, MarketplaceUserProduct, Delivery, Cart, CartItem
from .forms import ShippingAddressForm
from main.enums import GlobalEnumSerializer, get_enum_values


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

    def post(self, request, *args, **kwargs):
        user = request.user if request.user.is_authenticated else None
        if user:
            cart, created = Cart.objects.get_or_create(user=user)
            serializer = self.get_serializer(cart)
            return Response(serializer.data, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)
        else:
            return super().post(request, *args, **kwargs)


class CartItemCreateView(generics.CreateAPIView):
    serializer_class = CartItemSerializer

    def create(self, request, *args, **kwargs):
        cart_id = self.kwargs["cart_id"]
        cart = get_object_or_404(Cart, id=cart_id)

        # Check if item already exists in cart
        product_id = request.data.get("product_id")
        existing_item = CartItem.objects.filter(cart=cart, product_id=product_id).first()

        if existing_item:
            # Update quantity if item exists
            existing_item.quantity += request.data.get("quantity", 1)
            existing_item.save()
            serializer = self.get_serializer(existing_item)
        else:
            # Create new item
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(cart=cart)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CartItemUpdateView(generics.UpdateAPIView):
    serializer_class = CartItemSerializer

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
