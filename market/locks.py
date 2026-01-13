import json
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.utils import timezone
from django_redis import get_redis_connection


class DistributedNegotiationLock:
    """
    Distributed lock for negotiations using Redis.
    Prevents concurrent access to the same negotiation.
    """

    def __init__(self):
        self.redis_client = get_redis_connection("default")
        self.lock_timeout = 300  # 5 minutes lock timeout
        self.retry_interval = 0.1  # 100ms
        self.max_retries = 30  # Max 3 seconds waiting

    def _get_lock_key(self, negotiation_id, user_id=None):
        """Generate Redis key for negotiation lock"""
        if user_id:
            return f"negotiation:{negotiation_id}:lock:{user_id}"
        return f"negotiation:{negotiation_id}:lock"

    def acquire_lock(self, negotiation_id, user_id, timeout=None):
        """
        Acquire a lock for a negotiation for a specific user.

        Args:
            negotiation_id: ID of the negotiation
            user_id: ID of the user acquiring the lock
            timeout: Lock timeout in seconds (default: 5 minutes)

        Returns:
            str: Lock identifier if acquired, None otherwise
        """
        if timeout is None:
            timeout = self.lock_timeout

        lock_id = str(uuid.uuid4())
        lock_key = self._get_lock_key(negotiation_id)

        # Try to acquire lock with retry mechanism
        for attempt in range(self.max_retries):
            # Set lock with NX (only if not exists) and EX (expire)
            acquired = self.redis_client.set(
                lock_key,
                json.dumps(
                    {"user_id": user_id, "lock_id": lock_id, "acquired_at": timezone.now().isoformat(), "timeout": timeout}
                ),
                nx=True,
                ex=timeout,
            )

            if acquired:
                # Set user-specific lock for viewing permissions
                user_lock_key = self._get_lock_key(negotiation_id, user_id)
                self.redis_client.set(user_lock_key, lock_id, ex=timeout)
                return lock_id

            # Check if current lock owner is the same user (lock renewal)
            lock_data = self.redis_client.get(lock_key)
            if lock_data:
                try:
                    data = json.loads(lock_data)
                    if data.get("user_id") == str(user_id):
                        # Renew lock for current user
                        self.redis_client.expire(lock_key, timeout)
                        self.redis_client.expire(self._get_lock_key(negotiation_id, user_id), timeout)
                        return data.get("lock_id")
                except (json.JSONDecodeError, KeyError):
                    pass

            time.sleep(self.retry_interval)

        return None

    def release_lock(self, negotiation_id, user_id, lock_id):
        """
        Release a negotiation lock.

        Args:
            negotiation_id: ID of the negotiation
            user_id: ID of the user releasing the lock
            lock_id: Lock identifier

        Returns:
            bool: True if released successfully, False otherwise
        """
        lock_key = self._get_lock_key(negotiation_id)
        user_lock_key = self._get_lock_key(negotiation_id, user_id)

        # Verify lock ownership
        lock_data = self.redis_client.get(lock_key)
        if not lock_data:
            return False

        try:
            data = json.loads(lock_data)
            if data.get("user_id") == str(user_id) and data.get("lock_id") == lock_id:
                # Delete both locks
                self.redis_client.delete(lock_key)
                self.redis_client.delete(user_lock_key)
                return True
        except (json.JSONDecodeError, KeyError):
            pass

        return False

    def check_lock_ownership(self, negotiation_id, user_id):
        """
        Check if a user owns the lock for a negotiation.

        Args:
            negotiation_id: ID of the negotiation
            user_id: ID of the user to check

        Returns:
            tuple: (is_owner, lock_data) or (False, None)
        """
        lock_key = self._get_lock_key(negotiation_id)
        lock_data = self.redis_client.get(lock_key)

        if not lock_data:
            return False, None

        try:
            data = json.loads(lock_data)
            return data.get("user_id") == str(user_id), data
        except (json.JSONDecodeError, KeyError):
            return False, None

    def get_lock_owner(self, negotiation_id):
        """
        Get the current lock owner for a negotiation.

        Args:
            negotiation_id: ID of the negotiation

        Returns:
            dict: Lock owner information or None
        """
        lock_key = self._get_lock_key(negotiation_id)
        lock_data = self.redis_client.get(lock_key)

        if not lock_data:
            return None

        try:
            return json.loads(lock_data)
        except json.JSONDecodeError:
            return None

    @contextmanager
    def negotiation_context(self, negotiation_id, user_id, timeout=None):
        """
        Context manager for safe negotiation locking.

        Usage:
            with lock_manager.negotiation_context(negotiation_id, user_id) as lock_id:
                if lock_id:
                    # Perform negotiation operations
                    pass
        """
        lock_id = self.acquire_lock(negotiation_id, user_id, timeout)
        try:
            yield lock_id
        finally:
            if lock_id:
                self.release_lock(negotiation_id, user_id, lock_id)


class ViewPermissionManager:
    """
    Manages which users can view specific price information in negotiations.
    """

    def __init__(self):
        self.redis_client = get_redis_connection("default")

    def _get_view_key(self, negotiation_id, user_id):
        """Generate Redis key for view permissions"""
        return f"negotiation:{negotiation_id}:view:{user_id}"

    def grant_view_permission(self, negotiation_id, user_id, price, duration=3600):
        """
        Grant permission for a user to view a specific price.

        Args:
            negotiation_id: ID of the negotiation
            user_id: ID of the user
            price: Price they can view
            duration: Permission duration in seconds (default: 1 hour)
        """
        view_key = self._get_view_key(negotiation_id, user_id)
        self.redis_client.setex(
            view_key,
            duration,
            json.dumps(
                {
                    "price": str(price),
                    "granted_at": timezone.now().isoformat(),
                    "expires_at": (timezone.now() + timedelta(seconds=duration)).isoformat(),
                }
            ),
        )

    def revoke_view_permission(self, negotiation_id, user_id):
        """Revoke view permission for a user"""
        view_key = self._get_view_key(negotiation_id, user_id)
        self.redis_client.delete(view_key)

    def can_view_price(self, negotiation_id, user_id):
        """
        Check if a user can view the current price.

        Returns:
            tuple: (can_view, price) or (False, None)
        """
        view_key = self._get_view_key(negotiation_id, user_id)
        data = self.redis_client.get(view_key)

        if not data:
            return False, None

        try:
            view_data = json.loads(data)
            price = float(view_data.get("price", 0))
            return True, price
        except (json.JSONDecodeError, ValueError, KeyError):
            return False, None

    def update_view_permission_on_counter(self, negotiation_id, last_offer_by, new_price):
        """
        Update view permissions when a counter offer is made.
        Only the other party gets to see the new price.
        """
        from .models import Negotiation

        try:
            negotiation = Negotiation.objects.get(id=negotiation_id)

            # Grant view permission to the other party
            other_party = negotiation.seller if last_offer_by == negotiation.buyer else negotiation.buyer

            # Revoke old permissions
            self.revoke_view_permission(negotiation_id, negotiation.buyer_id)
            self.revoke_view_permission(negotiation_id, negotiation.seller_id)

            # Grant new permission only to the other party
            self.grant_view_permission(negotiation_id, other_party.id, new_price)

            return True
        except Negotiation.DoesNotExist:
            return False


lock_manager = DistributedNegotiationLock()
view_manager = ViewPermissionManager()
