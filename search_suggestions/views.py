import logging
from datetime import timedelta

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SearchEvent
from .services.suggestion_service import SearchSuggestionService
from .tasks import track_search_event, track_suggestion_click

logger = logging.getLogger(__name__)


class SearchSuggestionsAPIView(APIView):
    """
    API endpoint for 'Customers Also Searched For' suggestions
    """

    permission_classes = [AllowAny]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.suggestion_service = SearchSuggestionService()

    def get(self, request):
        """
        Get search suggestions

        Parameters:
        - query: Search query (required)
        - limit: Number of suggestions (default: 5)
        - include_metrics: Include detailed metrics (default: false)
        """
        query = request.GET.get("query", "").strip()

        if not query or len(query) < 2:
            return Response(
                {"error": "Query parameter is required", "message": "Query must be at least 2 characters long"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = min(int(request.GET.get("limit", 5)), 10)
            include_metrics = request.GET.get("include_metrics", "false").lower() == "true"

            # Get user info
            user_id = None
            if request.user.is_authenticated:
                user_id = str(request.user.id)

            # Get session ID
            session_id = request.session.session_key
            if not session_id:
                request.session.create()
                session_id = request.session.session_key

            # Get suggestions
            suggestions = self.suggestion_service.get_suggestions(query=query, user_id=user_id, limit=limit)

            # Track this search event asynchronously using Celery task
            track_search_event.delay(
                session_id=session_id,
                user_id=user_id,
                query=query,
                device_type=self._get_device_type(request),
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )

            # Prepare response
            response_data = {
                "query": query,
                "normalized_query": self.suggestion_service.normalize_query(query),
                "suggestions": [
                    {"query": s["query"], "type": s["type"], "reason": s["reason"], "confidence": round(s["confidence"], 2)}
                    for s in suggestions
                ],
                "count": len(suggestions),
                "generated_at": timezone.now().isoformat(),
            }

            if include_metrics:
                response_data["suggestions"] = suggestions  # Include full data

            return Response(response_data)

        except Exception as e:
            logger.error(f"Error in SearchSuggestionsAPIView: {e}")
            return Response(
                {"error": "Internal server error", "message": "Unable to process request"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @staticmethod
    def _get_device_type(request):
        """Extract device type from user agent"""
        user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
        if "mobile" in user_agent:
            return "mobile"
        elif "tablet" in user_agent or "ipad" in user_agent:
            return "tablet"
        else:
            return "desktop"

    @staticmethod
    def _get_client_ip(request):
        """Get client IP address"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class SuggestionClickAPIView(APIView):
    """
    API to track clicks on suggested queries
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """
        Track when a user clicks on a suggested query

        Request body:
        {
            "source_query": "original search query",
            "clicked_query": "suggested query that was clicked",
            "position": 1,  # Position in list (1-indexed)
            "session_id": "optional session id"
        }
        """
        try:
            data = request.data
            source_query = data.get("source_query", "").strip()
            clicked_query = data.get("clicked_query", "").strip()

            if not source_query or not clicked_query:
                return Response(
                    {"error": "Missing required fields", "required": ["source_query", "clicked_query"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get session ID
            session_id = data.get("session_id") or request.session.session_key
            if not session_id and request.session.session_key:
                session_id = request.session.session_key

            # Get user ID
            user_id = None
            if request.user.is_authenticated:
                user_id = str(request.user.id)

            # Update click stats asynchronously using Celery task
            track_suggestion_click.delay(
                source_query=source_query,
                clicked_query=clicked_query,
                position=data.get("position"),
                user_id=user_id,
                session_id=session_id,
            )

            return Response(
                {
                    "status": "success",
                    "message": "Click tracked successfully",
                    "data": {
                        "source_query": source_query,
                        "clicked_query": clicked_query,
                        "position": data.get("position"),
                        "tracked_at": timezone.now().isoformat(),
                    },
                }
            )

        except Exception as e:
            logger.error(f"Error in SuggestionClickAPIView: {e}")
            return Response(
                {"error": "Internal server error", "message": "Unable to track click"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SearchAnalyticsAPIView(APIView):
    """
    API to get search analytics (admin only)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get search analytics

        Parameters:
        - days: Number of days to look back (default: 7)
        - top_n: Number of top queries to return (default: 10)
        """
        if not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            days = int(request.GET.get("days", 7))
            top_n = int(request.GET.get("top_n", 10))

            from datetime import datetime

            from django.db.models import Avg, Count, Q, Sum
            from django.db.models.functions import TruncDate

            # Date range
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)

            # Overall statistics
            total_searches = SearchEvent.objects.filter(created_at__range=[start_date, end_date]).count()

            unique_users = (
                SearchEvent.objects.filter(created_at__range=[start_date, end_date], user_id__isnull=False)
                .values("user_id")
                .distinct()
                .count()
            )

            unique_sessions = (
                SearchEvent.objects.filter(created_at__range=[start_date, end_date]).values("session_id").distinct().count()
            )

            click_through_rate = (
                SearchEvent.objects.filter(created_at__range=[start_date, end_date]).aggregate(ctr=Avg("has_click"))["ctr"]
                or 0
            )

            conversion_rate = (
                SearchEvent.objects.filter(created_at__range=[start_date, end_date]).aggregate(cr=Avg("has_purchase"))["cr"]
                or 0
            )

            # Top queries
            top_queries = (
                SearchEvent.objects.filter(created_at__range=[start_date, end_date])
                .values("normalized_query")
                .annotate(total=Count("id"), clicks=Sum("has_click"), purchases=Sum("has_purchase"))
                .order_by("-total")[:top_n]
            )

            # Daily trends
            daily_trends = (
                SearchEvent.objects.filter(created_at__range=[start_date, end_date])
                .annotate(date=TruncDate("created_at"))
                .values("date")
                .annotate(count=Count("id"), clicks=Sum("has_click"), purchases=Sum("has_purchase"))
                .order_by("date")
            )

            # Prepare response
            response_data = {
                "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "days": days},
                "overall": {
                    "total_searches": total_searches,
                    "unique_users": unique_users,
                    "unique_sessions": unique_sessions,
                    "click_through_rate": round(click_through_rate, 4),
                    "conversion_rate": round(conversion_rate, 4),
                },
                "top_queries": [
                    {
                        "query": item["normalized_query"],
                        "total_searches": item["total"],
                        "clicks": item["clicks"],
                        "purchases": item["purchases"],
                        "ctr": round(item["clicks"] / item["total"] if item["total"] > 0 else 0, 4),
                        "conversion_rate": round(item["purchases"] / item["clicks"] if item["clicks"] > 0 else 0, 4),
                    }
                    for item in top_queries
                ],
                "daily_trends": [
                    {
                        "date": item["date"].isoformat() if item["date"] else None,
                        "searches": item["count"],
                        "clicks": item["clicks"],
                        "purchases": item["purchases"],
                    }
                    for item in daily_trends
                ],
            }

            return Response(response_data)

        except Exception as e:
            logger.error(f"Error in SearchAnalyticsAPIView: {e}")
            return Response(
                {"error": "Internal server error", "message": "Unable to fetch analytics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CacheManagementAPIView(APIView):
    """
    API for cache management (admin only)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get cache statistics
        """
        if not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            from django_redis import get_redis_connection

            redis_client = get_redis_connection("default")

            # Get cache stats
            pattern = "search_suggestions:*"
            keys = redis_client.keys(pattern)
            total_keys = len(keys)

            # Get hit statistics
            hits = redis_client.zrevrange("suggestion_cache:hits", 0, 9, withscores=True)

            # Calculate cache size
            cache_size = 0
            if keys:
                pipeline = redis_client.pipeline()
                for key in keys[:10]:  # Sample first 10 keys
                    pipeline.memory_usage(key)
                sizes = pipeline.execute()
                cache_size = sum([size for size in sizes if size])

            # Prepare response
            response_data = {
                "cache_stats": {
                    "total_cached_queries": total_keys,
                    "estimated_size_bytes": cache_size,
                    "cache_ttl_seconds": 3600,
                    "sample_size_checked": min(10, total_keys),
                },
                "top_hits": (
                    [{"key": key.decode() if isinstance(key, bytes) else key, "hits": int(score)} for key, score in hits]
                    if hits
                    else []
                ),
            }

            return Response(response_data)

        except Exception as e:
            logger.error(f"Error in CacheManagementAPIView: {e}")
            return Response(
                {"error": "Internal server error", "message": "Unable to fetch cache statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        """
        Clear cache or warm up cache
        """
        if not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        try:
            action = request.data.get("action", "")

            if action == "clear":
                from django_redis import get_redis_connection

                redis_client = get_redis_connection("default")

                # Delete all search suggestion cache keys
                keys = redis_client.keys("search_suggestions:*")
                if keys:
                    deleted = redis_client.delete(*keys)
                    return Response(
                        {
                            "status": "success",
                            "message": f"Successfully cleared {deleted} cache entries",
                            "cleared_count": deleted,
                        }
                    )
                else:
                    return Response({"status": "success", "message": "Cache is already empty", "cleared_count": 0})

            elif action == "warmup":
                from .tasks import warmup_cache

                limit = request.data.get("limit", 50)
                task = warmup_cache.delay(int(limit))

                return Response(
                    {"status": "success", "message": f"Cache warmup initiated for {limit} queries", "task_id": task.id}
                )

            elif action == "update_stats":
                from .tasks import update_query_associations, update_query_popularity

                # Run both update tasks
                popularity_task = update_query_popularity.delay()
                associations_task = update_query_associations.delay()

                return Response(
                    {
                        "status": "success",
                        "message": "Statistics update initiated",
                        "tasks": {"popularity_update": popularity_task.id, "associations_update": associations_task.id},
                    }
                )

            else:
                return Response(
                    {"error": "Invalid action", "valid_actions": ["clear", "warmup", "update_stats"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except Exception as e:
            logger.error(f"Error in CacheManagementAPIView POST: {e}")
            return Response(
                {"error": "Internal server error", "message": "Unable to perform cache operation"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class HealthCheckAPIView(APIView):
    """
    Health check endpoint for search suggestions
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """
        Check health of search suggestion system
        """
        try:
            from django.db import connection
            from django_redis import get_redis_connection

            from .models import QueryAssociation, QueryPopularity

            # Check database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                db_ok = cursor.fetchone()[0] == 1

            # Check Redis connection
            redis_client = get_redis_connection("default")
            redis_ok = redis_client.ping()

            # Check data
            total_queries = QueryPopularity.objects.count()
            total_associations = QueryAssociation.objects.count()

            # Test suggestion service
            suggestion_service = SearchSuggestionService()
            test_suggestions = suggestion_service.get_suggestions("test", limit=1)

            health_status = {
                "status": "healthy",
                "timestamp": timezone.now().isoformat(),
                "components": {
                    "database": "ok" if db_ok else "error",
                    "redis": "ok" if redis_ok else "error",
                    "suggestion_service": "ok" if test_suggestions is not None else "error",
                },
                "data_stats": {"total_queries": total_queries, "total_associations": total_associations},
                "cache_stats": {
                    "ttl_seconds": suggestion_service.cache_ttl,
                    "min_cooccurrence": suggestion_service.min_cooccurrence,
                },
            }

            # Overall status
            all_ok = all([db_ok, redis_ok, test_suggestions is not None])

            if not all_ok:
                health_status["status"] = "degraded"

            return Response(health_status)

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return Response(
                {"status": "unhealthy", "timestamp": timezone.now().isoformat(), "error": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
