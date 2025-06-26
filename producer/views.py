from datetime import timedelta, datetime

from django.db.models.query import QuerySet
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required

from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from rest_framework.decorators import api_view, permission_classes

from django.db.models import Sum, Q, Count, F, FloatField, ExpressionWrapper
from django.utils import timezone
from django.db.models.functions import TruncMonth
import logging

from .models import (
    Producer,
    Customer,
    Product,
    Order,
    Sale,
    StockList,
    MarketplaceProduct,
    City,
    LedgerEntry,
    AuditLog,
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
    MarketplaceProductSerializer,
    CitySerializer,
    LedgerEntrySerializer,
    AuditLogSerializer,
    ProcurementRequestSerializer,
    ProcurementResponseSerializer,
    SalesRequestSerializer,
    SalesResponseSerializer,
    ReconciliationResponseSerializer,
)
from .filters import (
    SaleFilter,
    ProducerFilter,
    CustomerFilter,
    ProductFilter,
    MarketplaceProductFilter,
)
from .utils import export_queryset_to_excel
from user.models import UserProfile
from .supply_chain import SupplyChainService

logger = logging.getLogger(__name__)


class ProducerViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing producer instances.
    """

    queryset = Producer.objects.all().order_by("-created_at")
    serializer_class = ProducerSerializer
    filterset_class = ProducerFilter
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Producer.objects.none()

        user_profile = getattr(user, "userprofile", None)
        if user_profile:
            return Producer.objects.filter(user__userprofile__shop_id=user_profile.shop_id)
        else:
            return Producer.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        producer = serializer.save()
        return Response(self.get_serializer(producer).data, status=status.HTTP_201_CREATED)


class CustomerViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing customer instances.
    """

    queryset = Customer.objects.all().order_by("-created_at")
    serializer_class = CustomerSerializer
    filterset_class = CustomerFilter
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Customer.objects.none()

        user_profile = getattr(user, "userprofile", None)
        if user_profile:
            return Customer.objects.filter(user__userprofile__shop_id=user_profile.shop_id)
        else:
            return Customer.objects.none()


class ProductViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing product instances.
    """

    queryset = Product.objects.all().order_by("-created_at")
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Product.objects.none()

        user_profile = getattr(user, "userprofile", None)
        if user_profile:
            return Product.objects.filter(user__userprofile__shop_id=user_profile.shop_id)
        else:
            return Product.objects.none()

    @action(detail=False, url_path="catgeories", methods=("get",), permission_classes=[AllowAny])
    def get_category(self, request, pk=None):
        return Response(
            [
                {
                    "key": key,
                    "value": value,
                }
                for key, value in Product.ProductCategory.choices
            ]
        )


class OrderViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing order instances.
    """

    queryset = Order.objects.all().order_by("-created_at")
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Order.objects.none()

        user_profile = getattr(user, "userprofile", None)
        if user_profile:
            return Order.objects.filter(user__userprofile__shop_id=user_profile.shop_id)
        else:
            return Order.objects.none()


class SaleViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing sale instances.
    """

    queryset = Sale.objects.all().order_by("-created_at")
    serializer_class = SaleSerializer
    filterset_class = SaleFilter
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Sale.objects.none()

        user_profile = getattr(user, "userprofile", None)
        if user_profile:
            return Sale.objects.filter(user__userprofile__shop_id=user_profile.shop_id)
        else:
            return Sale.objects.none()


class DashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=401)

        user_profile = getattr(user, "userprofile", None)
        if not user_profile:
            return Response({"detail": "User profile not found"}, status=404)

        # Filter data based on the shop_id of the user's profile
        shop_id = user_profile.shop_id
        current_year = timezone.now().year

        total_products = Product.objects.filter(user__userprofile__shop_id=shop_id).distinct().count() or 0
        total_orders = Order.objects.filter(user__userprofile__shop_id=shop_id).count()
        total_sales = Sale.objects.filter(user__userprofile__shop_id=shop_id).count()
        total_customers = Customer.objects.filter(user__userprofile__shop_id=shop_id).count()
        pending_orders = Order.objects.filter(
            status__in=[Order.Status.PENDING, Order.Status.APPROVED], user__userprofile__shop_id=shop_id
        ).count()
        total_revenue = (
            Sale.objects.filter(user__userprofile__shop_id=shop_id).aggregate(total_revenue=Sum("sale_price"))[
                "total_revenue"
            ]
            or 0
        )

        # Group sales by month for the current year
        sales_trends = (
            Sale.objects.filter(user__userprofile__shop_id=shop_id, sale_date__year=current_year)
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
        try:
            user_profile = UserProfile.objects.get(user=user)
            has_access_to_marketplace = user_profile.has_access_to_marketplace
        except UserProfile.DoesNotExist:
            has_access_to_marketplace = False

        return Response(
            {
                "username": user.username,
                "id": user.id,
                "has_access_to_marketplace": has_access_to_marketplace,
            }
        )


class TopSalesCustomersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        current_year = timezone.now().year
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=401)

        user_profile = getattr(user, "userprofile", None)
        if not user_profile:
            return Response({"detail": "User profile not found"}, status=404)

        # Filter data based on the shop_id of the user's profile
        shop_id = user_profile.shop_id

        top_sales_customers = (
            Sale.objects.filter(user__userprofile__shop_id=shop_id, sale_date__year=current_year)
            .annotate(total_sales_amount=ExpressionWrapper(F("sale_price") * F("quantity"), output_field=FloatField()))
            .values("order__customer__id", "order__customer__name")
            .annotate(total_sales=Sum("total_sales_amount"), name=F("order__customer__name"), id=F("order__customer__id"))
            .order_by("-total_sales")
        )
        sales_serializer = CustomerSalesSerializer(top_sales_customers, many=True)
        return Response(data=sales_serializer.data, status=status.HTTP_200_OK)


class TopOrdersCustomersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        current_year = timezone.now().year
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=401)

        user_profile = getattr(user, "userprofile", None)
        if not user_profile:
            return Response({"detail": "User profile not found"}, status=404)

        # Filter data based on the shop_id of the user's profile
        shop_id = user_profile.shop_id

        top_orders_customers = (
            Customer.objects.filter(user__userprofile__shop_id=shop_id, order__order_date__year=current_year)
            .annotate(total_orders=Count("order"))
            .order_by("-total_orders")[:10]
        )

        orders_serializer = CustomerOrdersSerializer(top_orders_customers, many=True)
        return Response(orders_serializer.data, status=status.HTTP_200_OK)


class StockListView(viewsets.ModelViewSet):
    queryset = StockList.objects.filter(is_pushed_to_marketplace=False).distinct()
    serializer_class = StockListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return StockList.objects.none()

        user_profile = getattr(user, "userprofile", None)
        if user_profile:
            return StockList.objects.filter(user__userprofile__shop_id=user_profile.shop_id)
        else:
            return StockList.objects.none()

    @action(detail=True, methods=["post"], url_path="push-to-marketplace")
    def push_to_marketplace(self, request, pk=None):
        try:
            stock_item = self.get_object()
        except StockList.DoesNotExist:
            return Response({"error": "StockList item not found."}, status=status.HTTP_404_NOT_FOUND)

        if MarketplaceProduct.objects.filter(product=stock_item.product).exists():
            return Response(
                {"error": f"Product '{stock_item.product.name}' is already listed in the marketplace."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        MarketplaceProduct.objects.create(
            product=stock_item.product,
            listed_price=stock_item.product.price,
            is_available=True,
            bid_end_date=timezone.now() + timedelta(days=7),
        )

        # Update the product to have moved to marketplace
        stock_item.is_pushed_to_marketplace = True
        stock_item.save(update_fields=["is_pushed_to_marketplace"])
        return Response(
            {"message": f"Product '{stock_item.product.name}' has been successfully pushed to the marketplace."},
            status=status.HTTP_200_OK,
        )


class MarketplaceProductViewSet(viewsets.ModelViewSet):
    serializer_class = MarketplaceProductSerializer
    filterset_class = MarketplaceProductFilter
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            MarketplaceProduct.objects.filter(is_available=True, bid_end_date__gte=timezone.now())
            .order_by("-listed_date")
            .distinct()
        )


class MarketplaceUserRecommendedProductViewSet(viewsets.ModelViewSet):
    serializer_class = MarketplaceProductSerializer
    filterset_class = MarketplaceProductFilter
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        user = self.request.user
        try:
            UserProfile.objects.get(user=user)
            # location = user_profile.location
        except UserProfile.DoesNotExist:
            return MarketplaceProduct.objects.none()

        # if not location:
        #     return MarketplaceProduct.objects.none()

        return (
            MarketplaceProduct.objects.filter(
                is_available=True,
                # bid_end_date__gte=timezone.now(),
                # product__location=location,
            )
            .exclude(product__user=user)
            .order_by("-listed_date")
        )


class StatsAPIView(APIView):
    """
    API to provide sales statistics with optional filtering.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        filter_params = self.get_filter_params(request)
        sales_query = self.get_filtered_sales(filter_params, user)
        data = self.get_sales_statistics(sales_query)
        return Response(data, status=status.HTTP_200_OK)

    def get_filter_params(self, request):
        """Get and parse filter parameters from the request."""
        location = request.query_params.get("location")
        category = request.query_params.get("category")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        parsed_start_date, parsed_end_date = None, None
        if start_date and end_date:
            try:
                parsed_start_date = timezone.datetime.strptime(start_date, "%Y-%m-%d")
                parsed_end_date = timezone.datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        return {"location": location, "category": category, "start_date": parsed_start_date, "end_date": parsed_end_date}

    def get_filtered_sales(self, filter_params, user):
        """Filter the sales query based on the provided parameters."""
        if not user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=401)

        user_profile = getattr(user, "userprofile", None)
        if not user_profile:
            return Response({"detail": "User profile not found"}, status=404)

        # Filter data based on the shop_id of the user's profile
        shop_id = user_profile.shop_id
        sales_query = Sale.objects.filter(user__userprofile__shop_id=shop_id)

        if filter_params["location"]:
            sales_query = sales_query.filter(order__customer__city=filter_params["location"])
        if filter_params["category"]:
            sales_query = sales_query.filter(order__product__category=filter_params["category"])
        if filter_params["start_date"] and filter_params["end_date"]:
            sales_query = sales_query.filter(
                sale_date__gte=filter_params["start_date"], sale_date__lte=filter_params["end_date"]
            )

        return sales_query

    def get_sales_statistics(self, sales_query):
        """Calculate sales statistics."""
        total_products_sold = sales_query.aggregate(total=Sum("quantity"))["total"] or 0
        total_revenue = sales_query.aggregate(revenue=Sum("sale_price"))["revenue"] or 0
        top_customers = (
            sales_query.values("order__customer__name", "order__customer__billing_address")
            .annotate(total_spent=Sum("sale_price"))
            .order_by("-total_spent")[:5]
        )
        top_products = (
            sales_query.values("order__product__name").annotate(total_sold=Sum("quantity")).order_by("-total_sold")[:5]
        )
        top_categories = (
            sales_query.values("order__product__category").annotate(total_sold=Sum("quantity")).order_by("-total_sold")[:5]
        )
        monthly_sales = (
            sales_query.annotate(month=TruncMonth("sale_date"))
            .values("month")
            .annotate(total_sold=Sum("quantity"))
            .order_by("month")
        )

        return {
            "total_products_sold": total_products_sold,
            "total_revenue": total_revenue,
            "top_customers": list(top_customers),
            "top_products": list(top_products),
            "top_categories": list(top_categories),
            "monthly_sales": list(monthly_sales),
        }


class CityListView(APIView):
    def get(self, request):
        cities = City.objects.all()
        serializer = CitySerializer(cities, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def withdraw_product(request, product_id):
    try:
        product = MarketplaceProduct.objects.get(pk=product_id, product__user=request.user)

        # Ensure that the bid end date has not expired
        if product.bid_end_date and product.bid_end_date < timezone.now():
            return Response(
                {"error": "Cannot withdraw product. The bidding period has ended."}, status=status.HTTP_400_BAD_REQUEST
            )

        # Withdraw the product
        product.is_available = False
        product.save()

        return Response({"message": "Product withdrawn successfully."}, status=status.HTTP_200_OK)

    except MarketplaceProduct.DoesNotExist:
        return Response(
            {"error": "Product not found or you do not have permission to withdraw this product."},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_producers_to_excel(request):
    field_names = [
        "name",
        "contact",
        "email",
        "address",
        "registration_number",
        "created_at",
        "updated_at",
    ]
    user = request.user
    if not user.is_authenticated:
        return

    user_profile = getattr(user, "userprofile", None)
    if user_profile:
        queryset = Producer.objects.filter(user__userprofile__shop_id=user_profile.shop_id)
    wb = export_queryset_to_excel(queryset, field_names)

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = "attachment; filename=producers.xlsx"
    wb.save(response)
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_customers_to_excel(request):
    field_names = [
        "name",
        "customer_type",
        "contact",
        "email",
        "billing_address",
        "shipping_address",
        "credit_limit",
        "current_balance",
        "created_at",
        "updated_at",
    ]
    user = request.user
    if not user.is_authenticated:
        return

    user_profile = getattr(user, "userprofile", None)
    if user_profile:
        queryset = Customer.objects.filter(user__userprofile__shop_id=user_profile.shop_id)
    wb = export_queryset_to_excel(queryset, field_names)

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = "attachment; filename=customers.xlsx"
    wb.save(response)
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_products_to_excel(request):
    field_names = [
        "name",
        "get_category_display",
        "description",
        "sku",
        "price",
        "cost_price",
        "stock",
        "reorder_level",
        "is_active",
        "created_at",
        "updated_at",
    ]
    headers = [
        "Name",
        "Category",
        "Description",
        "SKU",
        "Price",
        "Cost Price",
        "Stock",
        "Reorder Level",
        "Is Active",
        "Created At",
        "Updated At",
    ]

    user = request.user
    if not user.is_authenticated:
        return

    user_profile = getattr(user, "userprofile", None)
    if user_profile:
        queryset = Product.objects.filter(user__userprofile__shop_id=user_profile.shop_id)
    wb = export_queryset_to_excel(queryset, field_names, headers)

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = "attachment; filename=products.xlsx"
    wb.save(response)
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_orders_to_excel(request):
    field_names = [
        "order_number",
        "customer_name",
        "product_name",
        "quantity",
        "get_status_display",
        "order_date",
        "delivery_date",
        "total_price",
        "created_at",
        "updated_at",
    ]
    headers = [
        "Order Number",
        "Customer",
        "Product",
        "Quantity",
        "Status",
        "Order Date",
        "Delivery Date",
        "Total Price",
        "Created At",
        "Updated At",
    ]

    user = request.user
    if not user.is_authenticated:
        return

    user_profile = getattr(user, "userprofile", None)
    if user_profile:
        queryset = Order.objects.filter(user__userprofile__shop_id=user_profile.shop_id).select_related(
            "customer", "product"
        )
    for obj in queryset:
        obj.customer_name = obj.customer.name
        obj.product_name = obj.product.name

    wb = export_queryset_to_excel(queryset, field_names, headers)

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = "attachment; filename=orders.xlsx"
    wb.save(response)
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_sales_to_excel(request):
    field_names = [
        "order_number",
        "product_name",
        "quantity",
        "sale_price",
        "sale_date",
        "get_payment_status_display",
        "payment_due_date",
        "created_at",
        "updated_at",
    ]
    headers = [
        "Order Number",
        "Product",
        "Quantity",
        "Sale Price",
        "Sale Date",
        "Payment Status",
        "Payment Due Date",
        "Created At",
        "Updated At",
    ]

    user = request.user
    if not user.is_authenticated:
        return

    user_profile = getattr(user, "userprofile", None)
    if user_profile:
        queryset = Sale.objects.filter(user__userprofile__shop_id=user_profile.shop_id).select_related("order__product")
    for obj in queryset:
        obj.order_number = obj.order.order_number
        obj.product_name = obj.order.product.name

    wb = export_queryset_to_excel(queryset, field_names, headers)

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = "attachment; filename=sales.xlsx"
    wb.save(response)
    return response


class LedgerEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LedgerEntry.objects.all()
    serializer_class = LedgerEntrySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


@api_view(["POST"])
def procurement_view(request):
    serializer = ProcurementRequestSerializer(data=request.data)
    if serializer.is_valid():
        service = SupplyChainService(request.user)
        try:
            order = service.procurement_process(
                producer_id=serializer.validated_data["producer_id"],
                product_id=serializer.validated_data["product_id"],
                quantity=serializer.validated_data["quantity"],
                unit_cost=serializer.validated_data["unit_cost"],
            )
            response_serializer = ProcurementResponseSerializer(order)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def sales_view(request):
    serializer = SalesRequestSerializer(data=request.data)
    if serializer.is_valid():
        service = SupplyChainService(request.user)
        try:
            sale = service.sales_process(
                customer_id=serializer.validated_data["customer_id"],
                product_id=serializer.validated_data["product_id"],
                quantity=serializer.validated_data["quantity"],
                selling_price=serializer.validated_data["selling_price"],
            )
            response_serializer = SalesResponseSerializer(sale)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def reconciliation_view(request):
    service = SupplyChainService(request.user)
    try:
        result = service.reconciliation_process()
        serializer = ReconciliationResponseSerializer(result)
        return Response(serializer.data)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def stats_dashboard(request):
    user = request.user

    user_date = request.query_params.get("date", None)
    if user_date:
        print(user_date)
        try:
            date = datetime.strptime(user_date, "%Y-%m-%d")
            print(f"date:{date}")
        except ValueError:
            return Response({"error": "Invalid date format. Please use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
    else:
        date = datetime.today().date()
    start_of_week = date - timedelta(days=date.weekday())
    print(f"start_of_week: {start_of_week}")
    start_of_month = date.replace(day=1)

    producer_orders = (
        Order.objects.filter(user=user, order_date__gte=start_of_week)
        .select_related("product", "customer")
        .order_by("-created_at")[:10]
    )
    customer_sales = (
        Sale.objects.filter(user=user, sale_date__gte=start_of_week)
        .select_related("order__product")
        .order_by("-created_at")[:10]
    )

    producer_transactions = [
        {
            "name": order.product.producer.name if order.product and order.product.producer else "Unknown",
            "detail": f"{order.quantity} units of {order.product.name}",
            "date": order.order_date.date(),
        }
        for order in producer_orders
    ]

    customer_transactions = [
        {
            "name": sale.order.customer.name if sale.order.customer else "Unknown",
            "detail": f"{sale.quantity} units of {sale.order.product.name}",
            "date": sale.sale_date.date(),
        }
        for sale in customer_sales
    ]

    total_products = Product.objects.filter(user=user).count()
    total_stock_value = Product.objects.filter(user=user).aggregate(total=Sum("stock") * Sum("price"))["total"] or 0

    today_sales = Sale.objects.filter(user=user, created_at__date=date).aggregate(total=Sum("sale_price"))["total"] or 0
    week_sales = (
        Sale.objects.filter(user=user, created_at__date__gte=start_of_week).aggregate(total=Sum("sale_price"))["total"] or 0
    )
    month_sales = (
        Sale.objects.filter(user=user, created_at__date__gte=start_of_month).aggregate(total=Sum("sale_price"))["total"] or 0
    )

    order_status = Order.objects.filter(user=user).values("status").annotate(count=Count("id"))

    return Response(
        {
            "producer_transactions": producer_transactions,
            "customer_transactions": customer_transactions,
            "product_summary": [
                {"title": "Total Products", "value": str(total_products)},
                {"title": "Total Stock Value", "value": f"Rs.{total_stock_value:.2f}"},
            ],
            "sales_overview": [
                {"title": "Total Sales (Today)", "value": f"Rs.{today_sales:.2f}"},
                {"title": "Total Sales (Week)", "value": f"Rs.{week_sales:.2f}"},
                {"title": "Total Sales (Month)", "value": f"Rs.{month_sales:.2f}"},
            ],
            "order_status": [
                {"title": status["status"].capitalize() + " Orders", "value": str(status["count"])}
                for status in order_status
            ],
        }
    )
