from decimal import Decimal

from django.core.management.base import BaseCommand

from loyalty.models import LoyaltyPerk, LoyaltyTier


class Command(BaseCommand):
    help = "Initialize default loyalty tiers and perks"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing tiers and recreate",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Deleting existing tiers...")
            LoyaltyTier.objects.all().delete()

        self.stdout.write("Creating default tiers...")

        # Bronze Tier
        bronze, created = LoyaltyTier.objects.get_or_create(
            name="Bronze",
            defaults={
                "min_points": 0,
                "point_multiplier": Decimal("1.00"),
                "description": "Entry level tier for all members",
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Bronze tier"))

            # Bronze perks
            LoyaltyPerk.objects.get_or_create(
                tier=bronze,
                code="birthday_discount",
                defaults={"name": "Birthday Discount", "description": "10% off on your birthday month", "is_active": True},
            )

        # Silver Tier
        silver, created = LoyaltyTier.objects.get_or_create(
            name="Silver",
            defaults={
                "min_points": 1000,
                "point_multiplier": Decimal("1.25"),
                "description": "Silver members earn 25% bonus points",
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Silver tier"))

            # Silver perks
            LoyaltyPerk.objects.get_or_create(
                tier=silver,
                code="free_shipping",
                defaults={"name": "Free Shipping", "description": "Free standard shipping on all orders", "is_active": True},
            )
            LoyaltyPerk.objects.get_or_create(
                tier=silver,
                code="early_access",
                defaults={
                    "name": "Early Access",
                    "description": "Early access to sales and new products",
                    "is_active": True,
                },
            )

        # Gold Tier
        gold, created = LoyaltyTier.objects.get_or_create(
            name="Gold",
            defaults={
                "min_points": 5000,
                "point_multiplier": Decimal("1.50"),
                "description": "Gold members earn 50% bonus points",
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Gold tier"))

            # Gold perks
            LoyaltyPerk.objects.get_or_create(
                tier=gold,
                code="priority_support",
                defaults={"name": "Priority Support", "description": "24/7 priority customer support", "is_active": True},
            )
            LoyaltyPerk.objects.get_or_create(
                tier=gold,
                code="exclusive_events",
                defaults={
                    "name": "Exclusive Events",
                    "description": "Invitations to exclusive member events",
                    "is_active": True,
                },
            )
            LoyaltyPerk.objects.get_or_create(
                tier=gold,
                code="express_shipping",
                defaults={
                    "name": "Express Shipping",
                    "description": "Free express shipping on all orders",
                    "is_active": True,
                },
            )

        # Platinum Tier
        platinum, created = LoyaltyTier.objects.get_or_create(
            name="Platinum",
            defaults={
                "min_points": 10000,
                "point_multiplier": Decimal("2.00"),
                "description": "Platinum members earn double points",
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Platinum tier"))

            # Platinum perks
            LoyaltyPerk.objects.get_or_create(
                tier=platinum,
                code="concierge_service",
                defaults={
                    "name": "Concierge Service",
                    "description": "Personal shopping concierge service",
                    "is_active": True,
                },
            )
            LoyaltyPerk.objects.get_or_create(
                tier=platinum,
                code="lifetime_warranty",
                defaults={
                    "name": "Lifetime Warranty",
                    "description": "Lifetime warranty on all purchases",
                    "is_active": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("Successfully initialized loyalty tiers"))
