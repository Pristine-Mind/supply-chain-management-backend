import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from transport.models import Transporter, VehicleType


class Command(BaseCommand):
    help = "Create sample transporters for testing"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=10, help="Number of transporters to create")

    def handle(self, *args, **options):
        count = options["count"]

        vehicle_types = [choice[0] for choice in VehicleType.choices]

        for i in range(count):
            username = f"transporter_{i+1}"

            # Skip if user already exists
            if User.objects.filter(username=username).exists():
                continue

            # Create user
            user = User.objects.create_user(
                username=username,
                email=f"{username}@example.com",
                password="password123",
                first_name="Transporter",
                last_name=f"{i+1}",
            )

            # Create transporter profile
            Transporter.objects.create(
                user=user,
                license_number=f"LIC{1000 + i}",
                phone=f"+1555010{i:04d}",
                vehicle_type=random.choice(vehicle_types),
                vehicle_number=f"VEH{100 + i}",
                vehicle_capacity=random.uniform(50, 500),
                current_latitude=random.uniform(40.0, 41.0),
                current_longitude=random.uniform(-74.0, -73.0),
                is_available=random.choice([True, False]),
                is_verified=random.choice([True, False]),
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully created {count} sample transporters"))
