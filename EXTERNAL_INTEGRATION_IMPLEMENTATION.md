# External Business Integration - Implementation

This file contains the actual implementation code for the external business integration system.

## 1. Create the external app structure

```bash
mkdir -p external/{api,models,serializers,middleware,webhooks}
touch external/__init__.py
touch external/api/__init__.py
touch external/models/__init__.py
touch external/serializers/__init__.py
touch external/middleware/__init__.py
touch external/webhooks/__init__.py
```

## 2. Models Implementation

```python
# external/models.py
import uuid
import secrets
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class ExternalBusiness(models.Model):
    """External business/ecommerce platform"""
    
    BUSINESS_TYPES = [
        ('ecommerce', 'E-commerce Platform'),
        ('restaurant', 'Restaurant'),
        ('pharmacy', 'Pharmacy'),
        ('grocery', 'Grocery Store'),
        ('retail', 'Retail Business'),
        ('logistics', 'Logistics Company'),
        ('other', 'Other')
    ]
    
    SUBSCRIPTION_TYPES = [
        ('pay_per_delivery', 'Pay Per Delivery'),
        ('monthly', 'Monthly Subscription'),
        ('enterprise', 'Enterprise Plan'),
        ('trial', 'Trial Period')
    ]
    
    # Basic Information
    business_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    business_name = models.CharField(max_length=255)
    business_type = models.CharField(max_length=50, choices=BUSINESS_TYPES)
    business_description = models.TextField(blank=True)
    
    # Contact Information
    contact_person = models.CharField(max_length=255)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20)
    business_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='Nepal')
    
    # API Configuration
    api_key = models.CharField(max_length=128, unique=True, blank=True)
    api_secret = models.CharField(max_length=256, blank=True)
    webhook_url = models.URLField(blank=True, null=True)
    webhook_secret = models.CharField(max_length=128, blank=True)
    
    # Business Settings
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    subscription_type = models.CharField(max_length=20, choices=SUBSCRIPTION_TYPES, default='trial')
    
    # Limits and Pricing
    daily_delivery_limit = models.PositiveIntegerField(default=50)
    monthly_delivery_limit = models.PositiveIntegerField(default=1000)
    api_rate_limit = models.PositiveIntegerField(default=500)  # requests per hour
    delivery_fee_markup = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)  # percentage
    
    # Billing Information
    billing_email = models.EmailField(blank=True)
    payment_terms = models.CharField(max_length=50, default='monthly')
    credit_limit = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00)
    current_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # Timestamps
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    last_active = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "External Business"
        verbose_name_plural = "External Businesses"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.business_name} ({self.business_type})"
    
    def save(self, *args, **kwargs):
        if not self.api_key:
            self.generate_api_credentials()
        if not self.webhook_secret:
            self.webhook_secret = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)
    
    def generate_api_credentials(self):
        """Generate API key and secret"""
        self.api_key = f"pk_{secrets.token_urlsafe(32)}"
        self.api_secret = f"sk_{secrets.token_urlsafe(64)}"
    
    def is_trial_expired(self):
        """Check if trial period has expired"""
        if self.subscription_type == 'trial' and self.trial_ends_at:
            return timezone.now() > self.trial_ends_at
        return False
    
    def get_delivery_count_today(self):
        """Get today's delivery count"""
        from .models import ExternalDelivery
        return ExternalDelivery.objects.filter(
            external_business=self,
            created_at__date=timezone.now().date()
        ).count()
    
    def can_create_delivery(self):
        """Check if business can create more deliveries"""
        if not self.is_active or self.is_trial_expired():
            return False
        
        today_count = self.get_delivery_count_today()
        return today_count < self.daily_delivery_limit

class ExternalDelivery(models.Model):
    """Delivery created by external business"""
    
    external_business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE, related_name='deliveries')
    external_order_id = models.CharField(max_length=100)  # Their order/reference ID
    delivery_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    
    # Link to internal transport delivery
    transport_delivery = models.OneToOneField(
        'transport.Delivery', 
        on_delete=models.CASCADE,
        related_name='external_delivery'
    )
    
    # External business specific data
    customer_notes = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)
    cod_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Metadata
    external_metadata = models.JSONField(default=dict, blank=True)  # For business-specific data
    
    # Billing
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    markup_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_charged = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "External Delivery"
        verbose_name_plural = "External Deliveries"
        ordering = ['-created_at']
        unique_together = ['external_business', 'external_order_id']
    
    def __str__(self):
        return f"{self.external_business.business_name} - {self.external_order_id}"
    
    def calculate_total_charge(self):
        """Calculate total amount to charge business"""
        base_fee = self.delivery_fee or 0
        markup = (base_fee * self.external_business.delivery_fee_markup / 100)
        return base_fee + markup

class APIUsage(models.Model):
    """Track API usage for monitoring and billing"""
    
    external_business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE)
    endpoint = models.CharField(max_length=100)
    method = models.CharField(max_length=10)
    timestamp = models.DateTimeField(auto_now_add=True)
    response_code = models.IntegerField()
    response_time_ms = models.IntegerField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['external_business', 'timestamp']),
            models.Index(fields=['endpoint', 'timestamp']),
        ]

class WebhookLog(models.Model):
    """Log webhook delivery attempts"""
    
    external_business = models.ForeignKey(ExternalBusiness, on_delete=models.CASCADE)
    external_delivery = models.ForeignKey(ExternalDelivery, on_delete=models.CASCADE, null=True, blank=True)
    event_type = models.CharField(max_length=50)
    webhook_url = models.URLField()
    payload = models.JSONField()
    response_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    success = models.BooleanField()
    attempt_count = models.PositiveIntegerField(default=1)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
```

## 3. API Views Implementation

```python
# external/api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.utils import timezone
from django.db import transaction
from .serializers import ExternalDeliveryCreateSerializer, ExternalDeliverySerializer
from ..models import ExternalBusiness, ExternalDelivery
from ..middleware.auth import ExternalBusinessPermission

class ExternalBusinessMixin:
    """Mixin to ensure external business authentication"""
    permission_classes = [ExternalBusinessPermission]
    
    def get_external_business(self):
        return self.request.external_business

class ExternalDeliveryCreateAPIView(ExternalBusinessMixin, APIView):
    """Create delivery from external business"""
    
    def post(self, request):
        business = self.get_external_business()
        
        # Check if business can create delivery
        if not business.can_create_delivery():
            return Response({
                'error': 'Delivery limit exceeded or account suspended',
                'daily_limit': business.daily_delivery_limit,
                'current_count': business.get_delivery_count_today()
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        serializer = ExternalDeliveryCreateSerializer(
            data=request.data,
            context={'business': business, 'request': request}
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                external_delivery = serializer.save()
                
                # Update business last active
                business.last_active = timezone.now()
                business.save(update_fields=['last_active'])
                
                # Send webhook notification asynchronously
                from ..webhooks.tasks import send_webhook_notification
                if business.webhook_url:
                    send_webhook_notification.delay(
                        business.id,
                        'delivery.created',
                        external_delivery.delivery_id
                    )
                
                return Response({
                    'delivery_id': str(external_delivery.delivery_id),
                    'tracking_number': external_delivery.transport_delivery.tracking_number,
                    'status': external_delivery.transport_delivery.status,
                    'estimated_pickup': external_delivery.transport_delivery.requested_pickup_date,
                    'estimated_delivery': external_delivery.transport_delivery.requested_delivery_date,
                    'delivery_fee': external_delivery.total_charged
                }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ExternalDeliveryDetailAPIView(ExternalBusinessMixin, APIView):
    """Get delivery details and tracking information"""
    
    def get(self, request, delivery_id):
        try:
            external_delivery = ExternalDelivery.objects.select_related(
                'transport_delivery', 'transport_delivery__transporter'
            ).get(
                delivery_id=delivery_id,
                external_business=self.get_external_business()
            )
            
            transport_delivery = external_delivery.transport_delivery
            
            # Get tracking events
            tracking_events = transport_delivery.tracking_updates.all().order_by('-timestamp')
            
            response_data = {
                'delivery_id': str(external_delivery.delivery_id),
                'external_order_id': external_delivery.external_order_id,
                'status': transport_delivery.status,
                'status_display': transport_delivery.get_status_display(),
                'tracking_number': transport_delivery.tracking_number,
                
                'pickup': {
                    'address': transport_delivery.pickup_address,
                    'contact_name': transport_delivery.pickup_contact_name,
                    'contact_phone': transport_delivery.pickup_contact_phone,
                    'latitude': float(transport_delivery.pickup_latitude) if transport_delivery.pickup_latitude else None,
                    'longitude': float(transport_delivery.pickup_longitude) if transport_delivery.pickup_longitude else None,
                    'scheduled_time': transport_delivery.requested_pickup_date,
                    'actual_time': transport_delivery.picked_up_at
                },
                
                'delivery': {
                    'address': transport_delivery.delivery_address,
                    'contact_name': transport_delivery.delivery_contact_name,
                    'contact_phone': transport_delivery.delivery_contact_phone,
                    'latitude': float(transport_delivery.delivery_latitude) if transport_delivery.delivery_latitude else None,
                    'longitude': float(transport_delivery.delivery_longitude) if transport_delivery.delivery_longitude else None,
                    'scheduled_time': transport_delivery.requested_delivery_date,
                    'actual_time': transport_delivery.delivered_at
                },
                
                'package': {
                    'weight': float(transport_delivery.package_weight),
                    'dimensions': transport_delivery.package_dimensions,
                    'value': float(transport_delivery.package_value),
                    'fragile': transport_delivery.fragile,
                    'cod_amount': float(external_delivery.cod_amount) if external_delivery.cod_amount else None
                },
                
                'transporter': {
                    'name': transport_delivery.transporter.user.get_full_name(),
                    'phone': transport_delivery.transporter.phone,
                    'vehicle_type': transport_delivery.transporter.vehicle_type,
                    'vehicle_number': transport_delivery.transporter.vehicle_number
                } if transport_delivery.transporter else None,
                
                'pricing': {
                    'delivery_fee': float(external_delivery.delivery_fee or 0),
                    'markup_fee': float(external_delivery.markup_fee),
                    'total_charged': float(external_delivery.total_charged or 0)
                },
                
                'timeline': [
                    {
                        'status': event.status,
                        'timestamp': event.timestamp,
                        'message': event.notes,
                        'location': {
                            'latitude': float(event.latitude),
                            'longitude': float(event.longitude)
                        } if event.latitude and event.longitude else None
                    }
                    for event in tracking_events
                ],
                
                'created_at': external_delivery.created_at,
                'updated_at': external_delivery.updated_at
            }
            
            return Response(response_data)
            
        except ExternalDelivery.DoesNotExist:
            return Response({
                'error': 'Delivery not found'
            }, status=status.HTTP_404_NOT_FOUND)

class ExternalDeliveryListAPIView(ExternalBusinessMixin, APIView):
    """List deliveries for external business with filtering and pagination"""
    
    def get(self, request):
        business = self.get_external_business()
        
        # Base queryset
        queryset = ExternalDelivery.objects.filter(
            external_business=business
        ).select_related('transport_delivery').order_by('-created_at')
        
        # Apply filters
        status_filter = request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(transport_delivery__status=status_filter)
        
        date_from = request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        date_to = request.GET.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        # Pagination
        page_size = min(int(request.GET.get('page_size', 50)), 100)
        page = int(request.GET.get('page', 1))
        
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = queryset.count()
        deliveries = queryset[start:end]
        
        delivery_data = []
        for delivery in deliveries:
            transport = delivery.transport_delivery
            delivery_data.append({
                'delivery_id': str(delivery.delivery_id),
                'external_order_id': delivery.external_order_id,
                'status': transport.status,
                'status_display': transport.get_status_display(),
                'tracking_number': transport.tracking_number,
                'pickup_address': transport.pickup_address,
                'delivery_address': transport.delivery_address,
                'total_charged': float(delivery.total_charged or 0),
                'created_at': delivery.created_at,
                'estimated_delivery': transport.requested_delivery_date
            })
        
        return Response({
            'deliveries': delivery_data,
            'pagination': {
                'total': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size
            }
        })

class ExternalBusinessStatsAPIView(ExternalBusinessMixin, APIView):
    """Get business statistics and usage metrics"""
    
    def get(self, request):
        business = self.get_external_business()
        
        # Get date range
        from_date = request.GET.get('from_date', timezone.now().date().replace(day=1))
        to_date = request.GET.get('to_date', timezone.now().date())
        
        deliveries = ExternalDelivery.objects.filter(
            external_business=business,
            created_at__date__range=[from_date, to_date]
        )
        
        # Calculate statistics
        total_deliveries = deliveries.count()
        
        status_stats = {}
        for delivery in deliveries:
            status = delivery.transport_delivery.status
            status_stats[status] = status_stats.get(status, 0) + 1
        
        total_revenue = sum(
            delivery.total_charged or 0 
            for delivery in deliveries 
            if delivery.total_charged
        )
        
        # API usage stats
        api_usage = APIUsage.objects.filter(
            external_business=business,
            timestamp__date__range=[from_date, to_date]
        )
        
        api_calls_count = api_usage.count()
        avg_response_time = api_usage.aggregate(
            avg_time=models.Avg('response_time_ms')
        )['avg_time'] or 0
        
        return Response({
            'period': {
                'from': from_date,
                'to': to_date
            },
            'deliveries': {
                'total': total_deliveries,
                'by_status': status_stats,
                'total_revenue': float(total_revenue)
            },
            'api_usage': {
                'total_calls': api_calls_count,
                'avg_response_time_ms': round(avg_response_time, 2),
                'daily_limit': business.api_rate_limit * 24,  # Convert hourly to daily
                'remaining_today': max(0, business.daily_delivery_limit - business.get_delivery_count_today())
            },
            'account': {
                'subscription_type': business.subscription_type,
                'daily_limit': business.daily_delivery_limit,
                'monthly_limit': business.monthly_delivery_limit,
                'current_balance': float(business.current_balance),
                'credit_limit': float(business.credit_limit)
            }
        })
```

## 4. Authentication Middleware

```python
# external/middleware/auth.py
import hmac
import hashlib
import json
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from rest_framework.permissions import BasePermission
from ..models import ExternalBusiness, APIUsage
import time

class ExternalAPIAuthMiddleware(MiddlewareMixin):
    """Middleware to authenticate external API requests"""
    
    def process_request(self, request):
        if not request.path.startswith('/api/external/'):
            return None
        
        # Skip authentication for public endpoints (docs, status, etc.)
        public_endpoints = ['/api/external/docs/', '/api/external/status/']
        if any(request.path.startswith(endpoint) for endpoint in public_endpoints):
            return None
        
        start_time = time.time()
        
        # Extract authentication headers
        api_key = request.META.get('HTTP_X_API_KEY')
        signature = request.META.get('HTTP_X_SIGNATURE')
        timestamp = request.META.get('HTTP_X_TIMESTAMP')
        
        if not all([api_key, signature]):
            return self.auth_error('API key and signature required')
        
        try:
            # Get business by API key
            business = ExternalBusiness.objects.get(api_key=api_key, is_active=True)
            
            # Check if trial expired
            if business.is_trial_expired():
                return self.auth_error('Trial period expired')
            
            # Verify timestamp to prevent replay attacks (optional)
            if timestamp:
                request_time = int(timestamp)
                current_time = int(time.time())
                if abs(current_time - request_time) > 300:  # 5 minutes tolerance
                    return self.auth_error('Request timestamp too old')
            
            # Verify signature
            body = request.body.decode('utf-8') if request.body else ''
            expected_signature = hmac.new(
                business.api_secret.encode(),
                (timestamp + body).encode() if timestamp else body.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                return self.auth_error('Invalid signature')
            
            # Check rate limits
            if self.is_rate_limited(business):
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'limit': business.api_rate_limit,
                    'window': '1 hour'
                }, status=429)
            
            # Add business to request
            request.external_business = business
            request._auth_start_time = start_time
            
        except ExternalBusiness.DoesNotExist:
            return self.auth_error('Invalid API key')
        except Exception as e:
            return self.auth_error(f'Authentication error: {str(e)}')
    
    def process_response(self, request, response):
        # Log API usage
        if hasattr(request, 'external_business') and hasattr(request, '_auth_start_time'):
            response_time_ms = int((time.time() - request._auth_start_time) * 1000)
            
            # Log asynchronously to avoid blocking
            self.log_api_usage.delay(
                request.external_business.id,
                request.path,
                request.method,
                response.status_code,
                response_time_ms,
                self.get_client_ip(request),
                request.META.get('HTTP_USER_AGENT', '')
            )
        
        return response
    
    def auth_error(self, message):
        return JsonResponse({'error': message}, status=401)
    
    def is_rate_limited(self, business):
        """Check if business has exceeded rate limits"""
        cache_key = f"rate_limit:{business.business_id}"
        current_count = cache.get(cache_key, 0)
        
        if current_count >= business.api_rate_limit:
            return True
        
        # Increment counter with 1-hour expiry
        cache.set(cache_key, current_count + 1, 3600)
        return False
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def log_api_usage(business_id, endpoint, method, status_code, response_time_ms, ip_address, user_agent):
        """Log API usage - run as background task"""
        try:
            APIUsage.objects.create(
                external_business_id=business_id,
                endpoint=endpoint,
                method=method,
                response_code=status_code,
                response_time_ms=response_time_ms,
                ip_address=ip_address,
                user_agent=user_agent
            )
        except Exception:
            pass  # Don't fail requests due to logging issues

class ExternalBusinessPermission(BasePermission):
    """Permission class for external API views"""
    
    def has_permission(self, request, view):
        return hasattr(request, 'external_business') and request.external_business.is_active
```

This implementation provides a solid foundation for the external business integration system. You can build upon this by adding more features like billing integration, advanced analytics, and custom business rules as needed.