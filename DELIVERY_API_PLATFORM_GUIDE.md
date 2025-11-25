# Delivery API Platform - External Integration Guide

## Table of Contents
1. [Overview](#overview)
2. [Architecture Design](#architecture-design)
3. [API Key Management](#api-key-management)
4. [External Business Integration](#external-business-integration)
5. [Webhook System](#webhook-system)
6. [Rate Limiting & Security](#rate-limiting--security)
7. [Documentation & Developer Portal](#documentation--developer-portal)
8. [Implementation Steps](#implementation-steps)
9. [Testing Strategy](#testing-strategy)
10. [Deployment & Monitoring](#deployment--monitoring)

## Overview

Transform your delivery system into a multi-tenant platform that allows external businesses and ecommerce platforms to integrate their delivery needs with your transport network.

### Key Features
- **API-First Architecture**: RESTful APIs with comprehensive documentation
- **Multi-Tenant Support**: Isolated data and billing per business
- **Real-time Tracking**: WebSocket/webhook-based status updates
- **Flexible Pricing**: Per-delivery or subscription-based pricing models
- **White-label Options**: Customizable branding for enterprise clients
- **Analytics Dashboard**: Business insights and delivery analytics

## Architecture Design

### 1. Multi-Tenant Data Model

```python
# New models to support external integrations

class ExternalBusiness(models.Model):
    """External business/ecommerce platform"""
    business_id = models.UUIDField(default=uuid.uuid4, unique=True)
    business_name = models.CharField(max_length=255)
    business_type = models.CharField(max_length=50, choices=[
        ('ecommerce', 'E-commerce Platform'),
        ('restaurant', 'Restaurant'),
        ('pharmacy', 'Pharmacy'),
        ('grocery', 'Grocery Store'),
        ('retail', 'Retail Business'),
        ('other', 'Other')
    ])
    
    # Contact Information
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20)
    business_address = models.TextField()
    
    # API Configuration
    api_key = models.CharField(max_length=128, unique=True)
    api_secret = models.CharField(max_length=256)
    webhook_url = models.URLField(blank=True, null=True)
    webhook_secret = models.CharField(max_length=128, blank=True, null=True)
    
    # Business Settings
    is_active = models.BooleanField(default=True)
    subscription_type = models.CharField(max_length=20, choices=[
        ('pay_per_delivery', 'Pay Per Delivery'),
        ('monthly', 'Monthly Subscription'),
        ('enterprise', 'Enterprise Plan')
    ], default='pay_per_delivery')
    
    # Rate Limiting
    daily_delivery_limit = models.PositiveIntegerField(default=100)
    api_rate_limit = models.PositiveIntegerField(default=1000)  # requests per hour
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ExternalDelivery(models.Model):
    """Delivery created by external business"""
    external_business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE)
    external_order_id = models.CharField(max_length=100)  # Their order ID
    delivery_id = models.UUIDField(default=uuid.uuid4, unique=True)
    
    # Links to internal transport delivery
    transport_delivery = models.OneToOneField(
        'transport.Delivery', 
        on_delete=models.CASCADE,
        related_name='external_delivery'
    )
    
    # External business specific data
    customer_notes = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)
    cod_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Tracking
    external_tracking_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### 2. API Authentication System

```python
# authentication/models.py
class APIKey(models.Model):
    """API Key management for external businesses"""
    business = models.OneToOneField(ExternalBusiness, on_delete=models.CASCADE)
    key = models.CharField(max_length=128, unique=True)
    secret = models.CharField(max_length=256)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    
    def generate_key_pair(self):
        import secrets
        self.key = 'pk_' + secrets.token_urlsafe(32)
        self.secret = 'sk_' + secrets.token_urlsafe(64)
        
class APIUsage(models.Model):
    """Track API usage for billing and monitoring"""
    business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE)
    endpoint = models.CharField(max_length=100)
    method = models.CharField(max_length=10)
    timestamp = models.DateTimeField(auto_now_add=True)
    response_code = models.IntegerField()
    response_time_ms = models.IntegerField()
```

## API Key Management

### 1. Authentication Middleware

```python
# middleware/api_auth.py
import hmac
import hashlib
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

class APIAuthMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.path.startswith('/api/external/'):
            # Extract API key from header
            api_key = request.META.get('HTTP_X_API_KEY')
            signature = request.META.get('HTTP_X_SIGNATURE')
            
            if not api_key or not signature:
                return JsonResponse({'error': 'API key and signature required'}, status=401)
            
            try:
                business = ExternalBusiness.objects.get(api_key=api_key, is_active=True)
                
                # Verify signature
                expected_signature = hmac.new(
                    business.api_secret.encode(),
                    request.body,
                    hashlib.sha256
                ).hexdigest()
                
                if not hmac.compare_digest(signature, expected_signature):
                    return JsonResponse({'error': 'Invalid signature'}, status=401)
                
                # Add business to request
                request.external_business = business
                
            except ExternalBusiness.DoesNotExist:
                return JsonResponse({'error': 'Invalid API key'}, status=401)
```

### 2. Rate Limiting

```python
# middleware/rate_limiting.py
from django.core.cache import cache
from django.http import JsonResponse
import time

class RateLimitMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if hasattr(request, 'external_business'):
            business = request.external_business
            cache_key = f"rate_limit:{business.business_id}"
            
            # Get current usage
            current_usage = cache.get(cache_key, 0)
            
            if current_usage >= business.api_rate_limit:
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'limit': business.api_rate_limit,
                    'reset_time': time.time() + 3600
                }, status=429)
            
            # Increment usage
            cache.set(cache_key, current_usage + 1, 3600)  # 1 hour window
```

## External Business Integration

### 1. External Delivery API

```python
# api/external/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

class ExternalDeliveryCreateView(APIView):
    """Create delivery from external business"""
    
    def post(self, request):
        business = request.external_business
        
        serializer = ExternalDeliveryCreateSerializer(
            data=request.data,
            context={'business': business}
        )
        
        if serializer.is_valid():
            delivery = serializer.save()
            
            # Send webhook notification
            self.send_webhook_notification(business, 'delivery.created', delivery)
            
            return Response({
                'delivery_id': delivery.delivery_id,
                'tracking_number': delivery.transport_delivery.tracking_number,
                'status': delivery.transport_delivery.status,
                'estimated_pickup': delivery.transport_delivery.requested_pickup_date,
                'estimated_delivery': delivery.transport_delivery.requested_delivery_date
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def send_webhook_notification(self, business, event, delivery):
        if business.webhook_url:
            # Async task to send webhook
            send_webhook_notification.delay(
                business.webhook_url,
                business.webhook_secret,
                event,
                delivery.delivery_id
            )

class ExternalDeliveryTrackingView(APIView):
    """Track delivery status"""
    
    def get(self, request, delivery_id):
        try:
            external_delivery = ExternalDelivery.objects.get(
                delivery_id=delivery_id,
                external_business=request.external_business
            )
            
            transport_delivery = external_delivery.transport_delivery
            
            return Response({
                'delivery_id': external_delivery.delivery_id,
                'external_order_id': external_delivery.external_order_id,
                'status': transport_delivery.status,
                'tracking_number': transport_delivery.tracking_number,
                'current_location': {
                    'latitude': transport_delivery.pickup_latitude,
                    'longitude': transport_delivery.pickup_longitude
                },
                'timeline': [
                    {
                        'status': event.status,
                        'timestamp': event.timestamp,
                        'message': event.notes
                    }
                    for event in transport_delivery.tracking_updates.all()
                ]
            })
        
        except ExternalDelivery.DoesNotExist:
            return Response({'error': 'Delivery not found'}, status=404)

class ExternalDeliveryListView(APIView):
    """List all deliveries for business"""
    
    def get(self, request):
        deliveries = ExternalDelivery.objects.filter(
            external_business=request.external_business
        ).order_by('-created_at')
        
        # Add filtering and pagination
        status_filter = request.GET.get('status')
        if status_filter:
            deliveries = deliveries.filter(
                transport_delivery__status=status_filter
            )
        
        # Pagination
        page_size = min(int(request.GET.get('page_size', 50)), 100)
        page = int(request.GET.get('page', 1))
        
        start = (page - 1) * page_size
        end = start + page_size
        
        delivery_data = []
        for delivery in deliveries[start:end]:
            delivery_data.append({
                'delivery_id': delivery.delivery_id,
                'external_order_id': delivery.external_order_id,
                'status': delivery.transport_delivery.status,
                'created_at': delivery.created_at,
                'pickup_address': delivery.transport_delivery.pickup_address,
                'delivery_address': delivery.transport_delivery.delivery_address
            })
        
        return Response({
            'deliveries': delivery_data,
            'total': deliveries.count(),
            'page': page,
            'page_size': page_size
        })
```

### 2. Serializers

```python
# api/external/serializers.py
class ExternalDeliveryCreateSerializer(serializers.Serializer):
    external_order_id = serializers.CharField(max_length=100)
    
    # Pickup details
    pickup_address = serializers.CharField(max_length=500)
    pickup_contact_name = serializers.CharField(max_length=255)
    pickup_contact_phone = serializers.CharField(max_length=20)
    pickup_instructions = serializers.CharField(max_length=500, required=False)
    pickup_date = serializers.DateTimeField()
    
    # Delivery details  
    delivery_address = serializers.CharField(max_length=500)
    delivery_contact_name = serializers.CharField(max_length=255)
    delivery_contact_phone = serializers.CharField(max_length=20)
    delivery_instructions = serializers.CharField(max_length=500, required=False)
    delivery_date = serializers.DateTimeField()
    
    # Package details
    package_weight = serializers.DecimalField(max_digits=8, decimal_places=2)
    package_dimensions = serializers.CharField(max_length=100, required=False)
    package_value = serializers.DecimalField(max_digits=10, decimal_places=2)
    fragile = serializers.BooleanField(default=False)
    cod_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    
    # Special requirements
    special_instructions = serializers.CharField(max_length=1000, required=False)
    priority = serializers.ChoiceField(choices=[
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ], default='normal')
    
    def create(self, validated_data):
        business = self.context['business']
        
        # Create transport delivery
        transport_delivery = TransportDelivery.objects.create(
            pickup_address=validated_data['pickup_address'],
            pickup_contact_name=validated_data['pickup_contact_name'],
            pickup_contact_phone=validated_data['pickup_contact_phone'],
            pickup_instructions=validated_data.get('pickup_instructions', ''),
            
            delivery_address=validated_data['delivery_address'],
            delivery_contact_name=validated_data['delivery_contact_name'],
            delivery_contact_phone=validated_data['delivery_contact_phone'],
            delivery_instructions=validated_data.get('delivery_instructions', ''),
            
            package_weight=validated_data['package_weight'],
            package_dimensions=validated_data.get('package_dimensions', ''),
            package_value=validated_data['package_value'],
            fragile=validated_data.get('fragile', False),
            
            requested_pickup_date=validated_data['pickup_date'],
            requested_delivery_date=validated_data['delivery_date'],
            
            status=TransportStatus.AVAILABLE,
            priority=validated_data.get('priority', 'normal'),
            delivery_fee=self.calculate_delivery_fee(validated_data)
        )
        
        # Create external delivery record
        external_delivery = ExternalDelivery.objects.create(
            external_business=business,
            external_order_id=validated_data['external_order_id'],
            transport_delivery=transport_delivery,
            cod_amount=validated_data.get('cod_amount'),
            special_instructions=validated_data.get('special_instructions', '')
        )
        
        return external_delivery
    
    def calculate_delivery_fee(self, validated_data):
        # Implement your pricing logic here
        base_fee = 10.00
        weight_fee = float(validated_data['package_weight']) * 0.5
        priority_multiplier = {
            'normal': 1.0,
            'high': 1.5,
            'urgent': 2.0
        }.get(validated_data.get('priority', 'normal'), 1.0)
        
        return (base_fee + weight_fee) * priority_multiplier
```

## Webhook System

### 1. Webhook Implementation

```python
# webhooks/tasks.py
from celery import shared_task
import requests
import hmac
import hashlib
import json

@shared_task(retry_backoff=60, max_retries=3)
def send_webhook_notification(webhook_url, webhook_secret, event_type, delivery_id):
    """Send webhook notification to external business"""
    
    try:
        # Get delivery data
        external_delivery = ExternalDelivery.objects.get(delivery_id=delivery_id)
        transport_delivery = external_delivery.transport_delivery
        
        payload = {
            'event_type': event_type,
            'timestamp': timezone.now().isoformat(),
            'delivery_id': str(external_delivery.delivery_id),
            'external_order_id': external_delivery.external_order_id,
            'status': transport_delivery.status,
            'tracking_number': transport_delivery.tracking_number,
            'data': {
                'pickup_address': transport_delivery.pickup_address,
                'delivery_address': transport_delivery.delivery_address,
                'current_location': {
                    'latitude': transport_delivery.pickup_latitude,
                    'longitude': transport_delivery.pickup_longitude
                } if transport_delivery.pickup_latitude else None,
                'transporter': {
                    'name': transport_delivery.transporter.user.get_full_name(),
                    'phone': transport_delivery.transporter.phone
                } if transport_delivery.transporter else None
            }
        }
        
        # Create signature
        payload_json = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            webhook_secret.encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Send webhook
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature,
            'X-Delivery-Webhook': '1'
        }
        
        response = requests.post(
            webhook_url,
            json=payload,
            headers=headers,
            timeout=10
        )
        
        # Log webhook attempt
        WebhookLog.objects.create(
            external_business=external_delivery.external_business,
            event_type=event_type,
            webhook_url=webhook_url,
            payload=payload_json,
            response_code=response.status_code,
            response_body=response.text[:1000],
            success=200 <= response.status_code < 300
        )
        
        if not (200 <= response.status_code < 300):
            raise Exception(f"Webhook failed with status {response.status_code}")
            
    except Exception as e:
        # Log failure
        WebhookLog.objects.create(
            external_business_id=external_delivery.external_business_id,
            event_type=event_type,
            webhook_url=webhook_url,
            error_message=str(e),
            success=False
        )
        raise

class WebhookLog(models.Model):
    """Log webhook attempts for debugging"""
    external_business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=50)
    webhook_url = models.URLField()
    payload = models.TextField()
    response_code = models.IntegerField(null=True)
    response_body = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    success = models.BooleanField()
    timestamp = models.DateTimeField(auto_now_add=True)
```

### 2. Webhook Events

```python
# webhooks/events.py
class WebhookEvents:
    DELIVERY_CREATED = 'delivery.created'
    DELIVERY_ASSIGNED = 'delivery.assigned'
    DELIVERY_PICKED_UP = 'delivery.picked_up'
    DELIVERY_IN_TRANSIT = 'delivery.in_transit'
    DELIVERY_DELIVERED = 'delivery.delivered'
    DELIVERY_FAILED = 'delivery.failed'
    DELIVERY_CANCELLED = 'delivery.cancelled'

# Signal to trigger webhooks
@receiver(post_save, sender=TransportDelivery)
def send_delivery_webhook(sender, instance, **kwargs):
    """Send webhook when delivery status changes"""
    
    try:
        external_delivery = instance.external_delivery
        business = external_delivery.external_business
        
        if business.webhook_url:
            event_map = {
                'assigned': WebhookEvents.DELIVERY_ASSIGNED,
                'picked_up': WebhookEvents.DELIVERY_PICKED_UP,
                'in_transit': WebhookEvents.DELIVERY_IN_TRANSIT,
                'delivered': WebhookEvents.DELIVERY_DELIVERED,
                'failed': WebhookEvents.DELIVERY_FAILED,
                'cancelled': WebhookEvents.DELIVERY_CANCELLED
            }
            
            event = event_map.get(instance.status)
            if event:
                send_webhook_notification.delay(
                    business.webhook_url,
                    business.webhook_secret,
                    event,
                    external_delivery.delivery_id
                )
    except ExternalDelivery.DoesNotExist:
        # Not an external delivery, skip webhook
        pass
```

## Rate Limiting & Security

### 1. Advanced Rate Limiting

```python
# middleware/advanced_rate_limiting.py
class AdvancedRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if hasattr(request, 'external_business'):
            # Check multiple rate limits
            limits = [
                ('requests_per_minute', 60, 100),  # 100 requests per minute
                ('requests_per_hour', 3600, 1000),  # 1000 requests per hour
                ('deliveries_per_day', 86400, request.external_business.daily_delivery_limit)
            ]
            
            for limit_name, window, limit_value in limits:
                if self.is_rate_limited(request.external_business, limit_name, window, limit_value):
                    return JsonResponse({
                        'error': f'Rate limit exceeded for {limit_name}',
                        'limit': limit_value,
                        'window': window
                    }, status=429)
        
        return self.get_response(request)
    
    def is_rate_limited(self, business, limit_name, window, limit_value):
        cache_key = f"rate_limit:{business.business_id}:{limit_name}"
        current_count = cache.get(cache_key, 0)
        
        if current_count >= limit_value:
            return True
        
        cache.set(cache_key, current_count + 1, window)
        return False
```

### 2. Security Features

```python
# security/validators.py
class SecurityValidator:
    @staticmethod
    def validate_pickup_address(address):
        """Validate pickup address to prevent abuse"""
        # Implement geofencing, address validation
        pass
    
    @staticmethod
    def validate_package_details(weight, value):
        """Validate package details"""
        if weight > 50:  # 50kg limit
            raise ValidationError("Package weight exceeds limit")
        
        if value > 10000:  # $10,000 limit
            raise ValidationError("Package value exceeds insurance limit")
    
    @staticmethod
    def detect_suspicious_activity(business, delivery_data):
        """Detect potentially fraudulent deliveries"""
        # Check for suspicious patterns
        recent_deliveries = ExternalDelivery.objects.filter(
            external_business=business,
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()
        
        if recent_deliveries > 50:  # 50 deliveries in 1 hour
            raise ValidationError("Suspicious activity detected")
```

## Documentation & Developer Portal

### 1. API Documentation Structure

```markdown
# API Documentation Template

## Authentication
- API Key: Include in header as `X-API-Key`
- Signature: HMAC-SHA256 signature in `X-Signature` header

## Endpoints

### POST /api/external/deliveries/create
Create a new delivery request

**Request Body:**
```json
{
  "external_order_id": "ORDER123",
  "pickup_address": "123 Business St, City, State",
  "pickup_contact_name": "John Doe",
  "pickup_contact_phone": "+1234567890",
  "pickup_date": "2024-12-01T10:00:00Z",
  "delivery_address": "456 Customer Ave, City, State",
  "delivery_contact_name": "Jane Smith",
  "delivery_contact_phone": "+0987654321",
  "delivery_date": "2024-12-01T15:00:00Z",
  "package_weight": 2.5,
  "package_value": 100.00,
  "priority": "normal"
}
```

**Response:**
```json
{
  "delivery_id": "uuid-here",
  "tracking_number": "TRK123456",
  "status": "available",
  "estimated_pickup": "2024-12-01T10:00:00Z",
  "estimated_delivery": "2024-12-01T15:00:00Z"
}
```

### GET /api/external/deliveries/{delivery_id}/track
Track delivery status

### Webhook Events
Your webhook endpoint will receive POST requests with delivery updates.

**Webhook Payload:**
```json
{
  "event_type": "delivery.picked_up",
  "timestamp": "2024-12-01T10:30:00Z",
  "delivery_id": "uuid-here",
  "external_order_id": "ORDER123",
  "status": "picked_up",
  "data": {
    "transporter": {
      "name": "Driver Name",
      "phone": "+1234567890"
    },
    "current_location": {
      "latitude": 27.7172,
      "longitude": 85.3240
    }
  }
}
```
```

### 2. SDK Development

```python
# SDK Example (Python)
class DeliveryAPIClient:
    def __init__(self, api_key, api_secret, base_url="https://yourapi.com"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
    
    def create_delivery(self, delivery_data):
        endpoint = "/api/external/deliveries/create"
        return self._make_request("POST", endpoint, delivery_data)
    
    def track_delivery(self, delivery_id):
        endpoint = f"/api/external/deliveries/{delivery_id}/track"
        return self._make_request("GET", endpoint)
    
    def _make_request(self, method, endpoint, data=None):
        import requests
        import json
        import hmac
        import hashlib
        
        url = self.base_url + endpoint
        payload = json.dumps(data) if data else ""
        
        # Create signature
        signature = hmac.new(
            self.api_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            'X-API-Key': self.api_key,
            'X-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        response = requests.request(method, url, headers=headers, data=payload)
        return response.json()

# Usage example
client = DeliveryAPIClient("your_api_key", "your_api_secret")
delivery = client.create_delivery({
    "external_order_id": "ORDER123",
    # ... other fields
})
```

## Implementation Steps

### Phase 1: Core Infrastructure (Week 1-2)
1. **Database Schema**
   - Create ExternalBusiness, ExternalDelivery models
   - Set up API key management
   - Add indexes and constraints

2. **Authentication System**
   - Implement API key authentication
   - Create signature verification
   - Set up rate limiting

### Phase 2: API Development (Week 3-4)
1. **Core APIs**
   - Delivery creation endpoint
   - Delivery tracking endpoint
   - Delivery listing endpoint
   - Status update webhooks

2. **Testing**
   - Unit tests for all endpoints
   - Integration tests with mock external systems
   - Load testing for rate limits

### Phase 3: Business Features (Week 5-6)
1. **Business Dashboard**
   - Registration portal
   - API key management interface
   - Usage analytics
   - Billing integration

2. **Webhook System**
   - Reliable delivery with retries
   - Webhook testing tools
   - Webhook logs and debugging

### Phase 4: Advanced Features (Week 7-8)
1. **Developer Portal**
   - Interactive API documentation
   - SDK downloads
   - Integration guides
   - Sandbox environment

2. **Enterprise Features**
   - White-label options
   - Custom pricing models
   - Dedicated support
   - SLA monitoring

## Testing Strategy

### 1. API Testing

```python
# tests/test_external_api.py
class ExternalAPITestCase(APITestCase):
    def setUp(self):
        self.business = ExternalBusiness.objects.create(
            business_name="Test Business",
            contact_email="test@business.com",
            api_key="test_key",
            api_secret="test_secret"
        )
    
    def test_create_delivery(self):
        payload = {
            "external_order_id": "TEST123",
            "pickup_address": "123 Test St",
            "pickup_contact_name": "Test Picker",
            "pickup_contact_phone": "+1234567890",
            "pickup_date": "2024-12-01T10:00:00Z",
            # ... other required fields
        }
        
        # Create signature
        signature = self.create_signature(payload)
        
        response = self.client.post(
            '/api/external/deliveries/create',
            payload,
            HTTP_X_API_KEY=self.business.api_key,
            HTTP_X_SIGNATURE=signature,
            format='json'
        )
        
        self.assertEqual(response.status_code, 201)
        self.assertIn('delivery_id', response.data)
```

### 2. Load Testing

```python
# locustfile.py
from locust import HttpUser, task
import json
import hmac
import hashlib

class DeliveryAPIUser(HttpUser):
    def on_start(self):
        self.api_key = "test_key"
        self.api_secret = "test_secret"
    
    @task(10)
    def create_delivery(self):
        payload = {
            "external_order_id": f"ORDER{self.get_unique_id()}",
            # ... delivery data
        }
        
        signature = self.create_signature(payload)
        
        self.client.post(
            "/api/external/deliveries/create",
            json=payload,
            headers={
                'X-API-Key': self.api_key,
                'X-Signature': signature
            }
        )
    
    @task(5)
    def track_delivery(self):
        # Track existing delivery
        pass
```

## Deployment & Monitoring

### 1. Infrastructure Requirements

```yaml
# docker-compose.production.yml
version: '3.8'
services:
  api:
    image: your-delivery-api:latest
    environment:
      - DJANGO_SETTINGS_MODULE=main.settings.production
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql://user:pass@db:5432/deliverydb
    depends_on:
      - db
      - redis
      - celery
    
  celery:
    image: your-delivery-api:latest
    command: celery -A main worker -l info
    depends_on:
      - db
      - redis
    
  redis:
    image: redis:7-alpine
    
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: deliverydb
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### 2. Monitoring Setup

```python
# monitoring/metrics.py
import time
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

class APIMetrics:
    @staticmethod
    def track_api_call(business_id, endpoint, method, response_time, status_code):
        """Track API metrics"""
        date_key = time.strftime("%Y-%m-%d")
        
        # Increment counters
        cache.incr(f"api_calls:{business_id}:{date_key}", 1)
        cache.incr(f"api_calls:{endpoint}:{date_key}", 1)
        
        # Track response times
        cache.lpush(f"response_times:{endpoint}:{date_key}", response_time)
        
        # Track errors
        if status_code >= 400:
            cache.incr(f"api_errors:{business_id}:{date_key}", 1)

@receiver(post_save, sender=ExternalDelivery)
def track_delivery_metrics(sender, instance, created, **kwargs):
    if created:
        date_key = time.strftime("%Y-%m-%d")
        cache.incr(f"deliveries_created:{instance.external_business.business_id}:{date_key}", 1)
        cache.incr(f"deliveries_created:total:{date_key}", 1)
```

### 3. Alerting System

```python
# monitoring/alerts.py
from celery import shared_task
import requests

@shared_task
def check_api_health():
    """Monitor API health and send alerts"""
    
    # Check error rates
    total_calls = cache.get("api_calls:total:today", 0)
    total_errors = cache.get("api_errors:total:today", 0)
    
    if total_calls > 0:
        error_rate = (total_errors / total_calls) * 100
        
        if error_rate > 5:  # 5% error rate threshold
            send_alert(f"API error rate is {error_rate}% (threshold: 5%)")
    
    # Check delivery processing
    pending_deliveries = TransportDelivery.objects.filter(
        status='available',
        created_at__lt=timezone.now() - timedelta(hours=2)
    ).count()
    
    if pending_deliveries > 10:
        send_alert(f"{pending_deliveries} deliveries pending for >2 hours")

def send_alert(message):
    # Send to Slack, email, etc.
    requests.post(SLACK_WEBHOOK_URL, json={"text": f"🚨 Alert: {message}"})
```

## Pricing Models

### 1. Pay-per-Delivery Model

```python
class DeliveryPricing:
    BASE_RATES = {
        'standard': 10.00,
        'express': 15.00,
        'same_day': 25.00
    }
    
    @staticmethod
    def calculate_delivery_fee(delivery_data, business):
        base_fee = DeliveryPricing.BASE_RATES.get(
            delivery_data.get('service_type', 'standard')
        )
        
        # Distance-based pricing
        distance_km = delivery_data.get('distance_km', 5)
        distance_fee = max(0, (distance_km - 5) * 2)  # $2 per km after 5km
        
        # Weight-based pricing
        weight_kg = delivery_data.get('package_weight', 1)
        weight_fee = max(0, (weight_kg - 2) * 1)  # $1 per kg after 2kg
        
        # Business-specific discounts
        discount_rate = business.discount_rate or 0
        
        total = base_fee + distance_fee + weight_fee
        discounted_total = total * (1 - discount_rate / 100)
        
        return round(discounted_total, 2)
```

### 2. Subscription Models

```python
class SubscriptionPricing:
    PLANS = {
        'starter': {
            'monthly_fee': 99,
            'included_deliveries': 100,
            'overage_rate': 0.50
        },
        'growth': {
            'monthly_fee': 299,
            'included_deliveries': 500,
            'overage_rate': 0.40
        },
        'enterprise': {
            'monthly_fee': 999,
            'included_deliveries': 2000,
            'overage_rate': 0.30
        }
    }
```

This comprehensive guide provides the foundation for transforming your delivery system into a multi-tenant platform. Start with Phase 1 and gradually implement additional features based on business needs and customer feedback.