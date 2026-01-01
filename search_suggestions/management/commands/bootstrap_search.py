import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from search_suggestions.services.bootstrap_service import CatalogBootstrapService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Bootstrap initial search suggestions from product catalog"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Clear existing data and force bootstrap")
        parser.add_argument("--skip-manual", action="store_true", help="Skip manual associations")
        parser.add_argument("--categories-only", action="store_true", help="Only bootstrap category-based suggestions")

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Starting search suggestions bootstrap..."))

        try:
            with transaction.atomic():
                service = CatalogBootstrapService()

                if options["categories_only"]:
                    self.stdout.write("Bootstrapping category-based suggestions...")
                    count = service._bootstrap_from_categories()
                    self.stdout.write(self.style.SUCCESS(f"Created {count} category suggestions"))
                else:
                    results = service.bootstrap_from_catalog(force=options["force"])

                    self.stdout.write("\n" + "=" * 50)
                    self.stdout.write(self.style.SUCCESS("BOOTSTRAP COMPLETE"))
                    self.stdout.write("=" * 50)
                    self.stdout.write(f"Total Suggestions: {results['total_suggestions']}")
                    self.stdout.write(f"Category-based: {results['category']}")
                    self.stdout.write(f"Brand-based: {results['brand']}")
                    self.stdout.write(f"Attribute-based: {results['attribute']}")
                    self.stdout.write(f"Complementary: {results['complementary']}")
                    self.stdout.write(f"Manual: {results['manual']}")
                    self.stdout.write(f"Popularity Entries: {results['popularity']}")
                    self.stdout.write("=" * 50)

                    # # Warm up cache after bootstrap
                    # if not options.get('skip_cache', False):
                    #     self.stdout.write("\nWarming up cache...")
                    #     from search_suggestions.services.bootstrap_service import CatalogBootstrapService
                    #     cache_service = CatalogBootstrapService()
                    #     cached = cache_service.warmup_cache(50)
                    #     self.stdout.write(f"Cached {cached} popular queries")

                    # # Test a sample query
                    self._test_sample_queries()

        except Exception as e:
            logger.error(f"Bootstrap failed: {e}")
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
            raise

    def _test_sample_queries(self):
        """Test a few sample queries to verify bootstrap"""
        from search_suggestions.services.suggestion_service import (
            SearchSuggestionService,
        )

        service = SearchSuggestionService()
        test_queries = ["iphone", "laptop", "shoes", "watch"]

        self.stdout.write("\n" + "-" * 50)
        self.stdout.write("TESTING SAMPLE QUERIES")
        self.stdout.write("-" * 50)

        for query in test_queries:
            suggestions = service.get_suggestions(query, limit=3)
            self.stdout.write(f"\nQuery: '{query}'")
            if suggestions:
                for i, sugg in enumerate(suggestions, 1):
                    self.stdout.write(f"  {i}. {sugg['query']} ({sugg['type']})")
            else:
                self.stdout.write("  No suggestions yet")
