# search_suggestions/admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    ManualQueryAssociation,
    QueryAssociation,
    QueryPerformacePopularity,
    SearchEvent,
    SearchSuggestionCache,
)


@admin.register(SearchEvent)
class SearchEventAdmin(admin.ModelAdmin):
    list_display = ["truncated_query", "session_short", "has_click", "has_purchase", "device_type", "created_at"]
    list_filter = ["has_click", "has_purchase", "device_type", "created_at"]
    search_fields = ["normalized_query", "session_id", "user_id"]
    readonly_fields = ["created_at", "query_hash"]
    date_hierarchy = "created_at"
    list_per_page = 50

    def truncated_query(self, obj):
        return obj.normalized_query[:50] + ("..." if len(obj.normalized_query) > 50 else "")

    truncated_query.short_description = "Query"

    def session_short(self, obj):
        return obj.session_id[:8] + "..." if obj.session_id else ""

    session_short.short_description = "Session"


@admin.register(QueryAssociation)
class QueryAssociationAdmin(admin.ModelAdmin):
    list_display = [
        "source_query_display",
        "target_query_display",
        "co_occurrence_count",
        "association_type",
        "confidence_score_display",
        "is_active",
    ]
    list_filter = ["association_type", "is_active", "last_occurrence"]
    search_fields = ["source_query", "target_query"]
    readonly_fields = ["last_occurrence", "decay_score"]
    list_per_page = 50

    def source_query_display(self, obj):
        return obj.source_query[:40] + ("..." if len(obj.source_query) > 40 else "")

    source_query_display.short_description = "Source Query"

    def target_query_display(self, obj):
        return obj.target_query[:40] + ("..." if len(obj.target_query) > 40 else "")

    target_query_display.short_description = "Target Query"

    def confidence_score_display(self, obj):
        if obj.confidence_score > 0.8:
            color = "green"
        elif obj.confidence_score > 0.5:
            color = "orange"
        else:
            color = "red"
        return format_html('<span style="color: {}; font-weight: bold;">{:.2f}</span>', color, obj.confidence_score)

    confidence_score_display.short_description = "Confidence"


@admin.register(QueryPerformacePopularity)
class QueryPerformacePopularityAdmin(admin.ModelAdmin):
    list_display = [
        "query_display",
        "total_searches",
        "trending_score_display",
        "click_through_rate_display",
        "conversion_rate_display",
        "primary_category",
        "last_seen",
    ]
    list_filter = ["primary_category", "trend_direction", "last_seen"]
    search_fields = ["query"]
    readonly_fields = ["first_seen", "last_seen", "query_hash"]
    list_per_page = 50

    def query_display(self, obj):
        return obj.query[:50] + ("..." if len(obj.query) > 50 else "")

    query_display.short_description = "Query"

    def trending_score_display(self, obj):
        if obj.trending_score > 2:
            icon = "↗️"
            color = "green"
        elif obj.trending_score > 1:
            icon = "→"
            color = "orange"
        else:
            icon = "↘️"
            color = "red"
        return format_html('<span style="color: {};">{} {:.2f}</span>', color, icon, obj.trending_score)

    trending_score_display.short_description = "Trending"

    def click_through_rate_display(self, obj):
        return f"{obj.click_through_rate:.1%}"

    click_through_rate_display.short_description = "CTR"

    def conversion_rate_display(self, obj):
        return f"{obj.conversion_rate:.1%}"

    conversion_rate_display.short_description = "Conversion"


@admin.register(ManualQueryAssociation)
class ManualQueryAssociationAdmin(admin.ModelAdmin):
    list_display = ["source_query", "target_query", "relationship_type", "strength", "is_active", "priority", "created_by"]
    list_filter = ["relationship_type", "is_active", "created_at"]
    search_fields = ["source_query", "target_query", "description"]
    list_editable = ["strength", "is_active", "priority"]
    list_per_page = 50


@admin.register(SearchSuggestionCache)
class SearchSuggestionCacheAdmin(admin.ModelAdmin):
    list_display = ["query_hash_short", "hit_count", "created_at", "expires_at", "is_expired"]
    list_filter = ["expires_at"]
    readonly_fields = ["created_at", "last_accessed", "hit_count"]

    def query_hash_short(self, obj):
        return obj.query_hash[:8] + "..."

    query_hash_short.short_description = "Query Hash"

    def is_expired(self, obj):
        from django.utils import timezone

        return obj.expires_at < timezone.now()

    is_expired.boolean = True
    is_expired.short_description = "Expired"
