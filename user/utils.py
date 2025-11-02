"""
Utility functions for login protection and rate limiting.
These functions can be used for testing, debugging, and manual administration.
"""

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from user.models import LoginAttempt


class LoginProtectionUtils:
    """
    Utility class for managing login protection features.
    """

    @staticmethod
    def get_ip_status(ip_address):
        """
        Get comprehensive status information for an IP address.

        Returns:
            dict: Status information including attempt counts, blocking status, etc.
        """
        failed_attempts_15min = LoginAttempt.get_failed_attempts_for_ip(ip_address, minutes=15)
        failed_attempts_60min = LoginAttempt.get_failed_attempts_for_ip(ip_address, minutes=60)
        failed_attempts_24h = LoginAttempt.get_failed_attempts_for_ip(ip_address, minutes=1440)

        is_blocked = LoginAttempt.is_ip_blocked(ip_address, max_attempts=10, minutes=15)

        # Get rate limit info from cache
        rate_limit_key = f"rate_limit:{ip_address}:/api/login/"
        rate_limit_requests = cache.get(rate_limit_key, [])
        current_rate_limit_count = len(rate_limit_requests)

        return {
            "ip_address": ip_address,
            "failed_attempts_15min": failed_attempts_15min,
            "failed_attempts_60min": failed_attempts_60min,
            "failed_attempts_24h": failed_attempts_24h,
            "is_blocked": is_blocked,
            "rate_limit_requests_current": current_rate_limit_count,
            "max_attempts_before_block": 10,
            "attempts_until_block": max(0, 10 - failed_attempts_15min),
            "status": "BLOCKED" if is_blocked else "ACTIVE",
        }

    @staticmethod
    def get_user_status(username):
        """
        Get comprehensive status information for a username.

        Returns:
            dict: Status information including attempt counts, lockout status, etc.
        """
        failed_attempts_15min = LoginAttempt.get_failed_attempts_for_user(username, minutes=15)
        failed_attempts_60min = LoginAttempt.get_failed_attempts_for_user(username, minutes=60)
        failed_attempts_24h = LoginAttempt.get_failed_attempts_for_user(username, minutes=1440)

        is_locked = LoginAttempt.is_user_locked(username, max_attempts=3, minutes=15)
        remaining_lockout_time = LoginAttempt.get_lockout_time_remaining(username, minutes=15)

        return {
            "username": username,
            "failed_attempts_15min": failed_attempts_15min,
            "failed_attempts_60min": failed_attempts_60min,
            "failed_attempts_24h": failed_attempts_24h,
            "is_locked": is_locked,
            "remaining_lockout_seconds": remaining_lockout_time,
            "max_attempts_before_lock": 3,
            "attempts_until_lock": max(0, 3 - failed_attempts_15min),
            "status": "LOCKED" if is_locked else "ACTIVE",
        }

    @staticmethod
    def unblock_ip(ip_address):
        """
        Manually unblock an IP address by clearing its failed attempts.

        Returns:
            int: Number of attempts cleared
        """
        attempts = LoginAttempt.objects.filter(ip_address=ip_address, attempt_type="login_failed")
        count = attempts.count()
        attempts.delete()

        # Also clear rate limit cache
        rate_limit_key = f"rate_limit:{ip_address}:/api/login/"
        cache.delete(rate_limit_key)

        return count

    @staticmethod
    def unlock_user(username):
        """
        Manually unlock a user account by clearing its failed attempts.

        Returns:
            int: Number of attempts cleared
        """
        attempts = LoginAttempt.objects.filter(username=username, attempt_type="login_failed")
        count = attempts.count()
        attempts.delete()
        return count

    @staticmethod
    def get_security_stats():
        """
        Get overall security statistics.

        Returns:
            dict: Security statistics
        """
        now = timezone.now()
        last_15min = now - timedelta(minutes=15)
        last_hour = now - timedelta(hours=1)
        last_24h = now - timedelta(hours=24)

        stats = {
            "total_attempts": LoginAttempt.objects.count(),
            "attempts_last_15min": LoginAttempt.objects.filter(
                timestamp__gte=last_15min, attempt_type="login_failed"
            ).count(),
            "attempts_last_hour": LoginAttempt.objects.filter(timestamp__gte=last_hour, attempt_type="login_failed").count(),
            "attempts_last_24h": LoginAttempt.objects.filter(timestamp__gte=last_24h, attempt_type="login_failed").count(),
            "unique_ips_last_24h": LoginAttempt.objects.filter(timestamp__gte=last_24h)
            .values("ip_address")
            .distinct()
            .count(),
            "unique_users_last_24h": LoginAttempt.objects.filter(timestamp__gte=last_24h, username__isnull=False)
            .values("username")
            .distinct()
            .count(),
        }

        # Calculate currently blocked IPs and locked users
        all_ips = LoginAttempt.objects.filter(timestamp__gte=last_15min).values_list("ip_address", flat=True).distinct()

        blocked_ips = [ip for ip in all_ips if LoginAttempt.is_ip_blocked(ip, max_attempts=10, minutes=15)]

        all_users = (
            LoginAttempt.objects.filter(timestamp__gte=last_15min, username__isnull=False)
            .values_list("username", flat=True)
            .distinct()
        )

        locked_users = [user for user in all_users if LoginAttempt.is_user_locked(user, max_attempts=3, minutes=15)]

        stats.update(
            {
                "currently_blocked_ips": len(blocked_ips),
                "currently_locked_users": len(locked_users),
                "blocked_ip_list": list(blocked_ips),
                "locked_user_list": list(locked_users),
            }
        )

        return stats

    @staticmethod
    def clear_all_rate_limits():
        """
        Clear all rate limit caches. Use with caution!

        Returns:
            bool: True if successful
        """
        try:
            # This is a simple approach - in production you might want to be more selective
            cache.clear()
            return True
        except Exception:
            return False


# Convenience functions for Django shell usage
def ip_status(ip_address):
    """Get IP status - convenience function for Django shell"""
    return LoginProtectionUtils.get_ip_status(ip_address)


def user_status(username):
    """Get user status - convenience function for Django shell"""
    return LoginProtectionUtils.get_user_status(username)


def unblock_ip(ip_address):
    """Unblock IP - convenience function for Django shell"""
    return LoginProtectionUtils.unblock_ip(ip_address)


def unlock_user(username):
    """Unlock user - convenience function for Django shell"""
    return LoginProtectionUtils.unlock_user(username)


def security_stats():
    """Get security stats - convenience function for Django shell"""
    return LoginProtectionUtils.get_security_stats()


def trigger_cleanup_task(minutes=15):
    """Trigger the Celery cleanup task manually - convenience function for Django shell"""
    try:
        from .tasks import cleanup_login_attempts_task

        result = cleanup_login_attempts_task.delay(minutes=minutes)
        return {
            "task_id": result.id,
            "status": "triggered",
            "message": f"Cleanup task triggered for attempts older than {minutes} minutes",
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to trigger cleanup task: {str(e)}"}


def trigger_security_stats_task():
    """Trigger the security stats generation task manually"""
    try:
        from .tasks import get_login_security_stats_task

        result = get_login_security_stats_task.delay()
        return {"task_id": result.id, "status": "triggered", "message": "Security stats task triggered"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to trigger security stats task: {str(e)}"}
