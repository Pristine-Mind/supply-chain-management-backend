"""
Management command to clean up expired login attempts.
This command should be run periodically via cron or celery tasks.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from user.models import LoginAttempt


class Command(BaseCommand):
    help = "Clean up expired login attempts to prevent database bloat"

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes", type=int, default=15, help="Delete login attempts older than this many minutes (default: 15)"
        )
        parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
        parser.add_argument("--verbose", action="store_true", help="Show detailed output")

    def handle(self, *args, **options):
        minutes = options["minutes"]
        dry_run = options["dry_run"]
        verbose = options["verbose"]

        time_threshold = timezone.now() - timedelta(minutes=minutes)

        # Count attempts to be deleted
        expired_attempts = LoginAttempt.objects.filter(timestamp__lt=time_threshold)
        count = expired_attempts.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS(f"No login attempts older than {minutes} minutes found."))
            return

        if verbose:
            self.stdout.write(f"Found {count} login attempts older than {minutes} minutes.")

            # Show breakdown by attempt type
            for attempt_type, display_name in LoginAttempt.ATTEMPT_TYPE_CHOICES:
                type_count = expired_attempts.filter(attempt_type=attempt_type).count()
                if type_count > 0:
                    self.stdout.write(f"  - {display_name}: {type_count}")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN: Would delete {count} expired login attempts"))
        else:
            # Perform the deletion
            deleted_count = LoginAttempt.clear_expired_attempts(minutes=minutes)

            self.stdout.write(self.style.SUCCESS(f"Successfully deleted {deleted_count} expired login attempts"))

            if verbose:
                # Show current statistics
                total_remaining = LoginAttempt.objects.count()
                recent_failed = LoginAttempt.objects.filter(
                    timestamp__gte=time_threshold, attempt_type="login_failed"
                ).count()

                self.stdout.write(f"Current statistics:")
                self.stdout.write(f"  - Total login attempts: {total_remaining}")
                self.stdout.write(f"  - Recent failed attempts: {recent_failed}")
