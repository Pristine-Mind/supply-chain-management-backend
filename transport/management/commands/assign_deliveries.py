from django.core.management.base import BaseCommand
from django.db import transaction

from transport.models import Delivery, DeliveryPriority, Transporter, TransportStatus
from transport.utils import calculate_distance


class Command(BaseCommand):
    help = "Auto-assign available deliveries to suitable transporters"

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-assignments", type=int, default=50, help="Maximum number of deliveries to assign in one run"
        )
        parser.add_argument(
            "--radius-km", type=float, default=15000.0, help="Maximum radius in km to search for transporters"
        )
        parser.add_argument("--priority-only", action="store_true", help="Only assign high priority deliveries")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be assigned without making changes")

    def handle(self, *args, **options):
        max_assignments = options["max_assignments"]
        radius_km = options["radius_km"]
        priority_only = options["priority_only"]
        dry_run = options["dry_run"]

        queryset = Delivery.objects.filter(status=TransportStatus.AVAILABLE, transporter__isnull=True).select_related(
            "marketplace_sale"
        )

        if priority_only:
            queryset = queryset.filter(priority=DeliveryPriority.HIGH)

        deliveries = queryset.order_by("-priority", "requested_pickup_date")[:max_assignments]

        assignments_made = 0

        with transaction.atomic():
            for delivery in deliveries:
                available_transporters = self.find_nearby_transporters(delivery, radius_km)

                if available_transporters:
                    transporter = available_transporters[0]  # Get the closest one

                    if dry_run:
                        self.stdout.write(
                            f"Would assign Delivery {delivery.delivery_id} to {transporter.user.get_full_name()}"
                        )
                    else:
                        delivery.assign_to_transporter(transporter)
                        assignments_made += 1

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Assigned Delivery {delivery.delivery_id} to {transporter.user.get_full_name()}"
                            )
                        )

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Successfully assigned {assignments_made} deliveries"))

    def find_nearby_transporters(self, delivery, radius_km):
        """Find available transporters within radius of pickup location"""
        if not delivery.pickup_latitude or not delivery.pickup_longitude:
            return Transporter.objects.filter(is_available=True)[:1]

        available_transporters = Transporter.objects.filter(is_available=True).select_related("user")

        nearby_transporters = []
        for transporter in available_transporters:
            if hasattr(transporter, "current_latitude") and hasattr(transporter, "current_longitude"):
                if transporter.current_latitude and transporter.current_longitude:
                    distance = calculate_distance(
                        delivery.pickup_latitude,
                        delivery.pickup_longitude,
                        transporter.current_latitude,
                        transporter.current_longitude,
                    )
                    if distance <= radius_km:
                        nearby_transporters.append((transporter, distance))
        # Sort by distance
        nearby_transporters.sort(key=lambda x: x[1])
        return [t[0] for t in nearby_transporters]
