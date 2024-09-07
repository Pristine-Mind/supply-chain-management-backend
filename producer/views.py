from django.contrib.auth import authenticate

from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from django.db.models import Sum, Q
from django.utils import timezone
from django.db.models.functions import TruncMonth


from .models import Producer, Customer, Product, Order, Sale
from .serializers import ProducerSerializer, CustomerSerializer, ProductSerializer, OrderSerializer, SaleSerializer


class ProducerViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing producer instances.
    """

    queryset = Producer.objects.all()
    serializer_class = ProducerSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing customer instances.
    """

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer


class ProductViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing product instances.
    """

    queryset = Product.objects.all()
    serializer_class = ProductSerializer


class OrderViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing order instances.
    """

    queryset = Order.objects.all()
    serializer_class = OrderSerializer


class SaleViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing sale instances.
    """

    queryset = Sale.objects.all()
    serializer_class = SaleSerializer


class LoginAPIView(APIView):
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            token, created = Token.objects.get_or_create(user=user)
            return Response({"token": token.key})
        else:
            return Response({"error": "Invalid Credentials"}, status=status.HTTP_400_BAD_REQUEST)


class DashboardAPIView(APIView):
    def get(self, request):
        current_year = timezone.now().year
        total_products = Product.objects.filter(is_active=True).aggregate(total_stock=Sum("stock"))["total_stock"] or 0
        total_orders = Order.objects.count()
        total_sales = Sale.objects.count()
        total_customers = Customer.objects.count()
        pending_orders = Order.objects.filter(Q(status=Order.Status.PENDING) | Q(status=Order.Status.APPROVED)).count()
        total_revenue = Sale.objects.aggregate(total_revenue=Sum("sale_price"))["total_revenue"] or 0

        # Group sales by month for the current year
        sales_trends = (
            Sale.objects.filter(sale_date__year=current_year)
            .annotate(month=TruncMonth("sale_date"))
            .values("month")
            .annotate(total_sales=Sum("sale_price"))
            .order_by("month")
        )
        data = {
            "totalProducts": total_products,
            "totalOrders": total_orders,
            "totalSales": total_sales,
            "totalCustomers": total_customers,
            "pendingOrders": pending_orders,
            "totalRevenue": total_revenue,
            "salesTrends": [{"month": sale["month"].strftime("%B"), "value": sale["total_sales"]} for sale in sales_trends],
        }

        return Response(data)


class UserInfoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({"username": user.username})
