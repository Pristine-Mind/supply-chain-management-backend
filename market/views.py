from django.db.models.query import QuerySet
import requests

from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.conf import settings
from django.db.models import Subquery, OuterRef
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from rest_framework import viewsets, status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes

from market.models import Bid, ChatMessage
from producer.models import MarketplaceProduct
from .serializers import (
    PurchaseSerializer,
    BidSerializer,
    ChatMessageSerializer,
    MarketplaceUserProductSerializer,
    BidUserSerializer,
)
from .filters import ChatFilter, BidFilter, UserBidFilter
from .models import Payment, MarketplaceUserProduct
from .forms import ShippingAddressForm


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
        latest_bids = Bid.objects.filter(product=OuterRef('product')).order_by('-bid_date')
        queryset = Bid.objects.filter(id=Subquery(latest_bids.values('id')[:1]), bidder=self.request.user)
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


def payment_confirmation(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if payment.status == "completed":
        context = {"payment": payment, "message": "Your payment was successful. Please proceed to the shipping details."}
        return render(request, "payment_confirmation.html", context)
    else:
        return HttpResponse("Payment not verified")


@api_view(["POST"])
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
        return Response(
            {
                "message": "Update action is not allowed."
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {
                "message": "Delete action is not allowed."
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )


class ProductBidsView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        bids = Bid.objects.filter(product__id=product_id).order_by('-bid_date')
        serializer = BidUserSerializer(bids, many=True)
        return Response(serializer.data)


class UserBidsForProductView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        product = get_object_or_404(MarketplaceProduct, id=product_id)
        user_bids = Bid.objects.filter(bidder=request.user, product=product).order_by('-bid_date')

        bids_data = [
            {
                "bid_amount": bid.bid_amount,
                "max_bid_amount": bid.max_bid_amount,
                "bid_date": bid.bid_date
            }
            for bid in user_bids
        ]

        return Response(bids_data)
