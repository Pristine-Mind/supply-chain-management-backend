import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from transport.models import (
    Delivery,
    DeliveryPriority,
    MarketplaceSale,
    TransportStatus,
)


class Command(BaseCommand):
    help = "Create sample delivery records for testing"

    def __init__(self):
        super().__init__()
        self.fake = Faker()

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=10, help="Number of sample deliveries to create")
        parser.add_argument("--marketplace-sale-ids", type=str, help="Comma-separated list of marketplace sale IDs to use")
        parser.add_argument(
            "--priority-distribution",
            type=str,
            default="70,25,5",
            help="Priority distribution as percentages: normal,high,low (default: 70,25,5)",
        )
        parser.add_argument(
            "--location-bounds",
            type=str,
            default="27.6000,27.8000,85.2000,85.4000",
            help="Location bounds: min_lat,max_lat,min_lng,max_lng (default: Kathmandu area)",
        )

    def handle(self, *args, **options):
        count = options["count"]

        try:
            normal_pct, high_pct, low_pct = map(int, options["priority_distribution"].split(","))
            if normal_pct + high_pct + low_pct != 100:
                raise ValueError("Priority percentages must sum to 100")
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f"Invalid priority distribution: {e}"))
            return

        try:
            min_lat, max_lat, min_lng, max_lng = map(float, options["location_bounds"].split(","))
        except ValueError:
            self.stdout.write(self.style.ERROR("Invalid location bounds format"))
            return

        if options["marketplace_sale_ids"]:
            sale_ids = [int(id.strip()) for id in options["marketplace_sale_ids"].split(",")]
            marketplace_sales = MarketplaceSale.objects.filter(id__in=sale_ids)
            if marketplace_sales.count() != len(sale_ids):
                found_ids = list(marketplace_sales.values_list("id", flat=True))
                missing_ids = set(sale_ids) - set(found_ids)
                self.stdout.write(self.style.ERROR(f"MarketplaceSale IDs not found: {missing_ids}"))
                return
        else:
            marketplace_sales = MarketplaceSale.objects.all()
            if marketplace_sales.count() < count:
                self.stdout.write(
                    self.style.ERROR(f"Not enough MarketplaceSale records. Found {marketplace_sales.count()}, need {count}")
                )
                return

        sample_addresses = [
            "Thamel, Kathmandu",
            "Durbar Marg, Kathmandu",
            "New Road, Kathmandu",
            "Putalisadak, Kathmandu",
            "Baneshwor, Kathmandu",
            "Maharajgunj, Kathmandu",
            "Lazimpat, Kathmandu",
            "Dillibazar, Kathmandu",
            "Naxal, Kathmandu",
            "Tangal, Kathmandu",
            "Sinamangal, Kathmandu",
            "Pulchowk, Lalitpur",
            "Jawalakhel, Lalitpur",
            "Kupondole, Lalitpur",
            "Sanepa, Lalitpur",
        ]

        deliveries_created = 0
        errors = 0

        with transaction.atomic():
            for i in range(count):
                try:
                    if options["marketplace_sale_ids"]:
                        marketplace_sale = marketplace_sales[i % len(marketplace_sales)]
                    else:
                        marketplace_sale = random.choice(marketplace_sales)

                    if hasattr(marketplace_sale, "delivery_details"):
                        continue

                    rand_priority = random.randint(1, 100)
                    if rand_priority <= normal_pct:
                        priority = DeliveryPriority.NORMAL
                    elif rand_priority <= normal_pct + high_pct:
                        priority = DeliveryPriority.HIGH
                    else:
                        priority = DeliveryPriority.LOW

                    pickup_lat = random.uniform(min_lat, max_lat)
                    pickup_lng = random.uniform(min_lng, max_lng)
                    delivery_lat = random.uniform(min_lat, max_lat)
                    delivery_lng = random.uniform(min_lng, max_lng)

                    distance_km = abs(pickup_lat - delivery_lat) * 111 + abs(pickup_lng - delivery_lng) * 85
                    distance_km = round(distance_km, 2)

                    pickup_hours = random.randint(1, 72)
                    delivery_hours = pickup_hours + random.randint(4, 48)

                    now = timezone.now()
                    pickup_date = now + timedelta(hours=pickup_hours)
                    delivery_date = now + timedelta(hours=delivery_hours)

                    Delivery.objects.create(
                        marketplace_sale=marketplace_sale,
                        pickup_address=random.choice(sample_addresses),
                        pickup_latitude=Decimal(str(pickup_lat)),
                        pickup_longitude=Decimal(str(pickup_lng)),
                        pickup_contact_name=self.fake.name(),
                        pickup_contact_phone=f"+977-{random.randint(9800000000, 9899999999)}",
                        delivery_address=random.choice(sample_addresses),
                        delivery_latitude=Decimal(str(delivery_lat)),
                        delivery_longitude=Decimal(str(delivery_lng)),
                        delivery_contact_name=self.fake.name(),
                        delivery_contact_phone=f"+977-{random.randint(9800000000, 9899999999)}",
                        package_weight=Decimal(str(round(random.uniform(0.5, 50.0), 2))),
                        package_dimensions=f"{random.randint(10, 100)}x{random.randint(10, 100)}x{random.randint(5, 50)}",
                        special_instructions=self.fake.sentence() if random.random() < 0.3 else "",
                        priority=priority,
                        delivery_fee=Decimal(str(round(random.uniform(100, 2000), 2))),
                        distance_km=Decimal(str(distance_km)),
                        requested_pickup_date=pickup_date,
                        requested_delivery_date=delivery_date,
                        status=TransportStatus.AVAILABLE,
                    )

                    deliveries_created += 1

                    if deliveries_created % 10 == 0:
                        self.stdout.write(f"Created {deliveries_created} deliveries...")

                except Exception as e:
                    errors += 1
                    self.stdout.write(self.style.ERROR(f"Error creating delivery {i+1}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"Successfully created {deliveries_created} sample deliveries"))

        if errors > 0:
            self.stdout.write(self.style.WARNING(f"Encountered {errors} errors during creation"))
