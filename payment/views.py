from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import PaymentTransaction
# ...existing code...

class MyOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transactions = PaymentTransaction.objects.filter(user=request.user).order_by('-created_at')
        data = []
        for tx in transactions:
            data.append({
                "transaction_id": str(tx.transaction_id),
                "order_number": tx.order_number,
                "amount": float(tx.total_amount),
                "status": tx.status,
                "gateway": tx.gateway,
                "created_at": tx.created_at.isoformat(),
                "customer_name": tx.customer_name if hasattr(tx, 'customer_name') else request.user.get_full_name(),
                "customer_email": tx.customer_email if hasattr(tx, 'customer_email') else request.user.email,
                # Add marketplace_sales if available
                "marketplace_sales": getattr(tx, 'marketplace_sales', None),
            })
        return Response({"data": data})
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from market.models import Cart

from .khalti import Khalti
from .models import PaymentGateway, PaymentTransaction, PaymentTransactionStatus

logger = logging.getLogger(__name__)


class PaymentGatewayListView(View):
    """View to get available payment gateways"""

    def get(self, request: HttpRequest) -> JsonResponse:
        try:
            khalti = Khalti()
            gateways = khalti.get_payment_gateways()
            return JsonResponse({"status": "success", "data": gateways})
        except Exception as e:
            print(f"Error fetching payment gateways: {e}")
            return JsonResponse({"status": "error", "message": "Failed to fetch payment gateways"}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request: HttpRequest) -> Response:
    """Initiate payment with Khalti for cart items"""
    data = request.data

    cart_id = data.get("cart_id")
    return_url = settings.KHALTI_RETURN_URL
    gateway = data.get("gateway")

    bank = data.get("bank", None)
    customer_name = data.get("customer_name")
    customer_email = data.get("customer_email")
    customer_phone = data.get("customer_phone")
    tax_amount = Decimal(str(data.get("tax_amount", 0)))
    shipping_cost = Decimal(str(data.get("shipping_cost", 0)))

    if not all([cart_id, return_url, gateway]):
        return Response({"status": "error", "message": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

    if gateway not in [choice[0] for choice in PaymentGateway.choices]:
        return Response({"status": "error", "message": "Invalid payment gateway"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        cart = Cart.objects.prefetch_related("items__product__product").get(id=cart_id, user=request.user)
    except Cart.DoesNotExist:
        return Response({"status": "error", "message": "Cart not found"}, status=status.HTTP_404_NOT_FOUND)

    if not cart.items.exists():
        return Response({"status": "error", "message": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

    subtotal = sum(Decimal(str(item.product.listed_price)) * Decimal(str(item.quantity)) for item in cart.items.all())
    total_amount = subtotal + tax_amount + shipping_cost

    if total_amount <= 0:
        return Response({"status": "error", "message": "Invalid total amount"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            print(
                f"Initiating payment transaction for user={request.user}, cart_id={cart_id}, gateway={gateway}, bank={bank}, subtotal={subtotal}, total_amount={total_amount}"
            )
            payment_transaction = PaymentTransaction.objects.create(
                user=request.user,
                cart=cart,
                gateway=gateway,
                bank=bank,
                subtotal=subtotal,
                tax_amount=tax_amount,
                shipping_cost=shipping_cost,
                total_amount=total_amount,
                return_url=return_url,
                customer_name=customer_name or request.user.get_full_name(),
                customer_email=customer_email or request.user.email,
                customer_phone=customer_phone,
                status=PaymentTransactionStatus.PROCESSING,
            )
            khalti = Khalti()
            result = khalti.pay(
                amount=float(total_amount),
                return_url=return_url,
                purchase_order_id=str(payment_transaction.transaction_id),
                purchase_order_name=payment_transaction.order_number,
                gateway=gateway,
            )

            if isinstance(result, HttpResponseRedirect):
                # Legacy handling for HttpResponseRedirect (shouldn't happen with new Khalti code)
                return Response(
                    {
                        "status": "success",
                        "payment_url": result.url,
                        "transaction_id": str(payment_transaction.transaction_id),
                        "order_number": payment_transaction.order_number,
                    }
                )
            elif isinstance(result, dict) and "payment_url" in result:
                # New handling for dictionary response with pidx
                return Response(
                    {
                        "status": "success",
                        "payment_url": result["payment_url"],
                        "pidx": result.get("pidx"),  # Include pidx in response
                        "transaction_id": str(payment_transaction.transaction_id),
                        "order_number": payment_transaction.order_number,
                    }
                )
            else:
                return Response(
                    {
                        "status": "success",
                        "data": result,
                        "transaction_id": str(payment_transaction.transaction_id),
                        "order_number": payment_transaction.order_number,
                    }
                )
    except Exception as e:
        logger.error(f"Error initiating payment: {e}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def payment_callback(request: HttpRequest) -> Response:
    """Handle payment callback from Khalti"""
    try:
        data = request.data
        khalti_transaction_id = data.get("pidx")

        if not khalti_transaction_id:
            return Response(
                {"status": "error", "message": "Transaction ID not provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        khalti = Khalti()
        inquiry_result = khalti.inquiry(khalti_transaction_id)

        is_successful = khalti.is_success(inquiry_result)

        if is_successful:
            purchase_order_id = inquiry_result.get("purchase_order_id")
            if not purchase_order_id:
                return Response(
                    {"status": "error", "message": "Purchase order ID not found in inquiry result"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                payment_transaction = PaymentTransaction.objects.get(
                    transaction_id=purchase_order_id,
                    status__in=[PaymentTransactionStatus.PENDING, PaymentTransactionStatus.PROCESSING],
                )
            except PaymentTransaction.DoesNotExist:
                return Response(
                    {"status": "error", "message": "Payment transaction not found"}, status=status.HTTP_404_NOT_FOUND
                )

            with transaction.atomic():
                success = payment_transaction.mark_as_completed(khalti_transaction_id)

                if success:
                    # Generate invoice (placeholder: implement actual logic if needed)
                    # payment_transaction.generate_invoice()

                    marketplace_sales = []
                    for item in payment_transaction.transaction_items.select_related("marketplace_sale"):
                        if item.marketplace_sale:
                            marketplace_sales.append(
                                {
                                    "order_number": item.marketplace_sale.order_number,
                                    "product_name": item.product.product.name,
                                    "quantity": item.quantity,
                                    "total_amount": float(item.total_amount),
                                    "seller": item.marketplace_sale.seller.username,
                                }
                            )

                    return Response(
                        {
                            "status": "success",
                            "message": "Payment completed successfully",
                            "data": {
                                "transaction_id": khalti_transaction_id,
                                "payment_transaction_id": str(payment_transaction.transaction_id),
                                "order_number": payment_transaction.order_number,
                                "amount": float(khalti.requested_amount(inquiry_result)),
                                "gateway": payment_transaction.gateway,
                                "marketplace_sales": marketplace_sales,
                                "total_items": len(marketplace_sales),
                                "inquiry": inquiry_result,
                            },
                        }
                    )
                else:
                    return Response(
                        {"status": "error", "message": "Failed to complete payment transaction"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

        else:
            purchase_order_id = inquiry_result.get("purchase_order_id")
            if purchase_order_id:
                try:
                    payment_transaction = PaymentTransaction.objects.get(transaction_id=purchase_order_id)
                    payment_transaction.status = PaymentTransactionStatus.FAILED
                    payment_transaction.gateway_transaction_id = khalti_transaction_id
                    payment_transaction.metadata = inquiry_result
                    payment_transaction.save()
                except PaymentTransaction.DoesNotExist:
                    pass

            return Response(
                {"status": "failed", "message": "Payment was not successful", "data": inquiry_result},
                status=status.HTTP_400_BAD_REQUEST,
            )

    except Exception as e:
        logger.error(f"Error in payment callback: {e}")
        return Response(
            {"status": "error", "message": "Payment verification failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_status(request: HttpRequest, transaction_id: str) -> Response:
    """Check payment status by transaction ID"""
    try:
        try:
            payment_transaction = PaymentTransaction.objects.get(transaction_id=transaction_id, user=request.user)

            if payment_transaction.gateway_transaction_id:
                khalti = Khalti()
                inquiry_result = khalti.inquiry(payment_transaction.gateway_transaction_id)

                return Response(
                    {
                        "status": "success",
                        "data": {
                            "transaction_id": transaction_id,
                            "gateway_transaction_id": payment_transaction.gateway_transaction_id,
                            "order_number": payment_transaction.order_number,
                            "payment_status": payment_transaction.status,
                            "gateway": payment_transaction.gateway,
                            "total_amount": float(payment_transaction.total_amount),
                            "is_successful": khalti.is_success(inquiry_result),
                            "khalti_amount": khalti.requested_amount(inquiry_result),
                            "created_at": payment_transaction.created_at.isoformat(),
                            "completed_at": (
                                payment_transaction.completed_at.isoformat() if payment_transaction.completed_at else None
                            ),
                            "items_count": payment_transaction.get_items_count(),
                            "inquiry": inquiry_result,
                        },
                    }
                )
            else:
                return Response(
                    {
                        "status": "success",
                        "data": {
                            "transaction_id": transaction_id,
                            "order_number": payment_transaction.order_number,
                            "payment_status": payment_transaction.status,
                            "gateway": payment_transaction.gateway,
                            "total_amount": float(payment_transaction.total_amount),
                            "is_successful": payment_transaction.is_completed,
                            "created_at": payment_transaction.created_at.isoformat(),
                            "completed_at": (
                                payment_transaction.completed_at.isoformat() if payment_transaction.completed_at else None
                            ),
                            "items_count": payment_transaction.get_items_count(),
                        },
                    }
                )

        except PaymentTransaction.DoesNotExist:
            return Response(
                {"status": "error", "message": "Payment transaction not found"}, status=status.HTTP_404_NOT_FOUND
            )

    except Exception as e:
        logger.error(f"Error checking payment status: {e}")
        return Response(
            {"status": "error", "message": "Failed to check payment status"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@method_decorator(csrf_exempt, name="dispatch")
class PaymentWebhookView(View):
    """Handle Khalti webhooks (if needed)"""

    def post(self, request: HttpRequest) -> JsonResponse:
        """Handle webhook POST requests"""
        try:
            import json

            webhook_data = json.loads(request.body)
            logger.info(f"Received Khalti webhook: {webhook_data}")

            return JsonResponse({"status": "success", "message": "Webhook processed"})

        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return JsonResponse({"status": "error", "message": "Webhook processing failed"}, status=500)
