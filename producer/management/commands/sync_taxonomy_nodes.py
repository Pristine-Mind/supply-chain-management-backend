import json
import os
from django.core.management.base import BaseCommand
from producer.models import SearchTaxonomyNode
from producer.utils import DynamicSynonymService


class Command(BaseCommand):
    help = "Syncs and updates SearchTaxonomyNode table from a structured JSON feed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="/code/market/data/search_synonyms.json",
            help="Path to JSON taxonomy file",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        created_count = 0
        updated_count = 0

        for key, details in data.items():
            clean_key = key.strip().lower()
            _, created = SearchTaxonomyNode.objects.update_or_create(
                key=clean_key,
                defaults={
                    "canonical": details.get("canonical", clean_key),
                    "category": details.get("category", ""),
                    "aliases": [a.strip().lower() for a in details.get("aliases", [])],
                    "trending_suggestions": details.get("trending_suggestions", []),
                    "is_active": details.get("is_active", True),
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        DynamicSynonymService.invalidate_cache()
        self.stdout.write(
            self.style.SUCCESS(
                f"Taxonomy Sync Complete: {created_count} created, {updated_count} updated. Cache invalidated."
            )
        )