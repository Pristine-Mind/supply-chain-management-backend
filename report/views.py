from datetime import timedelta

from django.db.models import Count, F, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from producer.models import Product, Sale

from .models import CustomerRFMSegment, DailySalesReport, WeeklyBusinessHealthDigest


class CommandPaletteView(APIView):
    """
    OS-style Command Palette / Spotlight Search.
    Returns a list of actions the user can take based on their role.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = getattr(user.user_profile, "role", None)
        role_code = role.code if role else "general_user"

        commands = [
            {"title": "Search Products", "command": "search_products", "shortcut": "Ctrl+P", "category": "General"},
            {"title": "View Dashboard", "command": "view_dashboard", "shortcut": "Home", "category": "General"},
        ]

        if role_code in ["business_owner", "admin"]:
            commands.extend(
                [
                    {"title": "Export Sales Report", "command": "export_sales", "shortcut": "Ctrl+E", "category": "Reports"},
                    {
                        "title": "Inventory Audit",
                        "command": "audit_inventory",
                        "shortcut": "Ctrl+I",
                        "category": "Warehouse",
                    },
                    {"title": "Calculate EOQ", "command": "recalc_eoq", "shortcut": "Shift+R", "category": "System"},
                ]
            )

        return Response(commands)


class ERPHealthDashboardView(APIView):
    """
    Consolidated Health Dashboard for the ERP.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        shop_id = getattr(user.user_profile, "shop_id", None)

        if not shop_id:
            return Response({"error": "Shop ID not found"}, status=status.HTTP_404_NOT_FOUND)

        # 1. Lost Sales Calculation (Predictive)
        # We estimate lost sales as: (Avg Daily Demand * Days Out of Stock)
        out_of_stock_products = Product.objects.filter(user__user_profile__shop_id=shop_id, stock=0, avg_daily_demand__gt=0)

        lost_sales_revenue = 0
        for p in out_of_stock_products:
            # Edge Case: Dynamic Lost Sales based on lead time
            # If lead_time is 14 days, we lose 14 days of average demand
            lost_days = p.lead_time_days or 7
            lost_sales_revenue += p.avg_daily_demand * lost_days * float(p.price)

        # 2. Segment Distribution
        segments = CustomerRFMSegment.objects.filter(shop_owner=user).values("segment").annotate(count=Count("id"))

        return Response(
            {
                "lost_sales_estimated_7d": round(lost_sales_revenue, 2),
                "customer_segments": {s["segment"]: s["count"] for s in segments},
                "system_status": "Healthy",
                "last_recitation": timezone.now(),
            }
        )


class RFMReportViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = CustomerRFMSegment.objects.all()

    def get_queryset(self):
        return self.queryset.filter(shop_owner=self.request.user)
