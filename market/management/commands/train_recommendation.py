import logging

from django.core.management.base import BaseCommand

from market.recommendation import DiscoveryEngine, FastRetrievalService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Train the Shoppable Video recommendation engine (ALS) and rebuild FAISS index."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting recommendation engine training..."))

        # 1. Train Matrix Factorization (ALS)
        engine = DiscoveryEngine(factors=64)
        try:
            engine.train()
            self.stdout.write(self.style.SUCCESS("ALS training and embedding persistence completed."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"ALS training failed: {str(e)}"))
            return

        # 2. Rebuild FAISS index
        self.stdout.write("Rebuilding FAISS index...")
        retrieval = FastRetrievalService(dimension=64)
        try:
            retrieval.rebuild_index()
            self.stdout.write(self.style.SUCCESS("FAISS index successfully rebuilt."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"FAISS index rebuild failed: {str(e)}"))

        self.stdout.write(self.style.SUCCESS("All tasks completed successfully."))
