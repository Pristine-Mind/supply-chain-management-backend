from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from transport.models import (
    Delivery,
    MarketplaceSale,
    TransportStatus,
)


class Command(BaseCommand):
    help = "Create a single delivery record"

    def add_arguments(self, parser):
        parser.add_argument("--marketplace-sale-id", type=int, required=True, help="ID of the marketplace sale")
        parser.add_argument("--pickup-address", type=str, required=True, help="Pickup address")
        parser.add_argument("--delivery-address", type=str, required=True, help="Delivery address")
        parser.add_argument("--pickup-contact-name", type=str, required=True, help="Pickup contact name")
        parser.add_argument("--pickup-contact-phone", type=str, required=True, help="Pickup contact phone")
        parser.add_argument("--delivery-contact-name", type=str, required=True, help="Delivery contact name")
        parser.add_argument("--delivery-contact-phone", type=str, required=True, help="Delivery contact phone")
        parser.add_argument("--package-weight", type=float, required=True, help="Package weight in kg")
        parser.add_argument("--delivery-fee", type=float, required=True, help="Delivery fee amount")

        parser.add_argument("--pickup-lat", type=float, help="Pickup latitude")
        parser.add_argument("--pickup-lng", type=float, help="Pickup longitude")
        parser.add_argument("--delivery-lat", type=float, help="Delivery latitude")
        parser.add_argument("--delivery-lng", type=float, help="Delivery longitude")
        parser.add_argument("--package-dimensions", type=str, default="", help="Package dimensions (LxWxH in cm)")
        parser.add_argument("--special-instructions", type=str, default="", help="Special delivery instructions")
        parser.add_argument("--priority", choices=["LOW", "NORMAL", "HIGH"], default="NORMAL", help="Delivery priority")
        parser.add_argument("--distance-km", type=float, help="Distance in kilometers")
        parser.add_argument("--pickup-hours", type=int, default=24, help="Hours from now for pickup (default: 24)")
        parser.add_argument("--delivery-hours", type=int, default=48, help="Hours from now for delivery (default: 48)")

    def handle(self, *args, **options):
        try:
            try:
                marketplace_sale = MarketplaceSale.objects.get(id=options["marketplace_sale_id"])
            except MarketplaceSale.DoesNotExist:
                raise CommandError(f"MarketplaceSale with ID {options['marketplace_sale_id']} does not exist")
            if hasattr(marketplace_sale, "delivery_details"):
                raise CommandError(f"Delivery already exists for MarketplaceSale ID {options['marketplace_sale_id']}")

            now = timezone.now()
            pickup_date = now + timedelta(hours=options["pickup_hours"])
            delivery_date = now + timedelta(hours=options["delivery_hours"])
            with transaction.atomic():
                delivery = Delivery.objects.create(
                    marketplace_sale=marketplace_sale,
                    pickup_address=options["pickup_address"],
                    pickup_latitude=options.get("pickup_lat"),
                    pickup_longitude=options.get("pickup_lng"),
                    pickup_contact_name=options["pickup_contact_name"],
                    pickup_contact_phone=options["pickup_contact_phone"],
                    delivery_address=options["delivery_address"],
                    delivery_latitude=options.get("delivery_lat"),
                    delivery_longitude=options.get("delivery_lng"),
                    delivery_contact_name=options["delivery_contact_name"],
                    delivery_contact_phone=options["delivery_contact_phone"],
                    package_weight=Decimal(str(options["package_weight"])),
                    package_dimensions=options["package_dimensions"],
                    special_instructions=options["special_instructions"],
                    priority=options["priority"],
                    delivery_fee=Decimal(str(options["delivery_fee"])),
                    distance_km=Decimal(str(options["distance_km"])) if options.get("distance_km") else None,
                    requested_pickup_date=pickup_date,
                    requested_delivery_date=delivery_date,
                    status=TransportStatus.AVAILABLE,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully created delivery with ID: {delivery.delivery_id}\n"
                        f"Pickup scheduled for: {pickup_date}\n"
                        f"Delivery scheduled for: {delivery_date}"
                    )
                )

        except Exception as e:
            raise CommandError(f"Error creating delivery: {str(e)}")
