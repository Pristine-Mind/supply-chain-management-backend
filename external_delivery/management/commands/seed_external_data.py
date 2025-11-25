from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from external_delivery.models import (
    ExternalBusiness,
    ExternalBusinessPlan,
    ExternalBusinessStatus,
    ExternalDelivery,
    ExternalDeliveryStatus,
)


class Command(BaseCommand):
    help = "Seed database with sample external delivery data for testing"

    def add_arguments(self, parser):
        parser.add_argument("--businesses", type=int, default=5, help="Number of businesses to create (default: 5)")

        parser.add_argument(
            "--deliveries-per-business", type=int, default=10, help="Number of deliveries per business (default: 10)"
        )

        parser.add_argument("--clear", action="store_true", help="Clear existing external delivery data before seeding")

    def handle(self, *args, **options):
        if options["clear"]:
            self.clear_data()

        self.create_sample_data(
            num_businesses=options["businesses"], deliveries_per_business=options["deliveries_per_business"]
        )

    def clear_data(self):
        """Clear existing external delivery data"""
        self.stdout.write("Clearing existing data...")

        ExternalDelivery.objects.all().delete()
        ExternalBusiness.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("✓ Cleared existing external delivery data"))

    def create_sample_data(self, num_businesses, deliveries_per_business):
        """Create sample businesses and deliveries"""
        self.stdout.write(f"Creating {num_businesses} businesses...")

        # Sample business data
        business_templates = [
            {
                "name": "TechMart Electronics",
                "email": "api@techmart.com",
                "person": "Rajesh Sharma",
                "phone": "+977-9841234567",
                "address": "Putalisadak, Kathmandu",
                "website": "https://techmart.com",
                "plan": ExternalBusinessPlan.BUSINESS,
            },
            {
                "name": "Fashion Hub Nepal",
                "email": "integration@fashionhub.np",
                "person": "Priya Gurung",
                "phone": "+977-9856789012",
                "address": "Thamel, Kathmandu",
                "website": "https://fashionhub.np",
                "plan": ExternalBusinessPlan.STARTER,
            },
            {
                "name": "Organic Valley",
                "email": "delivery@organicvalley.com",
                "person": "Mohan Thapa",
                "phone": "+977-9812345678",
                "address": "Lalitpur, Nepal",
                "website": "https://organicvalley.com",
                "plan": ExternalBusinessPlan.FREE,
            },
            {
                "name": "Digital Solutions Pvt Ltd",
                "email": "api@digitalsolutions.com.np",
                "person": "Sita Rai",
                "phone": "+977-9823456789",
                "address": "Baneshwor, Kathmandu",
                "website": "https://digitalsolutions.com.np",
                "plan": ExternalBusinessPlan.ENTERPRISE,
            },
            {
                "name": "Nepal Books Store",
                "email": "orders@nepalbooks.com",
                "person": "Krishna Adhikari",
                "phone": "+977-9834567890",
                "address": "New Road, Kathmandu",
                "website": "https://nepalbooks.com",
                "plan": ExternalBusinessPlan.STARTER,
            },
        ]

        # Cities for pickup and delivery
        cities = [
            "Kathmandu",
            "Lalitpur",
            "Bhaktapur",
            "Pokhara",
            "Chitwan",
            "Dharan",
            "Birgunj",
            "Biratnagar",
            "Janakpur",
            "Nepalgunj",
        ]

        created_businesses = []

        for i in range(num_businesses):
            template = business_templates[i % len(business_templates)]

            # Create unique data for each business
            business_data = template.copy()
            if i > 0:
                business_data["name"] = f"{template['name']} {i+1}"
                business_data["email"] = f"api{i+1}@{template['email'].split('@')[1]}"

            business = ExternalBusiness.objects.create(
                business_name=business_data["name"],
                business_email=business_data["email"],
                contact_person=business_data["person"],
                contact_phone=business_data["phone"],
                business_address=business_data["address"],
                website=business_data["website"],
                plan=business_data["plan"],
                status=ExternalBusinessStatus.APPROVED,
                allowed_pickup_cities=cities[:5],  # First 5 cities
                allowed_delivery_cities=cities,  # All cities
                max_delivery_value=Decimal("50000.00"),
            )

            created_businesses.append(business)

            self.stdout.write(f"✓ Created business: {business.business_name}")
            self.stdout.write(f"  API Key: {business.api_key}")

        # Create deliveries for each business
        self.stdout.write(f"\nCreating deliveries for each business...")

        import random
        from datetime import datetime, timedelta

        # Sample delivery data
        pickup_names = [
            "Tech Store Warehouse",
            "Fashion Hub Store",
            "Organic Farm",
            "Digital Office",
            "Book Depot",
            "Electronics Hub",
            "Clothing Store",
            "Food Center",
            "Hardware Shop",
        ]

        delivery_names = [
            "Ram Bahadur",
            "Sita Maya",
            "Hari Prasad",
            "Gita Sharma",
            "Bikash Thapa",
            "Sunita Rai",
            "Deepak Gurung",
            "Mina Tamang",
        ]

        package_descriptions = [
            "Electronic Gadgets",
            "Fashion Items",
            "Organic Products",
            "Books and Stationery",
            "Computer Accessories",
            "Mobile Phone",
            "Clothing and Accessories",
            "Food Items",
            "Home Appliances",
        ]

        total_deliveries = 0

        for business in created_businesses:
            business_deliveries = 0

            for j in range(deliveries_per_business):
                # Random date in last 30 days
                days_ago = random.randint(0, 30)
                created_date = datetime.now() - timedelta(days=days_ago)

                # Random status with weighted distribution
                status_weights = [
                    (ExternalDeliveryStatus.DELIVERED, 40),
                    (ExternalDeliveryStatus.IN_TRANSIT, 20),
                    (ExternalDeliveryStatus.PICKED_UP, 15),
                    (ExternalDeliveryStatus.ACCEPTED, 10),
                    (ExternalDeliveryStatus.PENDING, 10),
                    (ExternalDeliveryStatus.FAILED, 3),
                    (ExternalDeliveryStatus.CANCELLED, 2),
                ]

                statuses, weights = zip(*status_weights)
                delivery_status = random.choices(statuses, weights=weights)[0]

                # Random cities
                pickup_city = random.choice(cities[:5])  # From allowed pickup cities
                delivery_city = random.choice(cities)

                # Random package details
                package_weight = round(random.uniform(0.5, 10.0), 2)
                package_value = round(random.uniform(100, 25000), 2)
                is_cod = random.choice([True, False])
                cod_amount = round(package_value * 0.8, 2) if is_cod else None

                delivery = ExternalDelivery.objects.create(
                    external_business=business,
                    external_delivery_id=f'{business.business_name.replace(" ", "")}_DEL_{j+1:03d}',
                    # Pickup info
                    pickup_name=random.choice(pickup_names),
                    pickup_phone=f"+977-98{random.randint(10000000, 99999999)}",
                    pickup_address=f"{random.randint(1, 999)} {pickup_city} Street",
                    pickup_city=pickup_city,
                    # Delivery info
                    delivery_name=random.choice(delivery_names),
                    delivery_phone=f"+977-98{random.randint(10000000, 99999999)}",
                    delivery_address=f"{random.randint(1, 999)} {delivery_city} Road",
                    delivery_city=delivery_city,
                    # Package info
                    package_description=random.choice(package_descriptions),
                    package_weight=Decimal(str(package_weight)),
                    package_value=Decimal(str(package_value)),
                    fragile=random.choice([True, False]),
                    # Payment
                    is_cod=is_cod,
                    cod_amount=Decimal(str(cod_amount)) if cod_amount else None,
                    # Status
                    status=delivery_status,
                    # Notes
                    notes=f"Sample delivery created for testing - {j+1}",
                )

                # Calculate and set delivery fees
                fees = delivery.calculate_delivery_fee()
                delivery.delivery_fee = fees["delivery_fee"]
                delivery.platform_commission = fees["platform_commission"]
                delivery.transporter_earnings = fees["transporter_earnings"]
                delivery.save()

                # Update timestamps based on status
                delivery.created_at = created_date
                if delivery_status in [
                    ExternalDeliveryStatus.ACCEPTED,
                    ExternalDeliveryStatus.PICKED_UP,
                    ExternalDeliveryStatus.IN_TRANSIT,
                    ExternalDeliveryStatus.DELIVERED,
                ]:
                    delivery.accepted_at = created_date + timedelta(hours=2)

                if delivery_status in [
                    ExternalDeliveryStatus.PICKED_UP,
                    ExternalDeliveryStatus.IN_TRANSIT,
                    ExternalDeliveryStatus.DELIVERED,
                ]:
                    delivery.picked_up_at = delivery.accepted_at + timedelta(hours=4)

                if delivery_status == ExternalDeliveryStatus.DELIVERED:
                    delivery.delivered_at = delivery.picked_up_at + timedelta(hours=8)

                delivery.save()

                business_deliveries += 1
                total_deliveries += 1

            self.stdout.write(f"✓ Created {business_deliveries} deliveries for {business.business_name}")

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n🎉 Sample data creation completed!\n"
                f"Created {len(created_businesses)} businesses and {total_deliveries} deliveries"
            )
        )

        # Show API keys for testing
        self.stdout.write(f"\n--- API KEYS FOR TESTING ---")
        for business in created_businesses:
            self.stdout.write(f"{business.business_name}: {business.api_key}")

        self.stdout.write(
            f"\n--- USAGE INSTRUCTIONS ---\n"
            f"1. Use the API keys above for testing external API endpoints\n"
            f"2. Test endpoints: /api/external/deliveries/\n"
            f"3. Use header: X-API-Key: <api_key>\n"
            f"4. Check admin panel for business and delivery management\n"
            f"5. Test tracking with any tracking number from created deliveries"
        )
