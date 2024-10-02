from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

from django.db.models import Sum, Q, Count, F, FloatField, ExpressionWrapper
from django.utils import timezone
from django.db.models.functions import TruncMonth


from .models import (
    Producer,
    Customer,
    Product,
    Order,
    Sale,
    StockList,
    MarketplaceProduct,
)
from .serializers import (
    ProducerSerializer,
    CustomerSerializer,
    ProductSerializer,
    OrderSerializer,
    SaleSerializer,
    CustomerSalesSerializer,
    CustomerOrdersSerializer,
    StockListSerializer,
    MarketplaceProductSerializer
)
from .filters import (
    SaleFilter,
    ProducerFilter,
    CustomerFilter,
    ProductFilter,
    MarketplaceProductFilter,
)


class ProducerViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing producer instances.
    """

    queryset = Producer.objects.all().order_by('-created_at')
    serializer_class = ProducerSerializer
    filterset_class = ProducerFilter


class CustomerViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing customer instances.
    """

    queryset = Customer.objects.all().order_by('-created_at')
    serializer_class = CustomerSerializer
    filterset_class = CustomerFilter


class ProductViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing product instances.
    """

    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer
    filterset_class = ProductFilter

    @action(
        detail=False,
        url_path="catgeory",
        methods=("get",),
    )
    def get_category(self, request, pk=None):
        return Response(
            [
                {
                    "key": key,
                    "value": value,
                } for key, value in Product.ProductCategory.choices
            ]
        )


class OrderViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing order instances.
    """

    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer


class SaleViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing sale instances.
    """

    queryset = Sale.objects.all().order_by('-created_at')
    serializer_class = SaleSerializer
    filterset_class = SaleFilter


class DashboardAPIView(APIView):
    def get(self, request):
        current_year = timezone.now().year
        total_products = Product.objects.filter(is_active=True).count() or 0
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


class TopSalesCustomersView(APIView):
    def get(self, request, format=None):
        current_year = timezone.now().year

        top_sales_customers = Sale.objects.filter(
            sale_date__year=current_year
        ).annotate(
            total_sales_amount=ExpressionWrapper(F('sale_price') * F('quantity'), output_field=FloatField())
        ).values(
            'order__customer__id',
            'order__customer__name'
        ).annotate(
            total_sales=Sum('total_sales_amount'),
            name=F('order__customer__name'),
            id=F('order__customer__id')
        ).order_by('-total_sales')
        sales_serializer = CustomerSalesSerializer(top_sales_customers, many=True)
        return Response(sales_serializer.data, status=status.HTTP_200_OK)


class TopOrdersCustomersView(APIView):
    def get(self, request, format=None):
        current_year = timezone.now().year
        top_orders_customers = Customer.objects.filter(
            order__order_date__year=current_year
        ).annotate(
            total_orders=Count('order')
        ).order_by('-total_orders')[:10]

        orders_serializer = CustomerOrdersSerializer(top_orders_customers, many=True)
        return Response(orders_serializer.data, status=status.HTTP_200_OK)


class StockListView(viewsets.ModelViewSet):
    queryset = StockList.objects.filter(is_pushed_to_marketplace=False).distinct()
    serializer_class = StockListSerializer

    @action(detail=True, methods=['post'], url_path='push-to-marketplace')
    def push_to_marketplace(self, request, pk=None):
        try:
            stock_item = self.get_object()
        except StockList.DoesNotExist:
            return Response({"error": "StockList item not found."}, status=status.HTTP_404_NOT_FOUND)

        if MarketplaceProduct.objects.filter(product=stock_item.product).exists():
            return Response(
                {
                    "error": f"Product '{stock_item.product.name}' is already listed in the marketplace."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        MarketplaceProduct.objects.create(
            product=stock_item.product,
            listed_price=stock_item.product.price,
            is_available=True
        )

        # Update the product to have moved to marketplace
        stock_item.is_pushed_to_marketplace = True
        stock_item.save(update_fields=['is_pushed_to_marketplace'])
        return Response(
            {
                "message": f"Product '{stock_item.product.name}' has been successfully pushed to the marketplace."
            },
            status=status.HTTP_200_OK
        )


class MarketplaceProductViewSet(viewsets.ModelViewSet):
    queryset = MarketplaceProduct.objects.filter(is_available=True).order_by('-listed_date')
    serializer_class = MarketplaceProductSerializer
    filterset_class = MarketplaceProductFilter


class StatsAPIView(APIView):
    """
    API to provide sales statistics with optional filtering.
    """

    def get(self, request, *args, **kwargs):
        # Get filter parameters from the query
        location = request.query_params.get('location', None)
        category = request.query_params.get('category', None)
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)

        sales_query = Sale.objects.all()
        if location:
            sales_query = sales_query.filter(order__customer__city=location)
        if category:
            sales_query = sales_query.filter(order__product__category=category)
        if start_date and end_date:
            try:
                start_date = timezone.datetime.strptime(start_date, "%Y-%m-%d")
                end_date = timezone.datetime.strptime(end_date, "%Y-%m-%d")
                sales_query = sales_query.filter(sale_date__gte=start_date, sale_date__lte=end_date)
            except ValueError:
                pass
        total_products_sold = sales_query.aggregate(total=Sum('quantity'))['total']
        total_revenue = sales_query.aggregate(revenue=Sum('sale_price'))['revenue']
        top_customers = (
            sales_query.values('order__customer__name', 'order__customer__billing_address')
            .annotate(total_spent=Sum('sale_price'))
            .order_by('-total_spent')[:5]
        )
        top_products = (
            sales_query.values('order__product__name')
            .annotate(total_sold=Sum('quantity'))
            .order_by('-total_sold')[:5]
        )
        top_categories = (
            sales_query.values('order__product__category')
            .annotate(total_sold=Sum('quantity'))
            .order_by('-total_sold')[:5]
        )
        monthly_sales = (
            sales_query.annotate(month=TruncMonth('sale_date'))
            .values('month')
            .annotate(total_sold=Sum('quantity'))
            .order_by('month')
        )
        data = {
            'total_products_sold': total_products_sold,
            'total_revenue': total_revenue,
            'top_customers': list(top_customers),
            'top_products': list(top_products),
            'top_categories': list(top_categories),
            'monthly_sales': list(monthly_sales),
        }
        return Response(data)
