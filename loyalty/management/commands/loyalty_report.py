import json

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from loyalty.models import LoyaltyTier, LoyaltyTransaction, UserLoyalty


class Command(BaseCommand):
    help = "Generate loyalty program statistics report"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to include in report",
        )
        parser.add_argument(
            "--format",
            type=str,
            default="text",
            choices=["text", "json"],
            help="Output format",
        )

    def handle(self, *args, **options):
        days = options["days"]
        output_format = options["format"]

        start_date = timezone.now() - timezone.timedelta(days=days)

        # Gather statistics
        stats = {
            "period_days": days,
            "start_date": start_date.isoformat(),
            "end_date": timezone.now().isoformat(),
        }

        # User statistics
        stats["users"] = {
            "total": UserLoyalty.objects.count(),
            "active": UserLoyalty.objects.filter(is_active=True).count(),
            "with_points": UserLoyalty.objects.filter(is_active=True, points__gt=0).count(),
        }

        # Points statistics
        points_data = UserLoyalty.objects.aggregate(total_outstanding=Sum("points"), total_lifetime=Sum("lifetime_points"))
        stats["points"] = {
            "outstanding": points_data["total_outstanding"] or 0,
            "lifetime_issued": points_data["total_lifetime"] or 0,
        }

        # Transaction statistics for period
        period_transactions = LoyaltyTransaction.objects.filter(created_at__gte=start_date)

        stats["transactions"] = {
            "total": period_transactions.count(),
            "earned": period_transactions.filter(transaction_type="earn").aggregate(Sum("points"))["points__sum"] or 0,
            "redeemed": abs(
                period_transactions.filter(transaction_type="redeem").aggregate(Sum("points"))["points__sum"] or 0
            ),
            "expired": abs(
                period_transactions.filter(transaction_type="expire").aggregate(Sum("points"))["points__sum"] or 0
            ),
        }

        # Tier distribution
        stats["tier_distribution"] = {}
        for tier in LoyaltyTier.objects.filter(is_active=True):
            count = UserLoyalty.objects.filter(tier=tier, is_active=True).count()
            stats["tier_distribution"][tier.name] = count

        no_tier = UserLoyalty.objects.filter(tier__isnull=True, is_active=True).count()
        if no_tier > 0:
            stats["tier_distribution"]["No Tier"] = no_tier

        # Output
        if output_format == "json":
            self.stdout.write(json.dumps(stats, indent=2))
        else:
            self.print_text_report(stats)

    def print_text_report(self, stats):
        """Print report in text format."""
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("LOYALTY PROGRAM REPORT"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"Period: Last {stats['period_days']} days")
        self.stdout.write("")

        self.stdout.write(self.style.HTTP_INFO("USER STATISTICS"))
        self.stdout.write(f"  Total Users:        {stats['users']['total']}")
        self.stdout.write(f"  Active Users:       {stats['users']['active']}")
        self.stdout.write(f"  Users with Points:  {stats['users']['with_points']}")
        self.stdout.write("")

        self.stdout.write(self.style.HTTP_INFO("POINTS STATISTICS"))
        self.stdout.write(f"  Outstanding:        {stats['points']['outstanding']:,}")
        self.stdout.write(f"  Lifetime Issued:    {stats['points']['lifetime_issued']:,}")
        self.stdout.write("")

        self.stdout.write(self.style.HTTP_INFO("TRANSACTIONS (Period)"))
        self.stdout.write(f"  Total:              {stats['transactions']['total']}")
        self.stdout.write(f"  Points Earned:      {stats['transactions']['earned']:,}")
        self.stdout.write(f"  Points Redeemed:    {stats['transactions']['redeemed']:,}")
        self.stdout.write(f"  Points Expired:     {stats['transactions']['expired']:,}")
        self.stdout.write("")

        self.stdout.write(self.style.HTTP_INFO("TIER DISTRIBUTION"))
        for tier, count in stats["tier_distribution"].items():
            self.stdout.write(f"  {tier:20s} {count}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
