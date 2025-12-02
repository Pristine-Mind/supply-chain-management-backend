from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from producer.models import Producer


class Command(BaseCommand):
    help = "Update producers with user associations based on producer name to username mappings"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        
        # Show debugging information
        self.stdout.write("=== DEBUGGING INFO ===")
        
        # Show all available users
        all_users = User.objects.all()[:15]
        self.stdout.write(f"Available users (first 15):")
        for user in all_users:
            self.stdout.write(f"  - {user.username}")
        
        # Show all available producers
        all_producers = Producer.objects.all()[:15]
        self.stdout.write(f"\nAvailable producers (first 15):")
        for producer in all_producers:
            self.stdout.write(f"  - {producer.name}")
        
        self.stdout.write("\n=== STARTING UPDATES ===\n")

        # Define producer name to username mappings
        producer_user_mappings = {
            "ITEAM PVT. LTD.": "iteam_nepal",
            "Himstar Nepal Pvt Ltd": "himstar_nepal",
            "Asus Nagmani Pvt Ltd": "asus_nagmani",
            "Hitech Nepal Pvt Ltd": "hitech_nepal",
            "SHYAM SPORTS AND FITNESS PVT LTD": "shyam_sports",
            "Gunina Technotronix and Research Center Pvt Ltd": "gtc_nepal",
            "Baladu Co": "baladu_co",
            "Aspire Nepal": "aspire_np",
            "Agro Unicorn": "agro_unicorn",
            "70mai Nepal": "70mai_nepal",
            "Clamp Nepal": "clamp_nepal",
            "Panipokhari Liquor Shop": "panipokhari_liquor_shop",
            "VaryGood Perfumes": "varygood_perfumes",
            "Bymo Nepal": "bymo_np",
            "Hamro Local Mart": "hamro_local_mart",
            "PeeKaboo": "peekaboo",
            "Ezee kart Nepal": "ezee_kart_nepal",
        }

        updated_count = 0
        errors = []

        for producer_name, username in producer_user_mappings.items():
            try:
                # Get the producer (using icontains for flexible matching)
                producer = Producer.objects.filter(name__icontains=producer_name).first()
                if not producer:
                    # Try exact match as fallback
                    producer = Producer.objects.filter(name=producer_name).first()
                
                if not producer:
                    error_msg = f"Producer with name containing '{producer_name}' not found"
                    errors.append(error_msg)
                    self.stdout.write(self.style.WARNING(error_msg))
                    
                    # Show similar producer names that might match
                    producer_parts = producer_name.split()
                    if producer_parts:
                        similar_producers = Producer.objects.filter(name__icontains=producer_parts[0])[:5]
                        if similar_producers:
                            self.stdout.write("  Similar producer names found:")
                            for similar_producer in similar_producers:
                                self.stdout.write(f"    - {similar_producer.name}")
                    continue
                
                self.stdout.write(f"Found producer: {producer.name}")

                # Get the user (using icontains for flexible matching)
                user = User.objects.filter(username__icontains=username).first()
                if not user:
                    # Try exact match as fallback
                    user = User.objects.filter(username=username).first()
                
                if not user:
                    error_msg = f"User with username containing '{username}' not found"
                    errors.append(error_msg)
                    self.stdout.write(self.style.WARNING(error_msg))
                    
                    # Show available usernames that might match
                    username_parts = username.split('_')
                    if username_parts:
                        similar_users = User.objects.filter(username__icontains=username_parts[0])[:5]
                        if similar_users:
                            self.stdout.write("  Similar usernames found:")
                            for similar_user in similar_users:
                                self.stdout.write(f"    - {similar_user.username}")
                    continue
                
                self.stdout.write(f"Found user: {user.username}")

                # Check if producer already has this user
                if producer.user == user:
                    self.stdout.write(f"Producer '{producer.name}' already mapped to user '{user.username}' - skipping")
                    continue

                # Show what would be updated
                current_user = producer.user.username if producer.user else "No user"
                if dry_run:
                    self.stdout.write(
                        f"DRY RUN - Would update producer '{producer.name}' from user '{current_user}' to '{user.username}'"
                    )
                else:
                    # Actually update the producer
                    old_user = producer.user.username if producer.user else "No user"
                    producer.user = user
                    producer.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Updated producer '{producer.name}' from user '{old_user}' to '{user.username}'"
                        )
                    )

            except Exception as e:
                error_msg = f"Error processing producer '{producer_name}': {str(e)}"
                errors.append(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))

        # Summary
        if dry_run:
            self.stdout.write(self.style.WARNING("\n=== DRY RUN SUMMARY ==="))
            self.stdout.write("No changes were made. Use --dry-run=False to apply changes.")
        else:
            self.stdout.write(self.style.SUCCESS(f"\n=== SUMMARY ==="))
            self.stdout.write(self.style.SUCCESS(f"Total producers updated: {updated_count}"))

        if errors:
            self.stdout.write(self.style.ERROR(f"Errors encountered: {len(errors)}"))
            for error in errors:
                self.stdout.write(self.style.ERROR(f"  - {error}"))
        else:
            self.stdout.write(self.style.SUCCESS("No errors encountered"))