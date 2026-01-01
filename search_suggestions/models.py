import hashlib
import uuid

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


def normalize_query(query):
    """Normalize search query"""
    import re

    if not query:
        return ""
    normalized = query.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^\w\s\-\.]", "", normalized)
    return normalized


def get_query_hash(query):
    """Generate consistent hash for query"""
    normalized = normalize_query(query)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


class SearchEvent(models.Model):
    """Tracks all search queries made by users"""

    # User/Session info
    session_id = models.CharField(max_length=64, db_index=True)
    user_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    # Search query
    original_query = models.TextField(_("Original Query"))
    normalized_query = models.CharField(max_length=500, db_index=True)
    query_hash = models.CharField(max_length=64, db_index=True)

    # Context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    device_type = models.CharField(
        max_length=32, choices=[("mobile", "Mobile"), ("desktop", "Desktop"), ("tablet", "Tablet")], default="desktop"
    )
    referrer = models.URLField(null=True, blank=True)

    # Results
    result_count = models.IntegerField(default=0)
    has_click = models.BooleanField(default=False)
    has_purchase = models.BooleanField(default=False)
    click_position = models.IntegerField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["normalized_query", "created_at"]),
            models.Index(fields=["session_id", "created_at"]),
            models.Index(fields=["user_id", "created_at"]),
            models.Index(fields=["has_click", "created_at"]),
            models.Index(fields=["has_purchase", "created_at"]),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Normalize before saving
        self.normalized_query = normalize_query(self.original_query)
        self.query_hash = get_query_hash(self.normalized_query)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.normalized_query[:30]}... ({self.session_id[:8]})"


class QueryAssociation(models.Model):
    """Precomputed relationships between search queries"""

    source_query = models.CharField(max_length=500, db_index=True)
    source_query_hash = models.CharField(max_length=64, db_index=True)
    target_query = models.CharField(max_length=500, db_index=True)
    target_query_hash = models.CharField(max_length=64, db_index=True)

    # Strength metrics
    co_occurrence_count = models.IntegerField(default=0, help_text="Number of times searched together")
    session_co_occurrence = models.IntegerField(default=0, help_text="Same session occurrences")

    # Performance metrics
    source_to_target_ctr = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Click-through rate from source to target",
    )
    target_to_source_ctr = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Click-through rate from target to source",
    )
    conversion_rate = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)], help_text="Purchase rate"
    )

    # Time-based weighting
    last_occurrence = models.DateTimeField(auto_now=True)
    decay_score = models.FloatField(default=1.0, help_text="Time-decayed importance")

    # Metadata
    association_type = models.CharField(
        max_length=50,
        choices=[
            ("co_search", "Co-Search"),
            ("category", "Same Category"),
            ("brand", "Same Brand"),
            ("complementary", "Complementary"),
            ("attribute", "Same Attributes"),
            ("manual", "Manually Added"),
        ],
        default="co_search",
    )

    confidence_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [["source_query_hash", "target_query_hash"]]
        indexes = [
            models.Index(fields=["source_query_hash", "-co_occurrence_count"]),
            models.Index(fields=["target_query_hash", "-co_occurrence_count"]),
            models.Index(fields=["association_type", "-confidence_score"]),
            models.Index(fields=["-decay_score"]),
        ]
        verbose_name = _("Query Association")
        verbose_name_plural = _("Query Associations")

    def __str__(self):
        return f"{self.source_query} → {self.target_query}"


class QueryPerformacePopularity(models.Model):
    """Tracks popularity and performance of search queries"""

    query = models.CharField(max_length=500, db_index=True)
    query_hash = models.CharField(max_length=64, db_index=True, unique=True)

    # Volume metrics
    total_searches = models.BigIntegerField(default=0)
    unique_users = models.IntegerField(default=0)
    unique_sessions = models.IntegerField(default=0)

    # Time-based volumes
    searches_today = models.IntegerField(default=0)
    searches_this_week = models.IntegerField(default=0)
    searches_this_month = models.IntegerField(default=0)

    # Performance metrics
    total_clicks = models.IntegerField(default=0)
    total_purchases = models.IntegerField(default=0)
    click_through_rate = models.FloatField(default=0.0)
    conversion_rate = models.FloatField(default=0.0)
    avg_click_position = models.FloatField(default=0.0)

    # Trending
    trending_score = models.FloatField(default=0.0, help_text="Velocity of searches")
    trend_direction = models.CharField(
        max_length=10,
        choices=[("up", "Increasing"), ("down", "Decreasing"), ("stable", "Stable"), ("new", "New")],
        default="stable",
    )

    # Category info (for better suggestions)
    primary_category = models.CharField(max_length=100, null=True, blank=True)
    detected_categories = ArrayField(
        models.CharField(max_length=100), default=list, blank=True, help_text="Categories this query belongs to"
    )

    # Business metrics
    avg_order_value = models.FloatField(null=True, blank=True)
    revenue_generated = models.FloatField(default=0.0)

    # Timestamps
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Query Performance Popularity")
        verbose_name_plural = _("Query Performance Popularities")
        ordering = ["-total_searches"]

    def __str__(self):
        return f"{self.query} ({self.total_searches} searches)"


class SearchSuggestionCache(models.Model):
    """Cache for expensive suggestion calculations"""

    query_hash = models.CharField(max_length=64, primary_key=True)
    suggestions = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    hit_count = models.IntegerField(default=0)
    last_accessed = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Suggestion Cache")
        verbose_name_plural = _("Suggestion Caches")

    def __str__(self):
        return f"Cache for {self.query_hash[:8]}..."


class ManualQueryAssociation(models.Model):
    """Manually curated query associations for important relationships"""

    source_query = models.CharField(max_length=500)
    target_query = models.CharField(max_length=500)

    # Relationship details
    relationship_type = models.CharField(
        max_length=50,
        choices=[
            ("synonym", "Synonym"),
            ("upsell", "Upsell"),
            ("cross_sell", "Cross-Sell"),
            ("complementary", "Complementary"),
            ("alternative", "Alternative"),
            ("upgrade", "Upgrade"),
            ("downgrade", "Downgrade"),
        ],
    )

    strength = models.FloatField(
        default=1.0, validators=[MinValueValidator(0.0), MaxValueValidator(10.0)], help_text="Manual strength score (0-10)"
    )

    description = models.TextField(blank=True, help_text="Why this association exists")

    # Business rules
    min_price = models.FloatField(null=True, blank=True, help_text="Minimum price for this suggestion")
    max_price = models.FloatField(null=True, blank=True, help_text="Maximum price for this suggestion")
    applicable_categories = ArrayField(
        models.CharField(max_length=100), default=list, blank=True, help_text="Categories where this applies"
    )

    # Activation
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="Higher priority shows first")

    # Metadata
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["source_query", "target_query"]]
        verbose_name = _("Manual Query Association")
        verbose_name_plural = _("Manual Query Associations")

    def __str__(self):
        return f"{self.source_query} → {self.target_query} ({self.relationship_type})"
