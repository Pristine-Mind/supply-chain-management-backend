from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from external_delivery.models import (
    ExternalBusiness,
    ExternalBusinessStatus,
    ExternalDelivery,
    ExternalDeliveryStatus,
)


class Command(BaseCommand):
    help = "Generate reports for external delivery system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            type=str,
            choices=["daily", "weekly", "monthly", "business"],
            default="daily",
            help="Type of report to generate",
        )

        parser.add_argument("--business-id", type=int, help="Specific business ID for business report")

        parser.add_argument("--date", type=str, help="Date for report (YYYY-MM-DD format)")

        parser.add_argument(
            "--format", type=str, choices=["json", "csv", "console"], default="console", help="Output format"
        )

    def handle(self, *args, **options):
        report_type = options["type"]

        if report_type == "daily":
            self.generate_daily_report(options)
        elif report_type == "weekly":
            self.generate_weekly_report(options)
        elif report_type == "monthly":
            self.generate_monthly_report(options)
        elif report_type == "business":
            self.generate_business_report(options)

    def generate_daily_report(self, options):
        """Generate daily report"""
        if options["date"]:
            from datetime import datetime

            report_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
        else:
            report_date = timezone.now().date()

        # Get daily stats
        deliveries = ExternalDelivery.objects.filter(created_at__date=report_date)

        total_deliveries = deliveries.count()
        successful = deliveries.filter(status=ExternalDeliveryStatus.DELIVERED).count()
        failed = deliveries.filter(status=ExternalDeliveryStatus.FAILED).count()
        pending = deliveries.filter(
            status__in=[
                ExternalDeliveryStatus.PENDING,
                ExternalDeliveryStatus.ACCEPTED,
                ExternalDeliveryStatus.PICKED_UP,
                ExternalDeliveryStatus.IN_TRANSIT,
            ]
        ).count()

        # Revenue calculation
        total_revenue = sum(delivery.platform_commission or 0 for delivery in deliveries if delivery.platform_commission)

        # Business breakdown
        business_stats = {}
        for delivery in deliveries:
            business_name = delivery.external_business.business_name
            if business_name not in business_stats:
                business_stats[business_name] = {"total": 0, "successful": 0, "failed": 0, "revenue": 0}

            business_stats[business_name]["total"] += 1
            if delivery.status == ExternalDeliveryStatus.DELIVERED:
                business_stats[business_name]["successful"] += 1
            elif delivery.status == ExternalDeliveryStatus.FAILED:
                business_stats[business_name]["failed"] += 1

            if delivery.platform_commission:
                business_stats[business_name]["revenue"] += float(delivery.platform_commission)

        # Output report
        if options["format"] == "console":
            self.stdout.write(f"\n=== DAILY REPORT for {report_date} ===")
            self.stdout.write(f"Total Deliveries: {total_deliveries}")
            self.stdout.write(
                f"Successful: {successful} ({successful/total_deliveries*100:.1f}% if total_deliveries else 0%)"
            )
            self.stdout.write(f"Failed: {failed} ({failed/total_deliveries*100:.1f}% if total_deliveries else 0%)")
            self.stdout.write(f"Pending: {pending} ({pending/total_deliveries*100:.1f}% if total_deliveries else 0%)")
            self.stdout.write(f"Total Revenue: NPR {total_revenue:.2f}")

            self.stdout.write(f"\n--- Business Breakdown ---")
            for business, stats in business_stats.items():
                self.stdout.write(f"{business}: {stats['total']} deliveries, " f"NPR {stats['revenue']:.2f} revenue")

        elif options["format"] == "json":
            import json

            report_data = {
                "date": report_date.isoformat(),
                "total_deliveries": total_deliveries,
                "successful_deliveries": successful,
                "failed_deliveries": failed,
                "pending_deliveries": pending,
                "total_revenue": float(total_revenue),
                "business_breakdown": business_stats,
            }
            self.stdout.write(json.dumps(report_data, indent=2))

    def generate_business_report(self, options):
        """Generate report for specific business"""
        business_id = options["business_id"]
        if not business_id:
            self.stdout.write(self.style.ERROR("Business ID is required for business report"))
            return

        try:
            business = ExternalBusiness.objects.get(id=business_id)
        except ExternalBusiness.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Business with ID {business_id} not found"))
            return

        # Get business stats
        deliveries = business.external_deliveries.all()
        total_deliveries = deliveries.count()

        if total_deliveries == 0:
            self.stdout.write(f"No deliveries found for {business.business_name}")
            return

        # Status breakdown
        status_counts = {}
        for status in ExternalDeliveryStatus:
            count = deliveries.filter(status=status.value).count()
            if count > 0:
                status_counts[status.label] = count

        # Monthly stats for last 6 months
        monthly_stats = []
        for i in range(6):
            month_start = timezone.now().replace(day=1) - timedelta(days=30 * i)
            month_deliveries = deliveries.filter(created_at__year=month_start.year, created_at__month=month_start.month)

            monthly_stats.append(
                {
                    "month": month_start.strftime("%Y-%m"),
                    "deliveries": month_deliveries.count(),
                    "revenue": sum(d.platform_commission or 0 for d in month_deliveries if d.platform_commission),
                }
            )

        # Output business report
        self.stdout.write(f"\n=== BUSINESS REPORT for {business.business_name} ===")
        self.stdout.write(f"Business Email: {business.business_email}")
        self.stdout.write(f"Status: {business.get_status_display()}")
        self.stdout.write(f"Plan: {business.get_plan_display()}")
        self.stdout.write(f"Total Deliveries: {total_deliveries}")

        self.stdout.write(f"\n--- Status Breakdown ---")
        for status_name, count in status_counts.items():
            percentage = count / total_deliveries * 100
            self.stdout.write(f"{status_name}: {count} ({percentage:.1f}%)")

        self.stdout.write(f"\n--- Monthly Trends (Last 6 Months) ---")
        for month_data in reversed(monthly_stats):
            self.stdout.write(
                f"{month_data['month']}: {month_data['deliveries']} deliveries, " f"NPR {month_data['revenue']:.2f} revenue"
            )

    def generate_weekly_report(self, options):
        """Generate weekly report"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=7)

        deliveries = ExternalDelivery.objects.filter(created_at__date__range=[start_date, end_date])

        self.stdout.write(f"\n=== WEEKLY REPORT ({start_date} to {end_date}) ===")

        # Daily breakdown
        daily_stats = {}
        for i in range(7):
            day = start_date + timedelta(days=i)
            day_deliveries = deliveries.filter(created_at__date=day)
            daily_stats[day] = {
                "total": day_deliveries.count(),
                "successful": day_deliveries.filter(status=ExternalDeliveryStatus.DELIVERED).count(),
                "revenue": sum(d.platform_commission or 0 for d in day_deliveries if d.platform_commission),
            }

        for day, stats in daily_stats.items():
            self.stdout.write(
                f"{day}: {stats['total']} deliveries, "
                f"{stats['successful']} successful, "
                f"NPR {stats['revenue']:.2f} revenue"
            )

    def generate_monthly_report(self, options):
        """Generate monthly report"""
        now = timezone.now()
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        deliveries = ExternalDelivery.objects.filter(created_at__gte=start_date)

        self.stdout.write(f"\n=== MONTHLY REPORT ({start_date.strftime('%B %Y')}) ===")

        # Overall stats
        total_deliveries = deliveries.count()
        total_businesses = ExternalBusiness.objects.filter(status=ExternalBusinessStatus.APPROVED).count()

        # Top performing businesses
        business_performance = {}
        for delivery in deliveries:
            business_name = delivery.external_business.business_name
            if business_name not in business_performance:
                business_performance[business_name] = {"deliveries": 0, "revenue": 0, "success_rate": 0}

            business_performance[business_name]["deliveries"] += 1
            if delivery.platform_commission:
                business_performance[business_name]["revenue"] += float(delivery.platform_commission)

        # Calculate success rates
        for business_name in business_performance:
            business_deliveries = deliveries.filter(external_business__business_name=business_name)
            successful = business_deliveries.filter(status=ExternalDeliveryStatus.DELIVERED).count()
            total = business_deliveries.count()
            business_performance[business_name]["success_rate"] = successful / total * 100 if total > 0 else 0

        # Sort by revenue
        top_businesses = sorted(business_performance.items(), key=lambda x: x[1]["revenue"], reverse=True)[:5]

        self.stdout.write(f"Total Deliveries: {total_deliveries}")
        self.stdout.write(f"Active Businesses: {total_businesses}")

        self.stdout.write(f"\n--- Top 5 Businesses by Revenue ---")
        for i, (business_name, stats) in enumerate(top_businesses, 1):
            self.stdout.write(
                f"{i}. {business_name}: {stats['deliveries']} deliveries, "
                f"NPR {stats['revenue']:.2f} revenue, "
                f"{stats['success_rate']:.1f}% success rate"
            )
