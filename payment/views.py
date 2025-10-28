from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import PaymentTransaction

# ...existing code...


class MyOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transactions = PaymentTransaction.objects.filter(user=request.user).order_by("-created_at")
        data = []
        for tx in transactions:
            data.append(
                {
                    "transaction_id": str(tx.transaction_id),
                    "order_number": tx.order_number,
                    "amount": float(tx.total_amount),
                    "status": tx.status,
                    "gateway": tx.gateway,
                    "created_at": tx.created_at.isoformat(),
                    "customer_name": tx.customer_name if hasattr(tx, "customer_name") else request.user.get_full_name(),
                    "customer_email": tx.customer_email if hasattr(tx, "customer_email") else request.user.email,
                    # Add marketplace_sales if available
                    "marketplace_sales": getattr(tx, "marketplace_sales", None),
                }
            )
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

from market.models import Cart, MarketplaceOrder, DeliveryInfo, OrderStatus, PaymentStatus, OrderTrackingEvent
from market.utils import notify_event

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
    
    # Add comprehensive logging for debugging
    logger.info(f"🎯 Payment initiation request:")
    logger.info(f"   User: {request.user.username} (ID: {request.user.id})")
    logger.info(f"   Gateway: {gateway}")
    logger.info(f"   Cart ID: {cart_id}")
    logger.info(f"   Request data: {data}")

    bank = data.get("bank", None)
    customer_name = data.get("customer_name")
    customer_email = data.get("customer_email")
    customer_phone = data.get("customer_phone")
    tax_amount = Decimal(str(data.get("tax_amount", 0)))
    shipping_cost = Decimal(str(data.get("shipping_cost", 0)))

    if not all([cart_id, return_url, gateway]):
        logger.error(f"❌ Missing required fields: cart_id={cart_id}, return_url={return_url}, gateway={gateway}")
        return Response({"status": "error", "message": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

    if gateway not in [choice[0] for choice in PaymentGateway.choices]:
        logger.error(f"❌ Invalid payment gateway: {gateway}")
        return Response({"status": "error", "message": "Invalid payment gateway"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        cart = Cart.objects.prefetch_related("items__product__product").get(id=cart_id, user=request.user)
        logger.info(f"✅ Cart found: ID={cart.id}, Items count={cart.items.count()}")
    except Cart.DoesNotExist:
        logger.error(f"❌ Cart not found: ID={cart_id}, User={request.user.username}")
        # List all carts for this user for debugging
        user_carts = Cart.objects.filter(user=request.user)
        logger.error(f"   Available carts for user: {[f'Cart {c.id}' for c in user_carts]}")
        return Response({"status": "error", "message": "Cart not found"}, status=status.HTTP_404_NOT_FOUND)

    if not cart.items.exists():
        logger.error(f"❌ Cart is empty: ID={cart_id}, User={request.user.username}")
        # Check if cart had items recently
        logger.error(f"   Cart created: {cart.created_at if hasattr(cart, 'created_at') else 'Unknown'}")
        return Response({"status": "error", "message": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

    # Log cart items for debugging
    cart_items = []
    for item in cart.items.all():
        cart_items.append(f"{item.product.product.name} (Qty: {item.quantity})")
    logger.info(f"📦 Cart items: {cart_items}")

    subtotal = sum(Decimal(str(item.product.listed_price)) * Decimal(str(item.quantity)) for item in cart.items.all())
    total_amount = subtotal + tax_amount + shipping_cost
    
    logger.info(f"💰 Payment calculation: subtotal={subtotal}, tax={tax_amount}, shipping={shipping_cost}, total={total_amount}")

    if total_amount <= 0:
        logger.error(f"❌ Invalid total amount: {total_amount}")
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
            logger.info(f"Calling Khalti.pay() with gateway={gateway}, amount={total_amount}")
            result = khalti.pay(
                amount=float(total_amount),
                return_url=return_url,
                purchase_order_id=str(payment_transaction.transaction_id),
                purchase_order_name=payment_transaction.order_number,
                gateway=gateway,
            )
            logger.info(f"Khalti.pay() returned: type={type(result)}, result={result}")

            if isinstance(result, HttpResponseRedirect):
                # Legacy handling for HttpResponseRedirect (shouldn't happen with new Khalti code)
                logger.info(f"Received HttpResponseRedirect: {result.url}")
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
                logger.info(f"Received dict with payment_url: {result.get('payment_url')}")
                return Response(
                    {
                        "status": "success",
                        "payment_url": result["payment_url"],
                        "pidx": result.get("pidx"),  # Include pidx in response
                        "transaction_id": str(payment_transaction.transaction_id),
                        "order_number": payment_transaction.order_number,
                        "gateway": gateway,  # Include gateway for debugging
                    }
                )
            else:
                logger.warning(f"Unexpected result format from Khalti.pay(): {result}")
                return Response(
                    {
                        "status": "success",
                        "data": result,
                        "transaction_id": str(payment_transaction.transaction_id),
                        "order_number": payment_transaction.order_number,
                        "gateway": gateway,  # Include gateway for debugging
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


def create_marketplace_order_from_payment(payment_transaction):
    """
    Create MarketplaceOrder from completed payment transaction.
    This handles the new order system integration.
    """
    if not payment_transaction.cart:
        return None
        
    try:
        # Create delivery info from payment transaction
        delivery_info = DeliveryInfo.objects.create(
            customer_name=payment_transaction.customer_name or payment_transaction.user.get_full_name(),
            phone_number=payment_transaction.customer_phone or "",
            address="", # Will be updated when delivery address is provided
            city="Kathmandu", # Default, will be updated
            state="Bagmati", # Default, will be updated  
            zip_code="44600", # Default, will be updated
            latitude=27.7172, # Default Kathmandu coordinates
            longitude=85.3240, # Default Kathmandu coordinates
        )
        
        # Create marketplace order
        order = MarketplaceOrder.objects.create_order_from_cart(
            cart=payment_transaction.cart,
            delivery_info=delivery_info,
            payment_method=payment_transaction.gateway
        )
        
        # Update order with payment information
        order.payment_status = PaymentStatus.PAID
        order.order_status = OrderStatus.CONFIRMED
        order.transaction_id = str(payment_transaction.transaction_id)
        order.save()
        
        # Create tracking event for payment confirmation
        OrderTrackingEvent.objects.create(
            marketplace_order=order,
            status=OrderStatus.CONFIRMED,
            message="Payment confirmed successfully",
            metadata={
                "payment_gateway": payment_transaction.gateway,
                "transaction_id": str(payment_transaction.transaction_id),
                "gateway_transaction_id": payment_transaction.gateway_transaction_id,
            }
        )
        
        return order
        
    except Exception as e:
        logger.error(f"Error creating marketplace order from payment: {e}")
        return None


def send_order_confirmation_email(marketplace_order, payment_transaction):
    """Send comprehensive order confirmation email to the buyer."""
    logger.info(f"Starting customer order confirmation for order {marketplace_order.order_number}, customer: {marketplace_order.customer.username}")
    try:
        customer = marketplace_order.customer
        order_items = []
        
        # Collect order items information
        for item in marketplace_order.items.all():
            try:
                order_items.append({
                    "product_name": item.product.product.name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "total_price": float(item.total_price),
                    "seller": item.product.product.user.get_full_name() or item.product.product.user.username,
                })
            except Exception as e:
                logger.warning(f"Error collecting item info for email: {e}")
                continue
        
        # Prepare email context with comprehensive order information
        email_context = {
            "customer_name": customer.get_full_name() or customer.username,
            "order": {
                "order_number": marketplace_order.order_number,
                "total_amount": float(marketplace_order.total_amount),
                "payment_status": marketplace_order.get_payment_status_display(),
                "order_status": marketplace_order.get_order_status_display(),
                "created_at": marketplace_order.created_at.strftime("%B %d, %Y at %I:%M %p"),
                "estimated_delivery": marketplace_order.estimated_delivery_date.strftime("%B %d, %Y") if marketplace_order.estimated_delivery_date else "To be determined",
            },
            "payment": {
                "transaction_id": payment_transaction.transaction_id,
                "gateway": payment_transaction.get_gateway_display(),
                "subtotal": float(payment_transaction.subtotal),
                "tax_amount": float(payment_transaction.tax_amount),
                "shipping_cost": float(payment_transaction.shipping_cost),
                "total_amount": float(payment_transaction.total_amount),
            },
            "items": order_items,
            "delivery_info": None,
        }
        
        # Add delivery information if available
        try:
            if hasattr(marketplace_order, 'delivery_info') and marketplace_order.delivery_info:
                email_context["delivery_info"] = {
                    "recipient_name": marketplace_order.delivery_info.recipient_name,
                    "phone_number": marketplace_order.delivery_info.phone_number,
                    "address": marketplace_order.delivery_info.address,
                    "city": marketplace_order.delivery_info.city,
                    "state": marketplace_order.delivery_info.state,
                    "postal_code": marketplace_order.delivery_info.postal_code,
                }
        except Exception as e:
            logger.warning(f"Error collecting delivery info for email: {e}")
        
        # Prepare notification message
        message = f"🎉 Order Confirmed! Your order #{marketplace_order.order_number} has been successfully placed and payment of Rs. {marketplace_order.total_amount} has been processed. We'll keep you updated on your order status."
        
        # Get customer phone number for SMS
        customer_phone = None
        
        # First, try to get phone from payment transaction
        if payment_transaction.customer_phone:
            customer_phone = payment_transaction.customer_phone
            logger.info(f"Customer {customer.username} has phone number from payment: {customer_phone}")
        # Then try user profile
        elif hasattr(customer, 'user_profile') and customer.user_profile and customer.user_profile.phone_number:
            customer_phone = customer.user_profile.phone_number
            logger.info(f"Customer {customer.username} has phone number from profile: {customer_phone}")
        # Finally try direct user field
        elif hasattr(customer, 'phone_number') and customer.phone_number:
            customer_phone = customer.phone_number
            logger.info(f"Customer {customer.username} has direct phone number: {customer_phone}")
        else:
            logger.warning(f"Customer {customer.username} does not have any phone number available")
        
        # Prepare SMS message (shorter version for SMS)
        sms_message = f"Order #{marketplace_order.order_number} confirmed! Payment Rs.{marketplace_order.total_amount} processed. Track your order online. Thank you!"
        
        logger.info(f"SMS notification enabled: {bool(customer_phone)} for customer {customer.username}")
        
        # Send comprehensive notification
        notify_event(
            user=customer,
            notif_type="ORDER",  # Using string since we need to check the Notification model
            message=message,
            via_in_app=True,
            via_email=True,
            email_addr=customer.email,
            email_tpl="order_confirmation_detailed.html",  # Enhanced template for order confirmation
            email_ctx=email_context,
            via_sms=bool(customer_phone),  # Enable SMS if phone number is available
            sms_number=customer_phone,
            sms_body=sms_message,
        )
        
        logger.info(f"Order confirmation email sent successfully for order {marketplace_order.order_number}")
        
    except Exception as e:
        logger.error(f"Error sending order confirmation email: {e}")


def send_seller_order_notifications(marketplace_order, payment_transaction):
    """Send notifications to sellers about new orders."""
    logger.info(f"Starting seller order notifications for order {marketplace_order.order_number}")
    try:
        # Collect unique sellers from order items
        sellers = set()
        seller_items = {}  # seller -> list of items
        
        for item in marketplace_order.items.all():
            try:
                if hasattr(item.product, 'product') and hasattr(item.product.product, 'user'):
                    seller = item.product.product.user
                    sellers.add(seller)
                    
                    # Group items by seller
                    if seller not in seller_items:
                        seller_items[seller] = []
                    
                    seller_items[seller].append({
                        "product_name": item.product.product.name,
                        "quantity": item.quantity,
                        "unit_price": float(item.unit_price),
                        "total_price": float(item.total_price),
                    })
            except Exception as e:
                logger.warning(f"Error collecting seller info: {e}")
                continue
        
        # Send notification to each seller
        for seller in sellers:
            items = seller_items.get(seller, [])
            total_seller_amount = sum(item['total_price'] for item in items)
            item_count = sum(item['quantity'] for item in items)
            
            # Prepare email context for seller
            seller_email_context = {
                "seller_name": seller.get_full_name() or seller.username,
                "customer_name": marketplace_order.customer.get_full_name() or marketplace_order.customer.username,
                "order": {
                    "order_number": marketplace_order.order_number,
                    "created_at": marketplace_order.created_at.strftime("%B %d, %Y at %I:%M %p"),
                    "payment_status": marketplace_order.get_payment_status_display(),
                    "order_status": marketplace_order.get_order_status_display(),
                },
                "items": items,
                "seller_total": total_seller_amount,
                "item_count": item_count,
                "payment": {
                    "transaction_id": payment_transaction.transaction_id,
                    "gateway": payment_transaction.get_gateway_display(),
                }
            }
            
            # Prepare notification message
            message = f"🛒 New Order! You have received an order #{marketplace_order.order_number} for {item_count} item(s) worth Rs. {total_seller_amount}. Please prepare the items for shipment."
            
            # Get seller phone number for SMS
            seller_phone = None
            if hasattr(seller, 'user_profile') and seller.user_profile and seller.user_profile.phone_number:
                seller_phone = seller.user_profile.phone_number
                logger.info(f"Seller {seller.username} has phone number: {seller_phone}")
            else:
                logger.warning(f"Seller {seller.username} does not have a phone number in profile")
                # Also check if user has phone_number directly
                if hasattr(seller, 'phone_number') and seller.phone_number:
                    seller_phone = seller.phone_number
                    logger.info(f"Seller {seller.username} has direct phone number: {seller_phone}")
            
            # Prepare SMS message (shorter version for SMS)
            sms_message = f"New Order #{marketplace_order.order_number}! {item_count} item(s) worth Rs.{total_seller_amount}. Please prepare for shipment."
            
            logger.info(f"SMS notification enabled: {bool(seller_phone)} for seller {seller.username}")
            
            # Send notification to seller
            notify_event(
                user=seller,
                notif_type="ORDER",
                message=message,
                via_in_app=True,
                via_email=True,
                email_addr=seller.email,
                email_tpl="seller_new_order.html",
                email_ctx=seller_email_context,
                via_sms=bool(seller_phone),  # Enable SMS if phone number is available
                sms_number=seller_phone,
                sms_body=sms_message,
            )
            
            logger.info(f"Seller notification sent successfully to {seller.username} for order {marketplace_order.order_number}")
            
    except Exception as e:
        logger.error(f"Error sending seller order notifications: {e}")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_payment(request: HttpRequest) -> Response:
    """Verify payment status with Khalti using pidx and handle payment completion"""
    data = request.data

    pidx = data.get("pidx")
    reference = data.get("reference")  # This might be our internal transaction ID

    if not pidx:
        return Response({"status": "error", "message": "PIDX is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Use Khalti to verify payment
        khalti = Khalti()
        inquiry_result = khalti.inquiry(pidx)

        if khalti.is_success(inquiry_result):
            # Payment is successful - handle like payment_callback
            purchase_order_id = inquiry_result.get("purchase_order_id")
            
            # Try to find payment transaction by purchase_order_id first, then by reference
            payment_transaction = None
            if purchase_order_id:
                try:
                    payment_transaction = PaymentTransaction.objects.get(
                        transaction_id=purchase_order_id,
                        status__in=[PaymentTransactionStatus.PENDING, PaymentTransactionStatus.PROCESSING],
                    )
                except PaymentTransaction.DoesNotExist:
                    pass
            
            # If not found by purchase_order_id, try by reference
            if not payment_transaction and reference:
                try:
                    payment_transaction = PaymentTransaction.objects.get(
                        transaction_id=reference, 
                        user=request.user,
                        status__in=[PaymentTransactionStatus.PENDING, PaymentTransactionStatus.PROCESSING],
                    )
                except PaymentTransaction.DoesNotExist:
                    pass
            
            if not payment_transaction:
                return Response(
                    {"status": "error", "message": "Payment transaction not found"}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Complete the payment transaction
            with transaction.atomic():
                success = payment_transaction.mark_as_completed(pidx)

                if success:
                    # Create MarketplaceOrder from payment (new system)
                    marketplace_order = create_marketplace_order_from_payment(payment_transaction)
                    
                    # Send order confirmation email to buyer
                    if marketplace_order:
                        logger.info(f"Sending customer order confirmation for order {marketplace_order.order_number}")
                        send_order_confirmation_email(marketplace_order, payment_transaction)
                        logger.info(f"Sending seller order notifications for order {marketplace_order.order_number}")
                        send_seller_order_notifications(marketplace_order, payment_transaction)
                    else:
                        logger.error("Failed to create marketplace order - notifications not sent")
                    
                    # Collect marketplace sales data like in callback (legacy system)
                    marketplace_sales = []
                    try:
                        # Try to get legacy sales data if available
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
                    except Exception as e:
                        logger.warning(f"Error collecting marketplace sales data: {e}")
                        marketplace_sales = []

                    # Prepare response data
                    response_data = {
                        "transaction_id": pidx,
                        "payment_transaction_id": str(payment_transaction.transaction_id),
                        "order_number": payment_transaction.order_number,
                        "amount": float(khalti.requested_amount(inquiry_result)),
                        "gateway": payment_transaction.gateway,
                        "inquiry": inquiry_result,
                        "created_at": payment_transaction.created_at.isoformat(),
                        "completed_at": (
                            payment_transaction.completed_at.isoformat() 
                            if payment_transaction.completed_at else None
                        ),
                    }
                    
                    # Add marketplace order info if created
                    if marketplace_order:
                        response_data.update({
                            "marketplace_order": {
                                "id": marketplace_order.id,
                                "order_number": marketplace_order.order_number,
                                "order_status": marketplace_order.order_status,
                                "payment_status": marketplace_order.payment_status,
                                "total_amount": str(marketplace_order.total_amount),
                            }
                        })
                    
                    # Add legacy sales data if available
                    if marketplace_sales:
                        response_data.update({
                            "marketplace_sales": marketplace_sales,
                            "total_items": len(marketplace_sales),
                        })

                    return Response(
                        {
                            "status": "success",
                            "message": "Payment verified and completed successfully",
                            "payment_status": "completed",
                            "data": response_data,
                        }
                    )
                else:
                    return Response(
                        {"status": "error", "message": "Failed to complete payment transaction"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
        else:
            # Payment failed - update status like in callback
            purchase_order_id = inquiry_result.get("purchase_order_id")
            payment_transaction = None
            
            if purchase_order_id:
                try:
                    payment_transaction = PaymentTransaction.objects.get(transaction_id=purchase_order_id)
                except PaymentTransaction.DoesNotExist:
                    pass
            elif reference:
                try:
                    payment_transaction = PaymentTransaction.objects.get(
                        transaction_id=reference, 
                        user=request.user
                    )
                except PaymentTransaction.DoesNotExist:
                    pass
            
            if payment_transaction:
                payment_transaction.status = PaymentTransactionStatus.FAILED
                payment_transaction.gateway_transaction_id = pidx
                payment_transaction.metadata = inquiry_result
                payment_transaction.save()

            return Response(
                {
                    "status": "error",
                    "message": "Payment verification failed",
                    "payment_status": inquiry_result.get("status", "unknown"),
                    "data": inquiry_result,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    except Exception as e:
        logger.error(f"Payment verification error: {e}")
        return Response(
            {"status": "error", "message": f"Payment verification failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
