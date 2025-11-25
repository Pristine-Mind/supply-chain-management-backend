from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from external_delivery.models import ExternalDelivery
from external_delivery.tasks import retry_failed_webhooks


class Command(BaseCommand):
    help = "Retry failed webhook deliveries"

    def add_arguments(self, parser):
        parser.add_argument("--delivery-id", type=int, help="Specific delivery ID to retry webhooks for")

        parser.add_argument("--max-retries", type=int, default=3, help="Maximum number of retries (default: 3)")

        parser.add_argument("--force", action="store_true", help="Force retry even if max retries exceeded")

    def handle(self, *args, **options):
        if options["delivery_id"]:
            self.retry_delivery_webhooks(options)
        else:
            self.retry_all_failed_webhooks(options)

    def retry_delivery_webhooks(self, options):
        """Retry webhooks for a specific delivery"""
        delivery_id = options["delivery_id"]

        try:
            delivery = ExternalDelivery.objects.get(id=delivery_id)

            failed_webhooks = delivery.webhook_logs.filter(success=False)

            if options["force"]:
                failed_webhooks = failed_webhooks.all()
            else:
                max_retries = options["max_retries"]
                failed_webhooks = failed_webhooks.filter(retry_count__lt=max_retries)

            if not failed_webhooks.exists():
                self.stdout.write(self.style.WARNING(f"No failed webhooks found for delivery {delivery.tracking_number}"))
                return

            self.stdout.write(f"Found {failed_webhooks.count()} failed webhooks for delivery {delivery.tracking_number}")

            # Retry each webhook
            for webhook_log in failed_webhooks:
                self.stdout.write(f"Retrying webhook {webhook_log.id}...")

                try:
                    from external_delivery.utils import send_webhook_notification

                    result = send_webhook_notification(
                        business=webhook_log.external_business,
                        event_type=webhook_log.event_type,
                        data=webhook_log.payload,
                        webhook_url=webhook_log.webhook_url,
                        delivery=webhook_log.delivery,
                    )

                    if result.get("success"):
                        self.stdout.write(self.style.SUCCESS(f"✓ Webhook {webhook_log.id} retried successfully"))
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'✗ Webhook {webhook_log.id} failed again: {result.get("error")}')
                        )

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"✗ Error retrying webhook {webhook_log.id}: {e}"))

        except ExternalDelivery.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Delivery with ID {delivery_id} not found"))

    def retry_all_failed_webhooks(self, options):
        """Retry all failed webhooks"""
        self.stdout.write("Starting retry of all failed webhooks...")

        # Use the Celery task for efficiency
        try:
            result = retry_failed_webhooks.delay()
            self.stdout.write(self.style.SUCCESS(f"Webhook retry task started with ID: {result.id}"))

            # Wait for task completion and show status
            import time

            while not result.ready():
                self.stdout.write("Waiting for webhook retry task to complete...")
                time.sleep(2)

            if result.successful():
                self.stdout.write(self.style.SUCCESS("Webhook retry task completed successfully"))
            else:
                self.stdout.write(self.style.ERROR(f"Webhook retry task failed: {result.result}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error starting webhook retry task: {e}"))

            # Fallback to direct retry
            self.stdout.write("Falling back to direct webhook retry...")
            self.direct_webhook_retry(options)

    def direct_webhook_retry(self, options):
        """Direct webhook retry without Celery"""
        from django.utils import timezone

        from external_delivery.models import WebhookLog

        max_retries = options["max_retries"]
        now = timezone.now()

        # Get failed webhooks that need retry
        query = WebhookLog.objects.filter(success=False)

        if not options["force"]:
            query = query.filter(retry_count__lt=max_retries)

        failed_webhooks = query.filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))

        total_webhooks = failed_webhooks.count()

        if total_webhooks == 0:
            self.stdout.write("No failed webhooks to retry.")
            return

        self.stdout.write(f"Found {total_webhooks} failed webhooks to retry.")

        success_count = 0
        error_count = 0

        for webhook_log in failed_webhooks:
            try:
                from external_delivery.utils import send_webhook_notification

                result = send_webhook_notification(
                    business=webhook_log.external_business,
                    event_type=webhook_log.event_type,
                    data=webhook_log.payload,
                    webhook_url=webhook_log.webhook_url,
                    delivery=webhook_log.delivery,
                )

                if result.get("success"):
                    success_count += 1
                    self.stdout.write(f"✓ Webhook {webhook_log.id} retried successfully")
                else:
                    error_count += 1
                    self.stdout.write(f'✗ Webhook {webhook_log.id} failed: {result.get("error")}')

            except Exception as e:
                error_count += 1
                self.stdout.write(f"✗ Error retrying webhook {webhook_log.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f"\nRetry completed: {success_count} successful, {error_count} failed"))
