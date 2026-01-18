import json
import logging
from datetime import timedelta

from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)


@shared_task(name="search_suggestions.update_query_associations")
def update_query_associations():
    """
    Periodically update query associations from search events
    Runs every hour
    """
    try:
        logger.info("Starting query associations update...")

        cutoff_time = timezone.now() - timedelta(days=7)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH session_pairs AS (
                    SELECT DISTINCT 
                        se1.query_hash as query1_hash,
                        se1.normalized_query as query1,
                        se2.query_hash as query2_hash,
                        se2.normalized_query as query2,
                        se1.session_id
                    FROM search_events se1
                    INNER JOIN search_events se2 ON se1.session_id = se2.session_id
                    WHERE se1.created_at >= %s
                    AND se2.created_at >= %s
                    AND se1.query_hash != se2.query_hash
                    AND se1.created_at BETWEEN se2.created_at - INTERVAL '1 hour' 
                                         AND se2.created_at + INTERVAL '1 hour'
                    AND se1.normalized_query != ''
                    AND se2.normalized_query != ''
                )
                INSERT INTO search_suggestions_queryassociation 
                    (source_query, source_query_hash, target_query, target_query_hash,
                     co_occurrence_count, session_co_occurrence, last_occurrence,
                     association_type, confidence_score, is_active)
                SELECT 
                    query1, query1_hash, query2, query2_hash,
                    COUNT(DISTINCT session_id),
                    COUNT(DISTINCT session_id),
                    NOW(),
                    'co_search',
                    CASE 
                        WHEN COUNT(DISTINCT session_id) >= 10 THEN 0.9
                        WHEN COUNT(DISTINCT session_id) >= 5 THEN 0.7
                        WHEN COUNT(DISTINCT session_id) >= 2 THEN 0.5
                        ELSE 0.3
                    END,
                    TRUE
                FROM session_pairs
                GROUP BY query1, query1_hash, query2, query2_hash
                HAVING COUNT(DISTINCT session_id) >= 2
                ON CONFLICT (source_query_hash, target_query_hash) 
                DO UPDATE SET
                    co_occurrence_count = EXCLUDED.co_occurrence_count,
                    session_co_occurrence = EXCLUDED.session_co_occurrence,
                    last_occurrence = NOW(),
                    confidence_score = EXCLUDED.confidence_score,
                    is_active = TRUE
            """,
                [cutoff_time, cutoff_time],
            )

            # Update CTR and conversion metrics
            cursor.execute(
                """
                UPDATE search_suggestions_queryassociation qa
                SET 
                    source_to_target_ctr = COALESCE((
                        SELECT 
                            CASE WHEN COUNT(*) > 0 THEN
                                SUM(CASE WHEN se2.has_click THEN 1.0 ELSE 0.0 END) / COUNT(*)
                            ELSE 0 END
                        FROM search_events se1
                        INNER JOIN search_events se2 ON se1.session_id = se2.session_id
                        WHERE se1.query_hash = qa.source_query_hash
                        AND se2.query_hash = qa.target_query_hash
                        AND se1.created_at >= %s
                        AND se2.created_at > se1.created_at
                        AND se2.created_at <= se1.created_at + INTERVAL '1 hour'
                    ), 0.0),
                    conversion_rate = COALESCE((
                        SELECT 
                            CASE WHEN COUNT(*) > 0 THEN
                                SUM(CASE WHEN se2.has_purchase THEN 1.0 ELSE 0.0 END) / COUNT(*)
                            ELSE 0 END
                        FROM search_events se1
                        INNER JOIN search_events se2 ON se1.session_id = se2.session_id
                        WHERE se1.query_hash = qa.source_query_hash
                        AND se2.query_hash = qa.target_query_hash
                        AND se1.created_at >= %s
                        AND se2.created_at > se1.created_at
                        AND se2.created_at <= se1.created_at + INTERVAL '1 hour'
                    ), 0.0),
                    decay_score = EXP(-EXTRACT(EPOCH FROM (NOW() - last_occurrence)) / (30 * 24 * 3600.0))
                WHERE qa.co_occurrence_count > 0
                AND qa.last_occurrence >= %s
            """,
                [cutoff_time, cutoff_time, cutoff_time],
            )

            rows_updated = cursor.rowcount
            logger.info(f"Updated {rows_updated} query associations")

        # Clear stale cache entries
        clear_stale_cache.delay()

        logger.info("Query associations update completed successfully")
        return rows_updated

    except Exception as e:
        logger.error(f"Error updating query associations: {e}")
        raise


@shared_task(name="search_suggestions.update_query_popularity")
def update_query_popularity():
    """
    Update query popularity statistics
    Runs every 15 minutes
    """
    try:
        logger.info("Starting query popularity update...")

        from search_suggestions.models import QueryPopularity

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=now.weekday())
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH search_stats AS (
                        SELECT 
                            query_hash,
                            normalized_query,
                            COUNT(*) as total_searches,
                            COUNT(DISTINCT session_id) as unique_sessions,
                            COUNT(DISTINCT user_id) as unique_users,
                            COUNT(CASE WHEN created_at >= %s THEN 1 END) as searches_today,
                            COUNT(CASE WHEN created_at >= %s THEN 1 END) as searches_week,
                            COUNT(CASE WHEN created_at >= %s THEN 1 END) as searches_month,
                            SUM(CASE WHEN has_click THEN 1 ELSE 0 END) as total_clicks,
                            SUM(CASE WHEN has_purchase THEN 1 ELSE 0 END) as total_purchases,
                            AVG(CASE WHEN has_click THEN click_position::float END) as avg_click_position
                        FROM search_events
                        WHERE created_at >= %s
                        AND normalized_query != ''
                        GROUP BY query_hash, normalized_query
                    )
                    INSERT INTO search_suggestions_querypopularity 
                        (query_hash, query, total_searches, unique_users, unique_sessions,
                         searches_today, searches_this_week, searches_this_month,
                         total_clicks, total_purchases, click_through_rate, conversion_rate,
                         avg_click_position, last_seen)
                    SELECT 
                        query_hash,
                        normalized_query,
                        total_searches,
                        unique_users,
                        unique_sessions,
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
                        COALESCE(avg_click_position, 0),
                        NOW()
                    FROM search_stats
                    ON CONFLICT (query_hash) 
                    DO UPDATE SET
                        total_searches = EXCLUDED.total_searches,
                        unique_users = EXCLUDED.unique_users,
                        unique_sessions = EXCLUDED.unique_sessions,
                        searches_today = EXCLUDED.searches_today,
                        searches_this_week = EXCLUDED.searches_week,
                        searches_this_month = EXCLUDED.searches_month,
                        total_clicks = EXCLUDED.total_clicks,
                        total_purchases = EXCLUDED.total_purchases,
                        click_through_rate = EXCLUDED.click_through_rate,
                        conversion_rate = EXCLUDED.conversion_rate,
                        avg_click_position = EXCLUDED.avg_click_position,
                        last_seen = NOW(),
                        trending_score = (
                            CASE 
                                WHEN search_suggestions_querypopularity.searches_today > 0 
                                THEN EXCLUDED.searches_today::float / 
                                     NULLIF(search_suggestions_querypopularity.searches_today, 0)
                                ELSE 1.0
                            END * 
                            CASE 
                                WHEN EXCLUDED.searches_week > 0 
                                THEN EXCLUDED.searches_today::float / 
                                     NULLIF(EXCLUDED.searches_week, 0) * 7
                                ELSE 1.0
                            END
                        ),
                        trend_direction = CASE 
                            WHEN EXCLUDED.searches_today > search_suggestions_querypopularity.searches_today * 1.2 
                            THEN 'up'
                            WHEN EXCLUDED.searches_today < search_suggestions_querypopularity.searches_today * 0.8 
                            THEN 'down'
                            ELSE 'stable'
                        END
                """,
                    [today_start, week_start, month_start, now - timedelta(days=90)],  # 90-day lookback
                )

                rows_updated = cursor.rowcount
                logger.info(f"Updated {rows_updated} query popularity entries")

                # Update categories for queries
                cursor.execute(
                    """
                    UPDATE search_suggestions_querypopularity qp
                    SET 
                        primary_category = (
                            SELECT p.category_id
                            FROM products_product p
                            WHERE LOWER(p.name) LIKE '%' || LOWER(qp.query) || '%'
                            OR LOWER(qp.query) LIKE '%' || LOWER(p.name) || '%'
                            LIMIT 1
                        )
                    WHERE qp.primary_category IS NULL
                    AND qp.total_searches >= 10
                """
                )

        logger.info("Query popularity update completed successfully")
        return rows_updated

    except Exception as e:
        logger.error(f"Error updating query popularity: {e}")
        raise


@shared_task(name="search_suggestions.clear_stale_cache")
def clear_stale_cache():
    """
    Clear stale cache entries
    Runs daily
    """
    try:
        logger.info("Clearing stale cache entries...")

        redis_client = get_redis_connection("default")

        # Clear expired suggestion cache entries
        pattern = "search_suggestions:*"
        keys = redis_client.keys(pattern)

        if keys:
            # Check TTL for each key and delete if expired or stale
            pipeline = redis_client.pipeline()
            for key in keys:
                pipeline.ttl(key)

            ttls = pipeline.execute()

            deleted_count = 0
            for key, ttl in zip(keys, ttls):
                if ttl <= 0 or ttl > 7200:  # TTL > 2 hours (stale) or expired
                    redis_client.delete(key)
                    deleted_count += 1

            logger.info(f"Cleared {deleted_count} stale cache entries")
        else:
            logger.info("No cache entries to clear")

        return True

    except Exception as e:
        logger.error(f"Error clearing stale cache: {e}")
        return False


@shared_task(name="search_suggestions.cleanup_old_data")
def cleanup_old_data():
    """
    Clean up old search data
    Runs weekly
    """
    try:
        logger.info("Cleaning up old search data...")

        from search_suggestions.models import QueryAssociation, SearchEvent

        # Delete old search events (keep 180 days)
        cutoff = timezone.now() - timedelta(days=180)
        deleted_count, _ = SearchEvent.objects.filter(created_at__lt=cutoff).delete()

        # Deactivate stale associations (no activity in 60 days)
        stale_cutoff = timezone.now() - timedelta(days=60)
        deactivated_count = QueryAssociation.objects.filter(
            last_occurrence__lt=stale_cutoff, co_occurrence_count__lt=5
        ).update(is_active=False)

        # Remove very low confidence associations
        removed_count = QueryAssociation.objects.filter(confidence_score__lt=0.1, co_occurrence_count__lt=3).delete()[0]

        logger.info(
            f"Cleaned up {deleted_count} old search events, "
            f"deactivated {deactivated_count} stale associations, "
            f"removed {removed_count} low confidence associations"
        )

        return {
            "deleted_events": deleted_count,
            "deactivated_associations": deactivated_count,
            "removed_associations": removed_count,
        }

    except Exception as e:
        logger.error(f"Error cleaning up old data: {e}")
        raise


@shared_task(name="search_suggestions.warmup_cache")
def warmup_cache(limit: int = 50):
    """
    Warm up cache with popular queries
    Can be triggered manually or on schedule
    """
    try:
        logger.info(f"Warming up cache with {limit} popular queries...")

        from search_suggestions.models import QueryPopularity
        from search_suggestions.services.suggestion_service import (
            SearchSuggestionService,
        )

        redis_client = get_redis_connection("default")
        suggestion_service = SearchSuggestionService()

        # Get popular queries
        popular_queries = QueryPopularity.objects.filter(total_searches__gte=20).order_by(
            "-total_searches", "-trending_score"
        )[:limit]

        cached_count = 0
        pipeline = redis_client.pipeline()

        for query_pop in popular_queries:
            try:
                # Generate suggestions
                suggestions = suggestion_service._generate_suggestions(query_pop.query, user_id=None)

                if suggestions:
                    cache_key = f"search_suggestions:{suggestion_service.get_query_hash(query_pop.query)}"

                    # Add to pipeline
                    pipeline.setex(cache_key, suggestion_service.cache_ttl, json.dumps(suggestions[:5]))
                    cached_count += 1

            except Exception as e:
                logger.error(f"Error caching query {query_pop.query}: {e}")

        # Execute all cache operations in batch
        if cached_count > 0:
            pipeline.execute()

        logger.info(f"Successfully warmed up cache with {cached_count} queries")
        return cached_count

    except Exception as e:
        logger.error(f"Error warming up cache: {e}")
        return 0


@shared_task(name="search_suggestions.track_search_event")
def track_search_event(session_id, user_id, query, device_type, ip_address, user_agent):
    """
    Track search event asynchronously
    Called from API views
    """
    try:
        from search_suggestions.models import SearchEvent

        SearchEvent.objects.create(
            session_id=session_id,
            user_id=user_id,
            original_query=query,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else "",
            created_at=timezone.now(),
        )

        # Update Redis counter for real-time trending
        redis_client = get_redis_connection("default")
        today_key = f"search_stats:today:{timezone.now().strftime('%Y-%m-%d')}"
        redis_client.hincrby(today_key, query.lower(), 1)
        redis_client.expire(today_key, 86400)  # 1 day

        return True

    except Exception as e:
        logger.error(f"Error tracking search event: {e}")
        return False


@shared_task(name="search_suggestions.track_suggestion_click")
def track_suggestion_click(source_query, clicked_query, position, user_id, session_id):
    """
    Track suggestion clicks asynchronously
    Called from API views
    """
    try:
        from search_suggestions.models import SearchEvent

        # Create search event for clicked query
        SearchEvent.objects.create(
            session_id=session_id or "anonymous",
            user_id=user_id,
            original_query=clicked_query,
            has_click=True,
            click_position=position,
            created_at=timezone.now(),
        )

        # Update Redis click counter
        redis_client = get_redis_connection("default")
        click_key = f"suggestion_clicks:{source_query.lower()}"
        redis_client.hincrby(click_key, clicked_query.lower(), 1)
        redis_client.expire(click_key, 2592000)  # 30 days

        # Update CTR in Redis for real-time updates
        ctr_key = f"suggestion_ctr:{source_query.lower()}:{clicked_query.lower()}"
        redis_client.incr(f"{ctr_key}:clicks")
        redis_client.incr(f"{ctr_key}:impressions")
        redis_client.expire(ctr_key, 604800)  # 7 days

        logger.info(f"Tracked click: {source_query} → {clicked_query} (pos: {position})")
        return True

    except Exception as e:
        logger.error(f"Error tracking suggestion click: {e}")
        return False


@shared_task(name="search_suggestions.generate_daily_report")
def generate_daily_report():
    """
    Generate daily search analytics report
    Runs daily at midnight
    """
    try:
        logger.info("Generating daily search analytics report...")

        from datetime import datetime
        from io import BytesIO

        import pandas as pd
        from django.conf import settings
        from django.core.mail import EmailMessage
        from django.db.models import Avg, Count, Sum

        from search_suggestions.models import SearchEvent

        yesterday = timezone.now() - timedelta(days=1)
        yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Get yesterday's statistics
        stats = {
            "date": yesterday.date(),
            "total_searches": SearchEvent.objects.filter(created_at__range=[yesterday_start, yesterday_end]).count(),
            "unique_users": SearchEvent.objects.filter(created_at__range=[yesterday_start, yesterday_end])
            .values("user_id")
            .distinct()
            .count(),
            "unique_sessions": SearchEvent.objects.filter(created_at__range=[yesterday_start, yesterday_end])
            .values("session_id")
            .distinct()
            .count(),
            "click_through_rate": SearchEvent.objects.filter(created_at__range=[yesterday_start, yesterday_end]).aggregate(
                ctr=Avg("has_click")
            )["ctr"]
            or 0,
            "conversion_rate": SearchEvent.objects.filter(created_at__range=[yesterday_start, yesterday_end]).aggregate(
                cr=Avg("has_purchase")
            )["cr"]
            or 0,
        }

        # Get top 10 queries
        top_queries = (
            SearchEvent.objects.filter(created_at__range=[yesterday_start, yesterday_end])
            .values("normalized_query")
            .annotate(count=Count("id"), clicks=Sum("has_click"), purchases=Sum("has_purchase"))
            .order_by("-count")[:10]
        )

        # Generate CSV report
        df_stats = pd.DataFrame([stats])
        df_queries = pd.DataFrame(list(top_queries))

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_stats.to_excel(writer, sheet_name="Summary", index=False)
            df_queries.to_excel(writer, sheet_name="Top Queries", index=False)

        output.seek(0)

        # Send email report
        email = EmailMessage(
            subject=f"Search Analytics Report - {yesterday.date()}",
            body=f"Daily search analytics attached.\n\nSummary:\n"
            f"Total Searches: {stats['total_searches']}\n"
            f"Unique Users: {stats['unique_users']}\n"
            f"Click-Through Rate: {stats['click_through_rate']:.2%}\n"
            f"Conversion Rate: {stats['conversion_rate']:.2%}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[admin[1] for admin in settings.ADMINS],
        )
        email.attach(
            f"search_report_{yesterday.date()}.xlsx",
            output.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        email.send()

        logger.info("Daily search report generated and sent successfully")
        return True

    except Exception as e:
        logger.error(f"Error generating daily report: {e}")
        return False
