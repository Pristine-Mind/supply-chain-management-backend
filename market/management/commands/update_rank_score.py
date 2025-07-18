from datetime import timedelta
from decimal import InvalidOperation
import logging

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from market.models import MarketplaceProduct, MarketplaceSale, ProductView
from producer.models import Sale

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Recompute rank_score for all marketplace products, including marketplace sales and views"

    # Define weights with validation
    WEIGHTS = {
        "sales_vel": 0.15,
        "mkt_sales": 0.15,
        "views_7d": 0.15,
        "recent_pur": 0.10,
        "avg_rating": 0.10,
        "review_ct": 0.05,
        "recency": 0.10,
        "margin": 0.05,
        "stock": 0.10,
        "offer": 0.05,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._validate_weights()

    def _validate_weights(self):
        """Validate that weights sum to 1 (or very close to it)"""
        total = sum(self.WEIGHTS.values())
        if not 0.999 <= total <= 1.001:
            raise ValueError(f"Weights must sum to 1, got {total}")

    def _safe_divide(self, numerator, denominator, default=0.0):
        """Safely divide two numbers, returning default if denominator is zero"""
        try:
            return float(numerator) / float(denominator) if denominator else default
        except (TypeError, ValueError):
            return default

    def _get_views_map(self, since_7d):
        """Get view counts for products"""
        try:
            views_qs = (
                ProductView.objects.filter(timestamp__gte=since_7d)
                .values("product")
                .annotate(unique_views=Count("session_key", distinct=True))
            )
            return {v["product"]: v["unique_views"] for v in views_qs}
        except Exception as e:
            logger.error(f"Error getting views data: {str(e)}")
            return {}

    def _get_marketplace_sales(self, since_30d):
        """Get marketplace sales data"""
        try:
            mkt_sales_qs = (
                MarketplaceSale.objects.filter(sale_date__date__gte=since_30d)
                .values("marketplace_product")
                .annotate(total_mkt_qty=Sum("quantity"))
            )
            return {v["marketplace_product"]: v["total_mkt_qty"] for v in mkt_sales_qs}
        except Exception as e:
            logger.error(f"Error getting marketplace sales data: {str(e)}")
            return {}

    def _calculate_product_metrics(self, mp, today, views_map, mkt_sales_map):
        """Calculate metrics for a single product"""
        try:
            prod = mp.product
            if not prod:
                return None

            sales_vel = MarketplaceSale.objects.filter(product=mp, sale_date__date__gte=today - timedelta(days=30)).count()

            mkt_sales = mkt_sales_map.get(mp.id, 0)

            days_old = (today - mp.listed_date.date()).days if mp.listed_date else 0
            recency = 1.0 / (1.0 + float(days_old)) if days_old >= 0 else 0.0

            try:
                margin = self._safe_divide(float(mp.listed_price) - float(prod.cost_price or 0), float(mp.listed_price or 1))
            except (TypeError, ValueError, InvalidOperation):
                margin = 0.0

            stock = max(0, int(prod.stock or 0))
            offer = 1 if mp.is_offer_active else 0
            views = max(0, int(views_map.get(mp.id, 0)))

            return {
                "id": mp.id,
                "sales_vel": max(0, int(sales_vel or 0)),
                "mkt_sales": max(0, int(mkt_sales or 0)),
                "recent_pur": max(0, int(mp.recent_purchases_count or 0)),
                "avg_rating": min(5.0, max(0.0, float(mp.average_rating or 0))),
                "review_ct": max(0, int(mp.total_reviews or 0)),
                "recency": min(1.0, max(0.0, float(recency or 0))),
                "margin": min(1.0, max(0.0, float(margin or 0))),
                "stock": stock,
                "offer": offer,
                "views_7d": views,
            }

        except Exception as e:
            logger.error(f"Error processing product {mp.id}: {str(e)}")
            return None

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Starting rank score update..."))
        start_time = timezone.now()

        try:
            today = timezone.now().date()
            since_30d = today - timedelta(days=30)
            since_7d = timezone.now() - timedelta(days=7)

            self.stdout.write("Collecting product views data...")
            views_map = self._get_views_map(since_7d)

            self.stdout.write("Collecting marketplace sales data...")
            mkt_sales_map = self._get_marketplace_sales(since_30d)

            self.stdout.write("Processing products...")
            data = []
            total_products = MarketplaceProduct.objects.count()
            processed = 0

            batch_size = 100
            for i in range(0, total_products, batch_size):
                batch = MarketplaceProduct.objects.select_related("product").order_by("id")[i : i + batch_size]
                for mp in batch:
                    metrics = self._calculate_product_metrics(mp, today, views_map, mkt_sales_map)
                    if metrics:
                        data.append(metrics)
                    processed += 1

                    if processed % 100 == 0 or processed == total_products:
                        self.stdout.write(f"Processed {processed}/{total_products} products...", ending="\r")
                        self.stdout.flush()

            if not data:
                self.stdout.write(self.style.WARNING("No valid product data to process"))
                return

            self.stdout.write("\nCalculating rank scores...")

            df = pd.DataFrame(data).set_index("id")

            for col in df.columns:
                col_min = df[col].min()
                col_range = df[col].max() - col_min
                if col_range > 0:
                    df[col] = (df[col] - col_min) / col_range

            df["rank_score"] = sum(df[col] * weight for col, weight in self.WEIGHTS.items())

            df["rank_score"] = (df["rank_score"] * 100).round(2)

            self.stdout.write("Updating database...")
            updated_count = 0
            with transaction.atomic():
                MarketplaceProduct.objects.all().update(rank_score=0)

                for i in range(0, len(df), batch_size):
                    batch = df.iloc[i : i + batch_size]
                    for mp_id, row in batch.iterrows():
                        MarketplaceProduct.objects.filter(pk=mp_id).update(rank_score=row["rank_score"])
                    updated_count += len(batch)
                    self.stdout.write(f"Updated {min(updated_count, len(df))}/{len(df)} products...", ending="\r")
                    self.stdout.flush()

            duration = (timezone.now() - start_time).total_seconds()
            self.stdout.write(
                "\n"
                + self.style.SUCCESS(
                    f"✅ Successfully updated rank scores for {updated_count} products in {duration:.1f} seconds"
                )
            )

            if not df.empty:
                stats = {
                    "Min Score": df["rank_score"].min(),
                    "Avg Score": df["rank_score"].mean(),
                    "Max Score": df["rank_score"].max(),
                    "Std Dev": df["rank_score"].std(),
                }
                self.stdout.write("\nScore Statistics:" + "\n" + "\n".join(f"- {k}: {v:.2f}" for k, v in stats.items()))

        except Exception as e:
            logger.exception("Error in update_rank_score command")
            self.stderr.write(self.style.ERROR(f"Error: {str(e)}"))
            self.stderr.write(self.style.ERROR("Rank score update failed. Check logs for details."))
            raise
