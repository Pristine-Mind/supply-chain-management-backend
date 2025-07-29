from django.core.management.base import BaseCommand

from transport.tasks import run_periodic_tasks


class Command(BaseCommand):
    help = "Run periodic transport tasks"

    def handle(self, *args, **options):
        results = run_periodic_tasks()
        self.stdout.write(f"Task results: {results}")
