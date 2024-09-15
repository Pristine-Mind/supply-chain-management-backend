import requests

from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes

from market.models import Bid, ChatMessage
from producer.models import MarketplaceProduct
from .serializers import PurchaseSerializer, BidSerializer, ChatMessageSerializer
from .filters import ChatFilter, BidFilter
from .models import Payment
from .forms import ShippingAddressForm


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_purchase(request):
    """
    API view to create a purchase and generate the eSewa payment URL.
    """
    serializer = PurchaseSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        purchase_data = serializer.save()
        return Response({
            'purchase': PurchaseSerializer(purchase_data['purchase']).data,
            'payment_url': purchase_data['payment_url']
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BidViewSet(viewsets.ModelViewSet):
    queryset = Bid.objects.all()
    serializer_class = BidSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = BidFilter

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bid = serializer.save()
        return Response(self.get_serializer(bid).data, status=status.HTTP_201_CREATED)


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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def highest_bidder(request, product_id):
    """
    Return whether the authenticated user is the highest bidder for a given product.
    """
    try:
        product = MarketplaceProduct.objects.get(id=product_id)
    except MarketplaceProduct.DoesNotExist:
        return Response({"error": "Product not found"}, status=404)

    highest_bid = Bid.objects.filter(product=product).order_by('-max_bid_amount').first()

    if highest_bid and highest_bid.bidder == request.user:
        return Response(
            {
                "is_highest_bidder": True,
                "max_bid_amount": highest_bid.max_bid_amount
            }
        )
    else:
        return Response({"is_highest_bidder": False})


@api_view(['GET'])
def verify_payment(request):
    # Get the transaction details from the query parameters
    transaction_id = request.GET.get('oid')  # eSewa's transaction ID (your transaction ID)
    ref_id = request.GET.get('refId')        # eSewa's reference ID

    # Fetch the corresponding Payment object using the transaction ID
    payment = get_object_or_404(Payment, transaction_id=transaction_id)

    # Verify the payment with eSewa
    verification_url = 'https://uat.esewa.com.np/epay/transrec'
    payload = {
        'amt': payment.amount,               # The amount from the Payment model
        'scd': 'EPAYTEST',                   # eSewa Merchant ID for sandbox, replace with your live merchant ID in production
        'pid': payment.transaction_id,       # Your transaction ID (same as `oid`)
        'rid': ref_id                        # eSewa's reference ID (refId)
    }

    # Send a POST request to eSewa to verify the payment
    response = requests.post(verification_url, data=payload)

    # Check if the response contains "Success"
    if 'Success' in response.text:
        # If the payment is verified, update the Payment status to 'completed'
        payment.status = 'completed'
        payment.save()
        return redirect('payment_confirmation', payment_id=payment.id)
    else:
        # If the verification failed, update the Payment status to 'failed'
        payment.status = 'failed'
        payment.save()
        return HttpResponse("Payment Verification Failed")


def payment_confirmation(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if payment.status == 'completed':
        context = {
            'payment': payment,
            'message': "Your payment was successful. Please proceed to the shipping details."
        }
        return render(request, 'payment_confirmation.html', context)
    else:
        return HttpResponse("Payment not verified")


@api_view(['POST'])
def shipping_address_form(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)

    if request.method == 'POST':
        form = ShippingAddressForm(request.POST)
        if form.is_valid():
            shipping_address = form.save(commit=False)
            shipping_address.payment = payment
            shipping_address.save()
            return render(request, 'shipping_address_form.html', {
                'form': form,
                'payment': payment,
                'order_success': True,
            })
    else:
        form = ShippingAddressForm()

    return render(request, 'shipping_address_form.html', {'form': form, 'payment': payment})
