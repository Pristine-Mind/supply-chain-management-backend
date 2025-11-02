"""
Celery tasks for user-related operations including login attempt cleanup.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.core.management import call_command
from django.utils import timezone

from .models import LoginAttempt

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def cleanup_login_attempts_task(self, minutes=15):
    """
    Celery task to clean up expired login attempts.

    Args:
        minutes (int): Delete login attempts older than this many minutes

    Returns:
        dict: Task execution results
    """
    try:
        logger.info(f"Starting login attempts cleanup for attempts older than {minutes} minutes")

        # Count attempts before cleanup
        time_threshold = timezone.now() - timedelta(minutes=minutes)
        expired_count = LoginAttempt.objects.filter(timestamp__lt=time_threshold).count()

        if expired_count == 0:
            logger.info("No expired login attempts found")
            return {
                "status": "success",
                "message": "No expired login attempts to clean up",
                "deleted_count": 0,
                "remaining_count": LoginAttempt.objects.count(),
            }

        # Perform cleanup using the model method
        deleted_count = LoginAttempt.clear_expired_attempts(minutes=minutes)
        remaining_count = LoginAttempt.objects.count()

        logger.info(f"Successfully cleaned up {deleted_count} expired login attempts. {remaining_count} attempts remaining.")

        return {
            "status": "success",
            "message": f"Successfully cleaned up {deleted_count} expired login attempts",
            "deleted_count": deleted_count,
            "remaining_count": remaining_count,
            "threshold_minutes": minutes,
        }

    except Exception as exc:
        logger.error(f"Login attempts cleanup failed: {str(exc)}")

        # Retry the task up to 3 times with exponential backoff
        if self.request.retries < self.max_retries:
            # Retry after 60, 120, 180 seconds
            retry_countdown = 60 * (self.request.retries + 1)
            logger.info(f"Retrying login cleanup task in {retry_countdown} seconds (attempt {self.request.retries + 1})")
            raise self.retry(countdown=retry_countdown, exc=exc)

        # Final failure after all retries
        return {
            "status": "error",
            "message": f"Login attempts cleanup failed after {self.max_retries} retries: {str(exc)}",
            "deleted_count": 0,
            "error": str(exc),
        }


@shared_task
def cleanup_login_attempts_via_command_task(minutes=15, verbose=False):
    """
    Alternative task that uses the Django management command directly.

    Args:
        minutes (int): Delete login attempts older than this many minutes
        verbose (bool): Enable verbose output

    Returns:
        dict: Task execution results
    """
    try:
        logger.info(f"Running login attempts cleanup command for {minutes} minutes")

        # Count before cleanup
        time_threshold = timezone.now() - timedelta(minutes=minutes)
        expired_count = LoginAttempt.objects.filter(timestamp__lt=time_threshold).count()

        # Run the management command
        call_command("cleanup_login_attempts", minutes=minutes, verbosity=2 if verbose else 1)

        # Count after cleanup
        remaining_count = LoginAttempt.objects.count()
        deleted_count = expired_count  # Assuming all expired were deleted

        logger.info(f"Management command completed. Cleaned up {deleted_count} attempts.")

        return {
            "status": "success",
            "message": f"Management command completed successfully",
            "deleted_count": deleted_count,
            "remaining_count": remaining_count,
            "method": "management_command",
        }

    except Exception as exc:
        logger.error(f"Management command cleanup failed: {str(exc)}")
        return {"status": "error", "message": f"Management command cleanup failed: {str(exc)}", "error": str(exc)}


@shared_task
def get_login_security_stats_task():
    """
    Task to generate and log security statistics.

    Returns:
        dict: Security statistics
    """
    try:
        from .utils import LoginProtectionUtils

        stats = LoginProtectionUtils.get_security_stats()

        logger.info("Login security statistics generated:")
        logger.info(f"- Total attempts: {stats['total_attempts']}")
        logger.info(f"- Attempts last 15 min: {stats['attempts_last_15min']}")
        logger.info(f"- Attempts last hour: {stats['attempts_last_hour']}")
        logger.info(f"- Attempts last 24h: {stats['attempts_last_24h']}")
        logger.info(f"- Currently blocked IPs: {stats['currently_blocked_ips']}")
        logger.info(f"- Currently locked users: {stats['currently_locked_users']}")

        if stats["blocked_ip_list"]:
            logger.warning(f"Blocked IPs: {', '.join(stats['blocked_ip_list'])}")

        if stats["locked_user_list"]:
            logger.warning(f"Locked users: {', '.join(stats['locked_user_list'])}")

        return {"status": "success", "stats": stats}

    except Exception as exc:
        logger.error(f"Failed to generate security stats: {str(exc)}")
        return {"status": "error", "message": f"Failed to generate security stats: {str(exc)}", "error": str(exc)}


@shared_task
def emergency_unlock_user_task(username):
    """
    Emergency task to unlock a specific user account.

    Args:
        username (str): Username to unlock

    Returns:
        dict: Unlock results
    """
    try:
        from .utils import LoginProtectionUtils

        cleared_count = LoginProtectionUtils.unlock_user(username)

        logger.info(f"Emergency unlock for user '{username}': cleared {cleared_count} attempts")

        return {
            "status": "success",
            "message": f"Successfully unlocked user {username}",
            "cleared_attempts": cleared_count,
            "username": username,
        }

    except Exception as exc:
        logger.error(f"Emergency unlock failed for user '{username}': {str(exc)}")
        return {
            "status": "error",
            "message": f"Emergency unlock failed for user {username}: {str(exc)}",
            "username": username,
            "error": str(exc),
        }


@shared_task
def emergency_unblock_ip_task(ip_address):
    """
    Emergency task to unblock a specific IP address.

    Args:
        ip_address (str): IP address to unblock

    Returns:
        dict: Unblock results
    """
    try:
        from .utils import LoginProtectionUtils

        cleared_count = LoginProtectionUtils.unblock_ip(ip_address)

        logger.info(f"Emergency unblock for IP '{ip_address}': cleared {cleared_count} attempts")

        return {
            "status": "success",
            "message": f"Successfully unblocked IP {ip_address}",
            "cleared_attempts": cleared_count,
            "ip_address": ip_address,
        }

    except Exception as exc:
        logger.error(f"Emergency unblock failed for IP '{ip_address}': {str(exc)}")
        return {
            "status": "error",
            "message": f"Emergency unblock failed for IP {ip_address}: {str(exc)}",
            "ip_address": ip_address,
            "error": str(exc),
        }
