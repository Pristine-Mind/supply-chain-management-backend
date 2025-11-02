"""
Management command to clean up expired login attempts.
This should be run periodically via cron job or Django-Crontab.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from user.models import LoginAttempt


class Command(BaseCommand):
    help = "Clean up expired login attempts from the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes", type=int, default=15, help="Clear login attempts older than this many minutes (default: 15)"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Show how many records would be deleted without actually deleting them"
        )

    def handle(self, *args, **options):
        minutes = options["minutes"]
        dry_run = options["dry_run"]

        time_threshold = timezone.now() - timedelta(minutes=minutes)

        # Get the query set of expired attempts
        expired_attempts = LoginAttempt.objects.filter(timestamp__lt=time_threshold)
        count = expired_attempts.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: Would delete {count} login attempts older than {minutes} minutes")
            )

            # Show some statistics
            if count > 0:
                oldest_attempt = expired_attempts.order_by("timestamp").first()
                newest_attempt = expired_attempts.order_by("-timestamp").first()

                self.stdout.write(f"Oldest attempt: {oldest_attempt.timestamp}")
                self.stdout.write(f"Newest attempt to be deleted: {newest_attempt.timestamp}")

                # Show breakdown by type
                failed_count = expired_attempts.filter(attempt_type="login_failed").count()
                locked_count = expired_attempts.filter(attempt_type="account_locked").count()
                blocked_count = expired_attempts.filter(attempt_type="ip_blocked").count()

                self.stdout.write(f"Failed login attempts: {failed_count}")
                self.stdout.write(f"Account locked attempts: {locked_count}")
                self.stdout.write(f"IP blocked attempts: {blocked_count}")
        else:
            if count == 0:
                self.stdout.write(self.style.SUCCESS(f"No login attempts older than {minutes} minutes found"))
            else:
                # Actually delete the records
                deleted_count = LoginAttempt.clear_expired_attempts(minutes=minutes)

                self.stdout.write(
                    self.style.SUCCESS(f"Successfully deleted {deleted_count} login attempts older than {minutes} minutes")
                )

        # Show current statistics
        total_attempts = LoginAttempt.objects.count()
        recent_attempts = LoginAttempt.objects.filter(timestamp__gte=timezone.now() - timedelta(minutes=minutes)).count()

        self.stdout.write(f"\nCurrent statistics:")
        self.stdout.write(f"Total login attempts in database: {total_attempts}")
        self.stdout.write(f"Recent attempts (last {minutes} minutes): {recent_attempts}")

        # Show IP addresses with the most attempts in the last hour
        hour_ago = timezone.now() - timedelta(hours=1)
        top_ips = (
            LoginAttempt.objects.filter(timestamp__gte=hour_ago)
            .values("ip_address")
            .annotate(attempt_count=Count("id"))
            .order_by("-attempt_count")[:5]
        )

        if top_ips:
            self.stdout.write(f"\nTop IP addresses (last hour):")
            for ip_data in top_ips:
                self.stdout.write(f"  {ip_data['ip_address']}: {ip_data['attempt_count']} attempts")
