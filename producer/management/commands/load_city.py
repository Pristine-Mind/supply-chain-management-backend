from django.core.management.base import BaseCommand
from producer.models import City


class Command(BaseCommand):
    help = "Load cities of Nepal into the City model"

    def handle(self, *args, **kwargs):
        cities = [
            "Kathmandu",
            "Pokhara",
            "Lalitpur",
            "Bhaktapur",
            "Biratnagar",
            "Birgunj",
            "Butwal",
            "Nepalgunj",
            "Dhangadhi",
            "Hetauda",
            "Dharan",
            "Bharatpur",
            "Janakpur",
            "Tansen",
            "Gorkha",
            "Bhadrapur",
            "Ilam",
            "Lumbini",
            "Palpa",
            "Syangja",
        ]

        for city_name in cities:
            City.objects.get_or_create(name=city_name)

        self.stdout.write(self.style.SUCCESS("Successfully loaded cities of Nepal"))
