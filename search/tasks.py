import logging

from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_device_type(user_agent: str):
    if not user_agent:
        return "desktop"
    ua = user_agent.lower()
    if "mobile" in ua:
        return "mobile"
    if "tablet" in ua or "ipad" in ua:
        return "tablet"
    return "desktop"


def _get_country_code(ip_address: str):
    # Keep this intentionally lightweight to avoid extra dependencies here
    if not ip_address:
        return None
    try:
        import ipaddress

        ip_obj = ipaddress.ip_address(ip_address)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
            return None
    except Exception:
        pass
    return None


@shared_task(bind=True)
def track_search_event(self, session_id, user_id, query, request_meta):
    """Create a SearchEvent record asynchronously."""
    try:
        from .models import SearchEvent

        SearchEvent.objects.create(
            session_id=session_id or "anonymous",
            user_id=user_id,
            query=query,
            device_type=_get_device_type((request_meta or {}).get("HTTP_USER_AGENT", "")),
            ip_address=(request_meta or {}).get("REMOTE_ADDR"),
            user_agent=(request_meta or {}).get("HTTP_USER_AGENT", "")[:500],
            country_code=_get_country_code((request_meta or {}).get("REMOTE_ADDR")),
        )
    except Exception:
        logger.exception("Error tracking search event")


@shared_task(bind=True)
def update_click_stats(self, source_query, clicked_query, position, user_id, session_id):
    """Update click statistics and associations asynchronously."""
    try:
        from .models import SearchEvent, QueryAssociation
        from .services import SearchSuggestionService

        service = SearchSuggestionService()

        # Create search event for the clicked query
        SearchEvent.objects.create(
            session_id=session_id or "anonymous",
            user_id=user_id,
            query=clicked_query,
            has_click=True,
        )

        # Update association metrics transactionally
        with transaction.atomic():
            source_hash = service.get_query_hash(source_query)
            target_hash = service.get_query_hash(clicked_query)

            QueryAssociation.objects.filter(source_query_hash=source_hash, target_query_hash=target_hash).update(
                source_to_target_ctr=F("source_to_target_ctr") * 0.9 + 0.1, last_updated=timezone.now()
            )

            QueryAssociation.objects.filter(source_query_hash=target_hash, target_query_hash=source_hash).update(
                target_to_source_ctr=F("target_to_source_ctr") * 0.9 + 0.1, last_updated=timezone.now()
            )

    except Exception:
        logger.exception("Error updating click stats")
import logging
from datetime import timedelta

from celery import shared_task
from django.db import connection
from django.utils import timezone

from .models import QueryAssociation, SearchEvent
from .services import SearchSuggestionService

logger = logging.getLogger(__name__)


@shared_task
def update_query_associations():
    """
    Periodically update query associations (run every hour)
    """
    try:
        service = SearchSuggestionService()

        # Get recent searches (last 24 hours)
        cutoff_time = timezone.now() - timedelta(hours=24)

        with connection.cursor() as cursor:
            # Update co-search counts
            cursor.execute(
                """
                WITH session_pairs AS (
                    SELECT DISTINCT 
                        s1.query_hash as query1_hash,
                        s1.normalized_query as query1,
                        s2.query_hash as query2_hash,
                        s2.normalized_query as query2,
                        s1.session_id
                    FROM search_events s1
                    JOIN search_events s2 ON s1.session_id = s2.session_id
                    WHERE s1.created_at >= %s
                    AND s2.created_at >= %s
                    AND s1.query_hash != s2.query_hash
                    AND s1.created_at BETWEEN s2.created_at - INTERVAL '30 minutes' 
                                         AND s2.created_at + INTERVAL '30 minutes'
                )
                INSERT INTO query_associations 
                    (source_query, source_query_hash, associated_query, associated_query_hash,
                     co_search_count, session_cooccurrence, last_updated, is_active)
                SELECT 
                    query1, query1_hash, query2, query2_hash,
                    COUNT(DISTINCT session_id),
                    COUNT(DISTINCT session_id),
                    NOW(),
                    TRUE
                FROM session_pairs
                GROUP BY query1, query1_hash, query2, query2_hash
                ON CONFLICT (source_query_hash, associated_query_hash) 
                DO UPDATE SET
                    co_search_count = EXCLUDED.co_search_count,
                    session_cooccurrence = EXCLUDED.session_cooccurrence,
                    last_updated = NOW(),
                    is_active = TRUE
            """,
                [cutoff_time, cutoff_time],
            )

            # Update metrics (CTR, conversion)
            cursor.execute(
                """
                UPDATE query_associations qa
                SET 
                    source_to_target_ctr = (
                        SELECT COALESCE(
                            AVG(CASE WHEN se.has_click THEN 1.0 ELSE 0.0 END), 0
                        )
                        FROM search_events se
                        WHERE se.query_hash = qa.associated_query_hash
                        AND se.session_id IN (
                            SELECT session_id 
                            FROM search_events 
                            WHERE query_hash = qa.source_query_hash
                        )
                        AND se.created_at >= %s
                    ),
                    conversion_rate = (
                        SELECT COALESCE(
                            AVG(CASE WHEN se.has_purchase THEN 1.0 ELSE 0.0 END), 0
                        )
                        FROM search_events se
                        WHERE se.query_hash = qa.associated_query_hash
                        AND se.session_id IN (
                            SELECT session_id 
                            FROM search_events 
                            WHERE query_hash = qa.source_query_hash
                        )
                        AND se.created_at >= %s
                    ),
                    time_decay_score = (
                        CASE 
                            WHEN co_search_count > 0 THEN
                                co_search_count * EXP(-EXTRACT(EPOCH FROM (NOW() - last_updated)) / (30 * 24 * 3600))
                            ELSE 0
                        END
                    )
                WHERE qa.last_updated >= %s
                OR qa.co_search_count > 0
            """,
                [cutoff_time, cutoff_time, cutoff_time],
            )

        logger.info("Updated query associations successfully")

    except Exception as e:
        logger.error(f"Error updating query associations: {e}")
        raise


@shared_task
def update_query_popularity():
    """
    Update query popularity metrics (run every 15 minutes)
    """
    try:
        # Time windows
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=now.weekday())
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH search_stats AS (
                    SELECT 
                        query_hash,
                        normalized_query,
                        COUNT(*) as total_searches,
                        COUNT(CASE WHEN created_at >= %s THEN 1 END) as searches_today,
                        COUNT(CASE WHEN created_at >= %s THEN 1 END) as searches_week,
                        COUNT(CASE WHEN created_at >= %s THEN 1 END) as searches_month,
                        SUM(CASE WHEN has_click THEN 1 ELSE 0 END) as total_clicks,
                        SUM(CASE WHEN has_purchase THEN 1 ELSE 0 END) as total_purchases
                    FROM search_events
                    WHERE created_at >= %s
                    GROUP BY query_hash, normalized_query
                )
                INSERT INTO query_popularity 
                    (query_hash, query, total_searches, searches_today, 
                     searches_this_week, searches_this_month, total_clicks,
                     total_purchases, click_through_rate, conversion_rate,
                     last_updated)
                SELECT 
                    query_hash,
                    normalized_query,
                    total_searches,
                    searches_today,
                    searches_week,
                    searches_month,
                    total_clicks,
                    total_purchases,
                    CASE WHEN total_searches > 0 
                         THEN total_clicks::float / total_searches 
                         ELSE 0 END,
                    CASE WHEN total_clicks > 0 
                         THEN total_purchases::float / NULLIF(total_clicks, 0) 
                         ELSE 0 END,
                    NOW()
                FROM search_stats
                ON CONFLICT (query_hash) 
                DO UPDATE SET
                    total_searches = EXCLUDED.total_searches,
                    searches_today = EXCLUDED.searches_today,
                    searches_this_week = EXCLUDED.searches_this_week,
                    searches_this_month = EXCLUDED.searches_this_month,
                    total_clicks = EXCLUDED.total_clicks,
                    total_purchases = EXCLUDED.total_purchases,
                    click_through_rate = EXCLUDED.click_through_rate,
                    conversion_rate = EXCLUDED.conversion_rate,
                    last_updated = NOW(),
                    trending_score = (
                        CASE 
                            WHEN query_popularity.searches_today > 0 
                            THEN EXCLUDED.searches_today::float / NULLIF(query_popularity.searches_today, 0)
                            ELSE 1.0
                        END * 
                        CASE 
                            WHEN EXCLUDED.searches_this_week > 0 
                            THEN EXCLUDED.searches_today::float / NULLIF(EXCLUDED.searches_this_week, 0) * 7
                            ELSE 1.0
                        END
                    )
            """,
                [today_start, week_start, month_start, now - timedelta(days=90)],  # 90-day lookback
            )

        logger.info("Updated query popularity successfully")

    except Exception as e:
        logger.error(f"Error updating query popularity: {e}")
        raise


@shared_task
def cleanup_old_data():
    """
    Clean up old search data (run daily)
    """
    try:
        # Delete old search events (keep 90 days)
        cutoff = timezone.now() - timedelta(days=90)
        deleted_count, _ = SearchEvent.objects.filter(created_at__lt=cutoff).delete()

        # Deactivate stale associations
        deactivated_count = QueryAssociation.objects.filter(
            last_updated__lt=timezone.now() - timedelta(days=30), co_search_count__lt=2
        ).update(is_active=False)

        logger.info(f"Cleaned up {deleted_count} old search events, " f"deactivated {deactivated_count} stale associations")

    except Exception as e:
        logger.error(f"Error cleaning up old data: {e}")
