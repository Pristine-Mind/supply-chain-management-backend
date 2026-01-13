from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from producer.models import Product

from .models import CustomerRFMSegment, WeeklyBusinessHealthDigest
from .serializers import (
    CustomerRFMSegmentSerializer,
    WeeklyBusinessHealthDigestSerializer,
)


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

        out_of_stock_products = Product.objects.filter(user__user_profile__shop_id=shop_id, stock=0, avg_daily_demand__gt=0)

        lost_sales_revenue = 0
        for p in out_of_stock_products:
            lost_days = p.lead_time_days or 7
            lost_sales_revenue += p.avg_daily_demand * lost_days * float(p.price)

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
    serializer_class = CustomerRFMSegmentSerializer

    def get_queryset(self):
        return self.queryset.filter(shop_owner=self.request.user)


class LostSalesView(APIView):
    """
    Detailed report on lost sales due to stockouts.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        shop_id = getattr(user.user_profile, "shop_id", None)

        if not shop_id:
            return Response({"error": "Shop ID not found"}, status=status.HTTP_404_NOT_FOUND)

        out_of_stock = Product.objects.filter(user__user_profile__shop_id=shop_id, stock=0, avg_daily_demand__gt=0)

        results = []
        total_lost_revenue = 0

        for p in out_of_stock:
            lost_days = p.lead_time_days or 7
            potential_lost_units = p.avg_daily_demand * lost_days
            potential_lost_rev = potential_lost_units * float(p.price)

            results.append(
                {
                    "product_id": p.id,
                    "product_name": p.name,
                    "avg_daily_demand": p.avg_daily_demand,
                    "lead_time_days": lost_days,
                    "potential_units_lost": round(potential_lost_units, 2),
                    "potential_revenue_lost": round(potential_lost_rev, 2),
                }
            )
            total_lost_revenue += potential_lost_rev

        return Response({"detailed_lost_sales": results, "total_potential_lost_revenue": round(total_lost_revenue, 2)})


class WeeklyDigestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Access to generated weekly business digests.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = WeeklyBusinessHealthDigestSerializer
    queryset = WeeklyBusinessHealthDigest.objects.all()

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
