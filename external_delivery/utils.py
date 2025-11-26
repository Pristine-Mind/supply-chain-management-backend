import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.utils import timezone

from .models import APIUsageLog, RateLimitLog, WebhookLog

logger = logging.getLogger(__name__)


def log_rate_limit_exceeded(external_business, request, rate_type="minute"):
    """
    Log rate limit exceeded events for monitoring and analysis
    """
    try:
        client_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR", "")

        RateLimitLog.objects.create(
            external_business=external_business,
            request_ip=client_ip,
            endpoint=request.path,
            request_count=1,
            time_window=rate_type,
            blocked=True,
        )

        logger.warning(
            f"Rate limit exceeded for business {external_business.business_name} "
            f"(ID: {external_business.id}) from IP {client_ip} "
            f"on endpoint {request.path} - {rate_type} limit"
        )
    except Exception as e:
        logger.error(f"Error logging rate limit exceeded: {e}")


def send_webhook_notification(business, event_type, data, webhook_url=None, delivery=None):
    """
    Send webhook notification to external business
    """
    if not business.webhook_url and not webhook_url:
        return {"success": False, "error": "No webhook URL configured"}

    url = webhook_url or business.webhook_url

    # Prepare payload
    payload = {
        "event_type": event_type,
        "timestamp": timezone.now().isoformat(),
        "business_id": str(business.id),
        "data": data,
    }

    # Create HMAC signature
    payload_json = json.dumps(payload, sort_keys=True, default=str)
    signature = hmac.new(business.webhook_secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Event-Type": event_type,
        "User-Agent": "SupplyChain-Webhooks/1.0",
    }

    webhook_log = WebhookLog.objects.create(
        external_business=business, delivery=delivery, event_type=event_type, webhook_url=url, payload=payload
    )

    try:
        start_time = timezone.now()
        response = requests.post(url, json=payload, headers=headers, timeout=30, verify=True)
        end_time = timezone.now()

        response_time = (end_time - start_time).total_seconds()

        webhook_log.response_status = response.status_code
        webhook_log.response_body = response.text[:1000]  # Limit response size
        webhook_log.response_time = response_time
        webhook_log.success = response.status_code < 400

        if not webhook_log.success:
            webhook_log.error_message = f"HTTP {response.status_code}: {response.text[:500]}"

        webhook_log.save()

        return {"success": webhook_log.success, "response_status": response.status_code, "response_time": response_time}

    except requests.exceptions.RequestException as e:
        webhook_log.success = False
        webhook_log.error_message = str(e)[:500]
        webhook_log.retry_count += 1

        # Schedule retry if needed (implement retry logic as needed)
        if webhook_log.retry_count < 3:
            retry_delay = 2**webhook_log.retry_count  # Exponential backoff
            webhook_log.next_retry_at = timezone.now() + timedelta(minutes=retry_delay)

        webhook_log.save()

        return {"success": False, "error": str(e)}


def log_api_usage(external_business, request, response, response_time):
    """
    Log API usage for monitoring and billing
    """
    try:
        # Safe way to get request size without reading body again
        request_size = 0
        try:
            # Try to get the content length from headers first
            request_size = int(request.META.get("CONTENT_LENGTH", 0) or 0)
        except (ValueError, TypeError):
            # If that fails, try to get from body if available and not consumed
            try:
                if hasattr(request, "body") and hasattr(request, "_body"):
                    request_size = len(request._body) if request._body else 0
                elif hasattr(request, "stream") and hasattr(request.stream, "read"):
                    # For DRF requests, try to get from the stream
                    request_size = getattr(request, "_content_length", 0)
            except Exception:
                # If we can't get the request size, default to 0
                request_size = 0

        # Get response size safely
        response_size = 0
        try:
            if hasattr(response, "content"):
                response_size = len(response.content)
            elif hasattr(response, "data"):
                # For DRF responses
                response_size = len(str(response.data).encode("utf-8"))
        except Exception:
            response_size = 0

        # Extract client IP
        client_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR", "")

        APIUsageLog.objects.create(
            external_business=external_business,
            endpoint=request.path,
            method=request.method,
            request_ip=client_ip,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            request_size=request_size,
            response_status=response.status_code,
            response_size=response_size,
            response_time=response_time,
        )
    except Exception as e:
        logger.error(f"Error logging API usage: {e}")


def calculate_delivery_stats(business):
    """
    Calculate comprehensive delivery statistics for a business
    """
    deliveries = business.external_deliveries.all()

    total_deliveries = deliveries.count()
    if total_deliveries == 0:
        return {
            "total_deliveries": 0,
            "current_month_deliveries": 0,
            "successful_deliveries": 0,
            "failed_deliveries": 0,
            "pending_deliveries": 0,
            "total_revenue": Decimal("0.00"),
            "current_month_revenue": Decimal("0.00"),
            "success_rate": 0.0,
            "average_delivery_value": Decimal("0.00"),
        }

    # Count deliveries by status
    successful_deliveries = deliveries.filter(status="delivered").count()
    failed_deliveries = deliveries.filter(status="failed").count()
    pending_deliveries = deliveries.filter(status__in=["pending", "accepted", "picked_up", "in_transit"]).count()

    # Calculate revenue
    total_revenue = sum(
        delivery.platform_commission or Decimal("0.00") for delivery in deliveries if delivery.platform_commission
    )

    # Current month stats
    now = timezone.now()
    current_month_deliveries = deliveries.filter(created_at__month=now.month, created_at__year=now.year)
    current_month_count = current_month_deliveries.count()
    current_month_revenue = sum(
        delivery.platform_commission or Decimal("0.00")
        for delivery in current_month_deliveries
        if delivery.platform_commission
    )

    # Calculate success rate
    success_rate = (successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0.0

    # Average delivery value
    total_package_value = sum(delivery.package_value or Decimal("0.00") for delivery in deliveries)
    average_delivery_value = total_package_value / total_deliveries if total_deliveries > 0 else Decimal("0.00")

    return {
        "total_deliveries": total_deliveries,
        "current_month_deliveries": current_month_count,
        "successful_deliveries": successful_deliveries,
        "failed_deliveries": failed_deliveries,
        "pending_deliveries": pending_deliveries,
        "total_revenue": total_revenue,
        "current_month_revenue": current_month_revenue,
        "success_rate": round(success_rate, 2),
        "average_delivery_value": average_delivery_value,
    }


def generate_tracking_url(tracking_number):
    """
    Generate public tracking URL for a delivery
    """
    base_url = getattr(settings, "FRONTEND_BASE_URL", "https://example.com")
    return f"{base_url}/track/{tracking_number}"


def validate_delivery_data(data, business):
    """
    Validate delivery data against business constraints
    """
    errors = []

    # Check package value limit with proper type checking
    package_value = data.get("package_value", 0)
    if package_value:
        try:
            package_value_decimal = Decimal(str(package_value))
            # Only check limit if business has a max_delivery_value set
            if business.max_delivery_value and package_value_decimal > business.max_delivery_value:
                errors.append(
                    f"Package value ({package_value}) exceeds maximum allowed value ({business.max_delivery_value})"
                )
        except (TypeError, ValueError, InvalidOperation):
            errors.append("Invalid package value format")

    # Check allowed cities
    pickup_city = data.get("pickup_city", "")
    delivery_city = data.get("delivery_city", "")

    if business.allowed_pickup_cities and pickup_city not in business.allowed_pickup_cities:
        errors.append(f"Pickup city '{pickup_city}' is not allowed")

    if business.allowed_delivery_cities and delivery_city not in business.allowed_delivery_cities:
        errors.append(f"Delivery city '{delivery_city}' is not allowed")

    # Validate COD constraints
    is_cod = data.get("is_cod", False)
    cod_amount = data.get("cod_amount")

    if is_cod and not cod_amount:
        errors.append("COD amount is required for Cash on Delivery")

    # Check COD amount vs package value (only if both are provided and valid)
    if is_cod and cod_amount is not None and package_value is not None:
        try:
            cod_amount_decimal = Decimal(str(cod_amount))
            package_value_decimal = Decimal(str(package_value))
            if cod_amount_decimal > package_value_decimal:
                errors.append("COD amount cannot be greater than package value")
        except (TypeError, ValueError, InvalidOperation):
            errors.append("Invalid COD amount or package value format")

    return errors


def format_webhook_delivery_data(delivery):
    """
    Format delivery data for webhook notifications
    """
    return {
        "tracking_number": delivery.tracking_number,
        "external_delivery_id": delivery.external_delivery_id,
        "status": delivery.status,
        "status_display": delivery.get_status_display(),
        "pickup": {
            "name": delivery.pickup_name,
            "phone": delivery.pickup_phone,
            "address": delivery.pickup_address,
            "city": delivery.pickup_city,
        },
        "delivery": {
            "name": delivery.delivery_name,
            "phone": delivery.delivery_phone,
            "address": delivery.delivery_address,
            "city": delivery.delivery_city,
        },
        "package": {
            "description": delivery.package_description,
            "weight": float(delivery.package_weight),
            "value": float(delivery.package_value),
            "fragile": delivery.fragile,
        },
        "payment": {
            "is_cod": delivery.is_cod,
            "cod_amount": float(delivery.cod_amount) if delivery.cod_amount else None,
            "delivery_fee": float(delivery.delivery_fee) if delivery.delivery_fee else None,
        },
        "timestamps": {
            "created_at": delivery.created_at.isoformat(),
            "updated_at": delivery.updated_at.isoformat(),
            "accepted_at": delivery.accepted_at.isoformat() if delivery.accepted_at else None,
            "picked_up_at": delivery.picked_up_at.isoformat() if delivery.picked_up_at else None,
            "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
            "cancelled_at": delivery.cancelled_at.isoformat() if delivery.cancelled_at else None,
        },
        "tracking_url": generate_tracking_url(delivery.tracking_number),
    }


def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two coordinates using Haversine formula
    Returns distance in kilometers
    """
    from math import asin, cos, radians, sin, sqrt

    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers

    return c * r


def estimate_delivery_time(pickup_city, delivery_city, pickup_coords=None, delivery_coords=None):
    """
    Estimate delivery time based on cities and coordinates
    """
    # If same city, return 1 day
    if pickup_city.lower() == delivery_city.lower():
        return timedelta(days=1)

    # If coordinates available, calculate distance
    if pickup_coords and delivery_coords:
        distance = calculate_distance(*pickup_coords, *delivery_coords)

        # Estimate based on distance (assuming 50km/hour average speed)
        estimated_hours = distance / 50
        estimated_days = max(1, int(estimated_hours / 8))  # 8 working hours per day

        return timedelta(days=estimated_days)

    # Default inter-city delivery time
    return timedelta(days=2)
