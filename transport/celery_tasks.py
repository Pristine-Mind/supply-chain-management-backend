from celery import shared_task

from .tasks import (
    cleanup_expired_deliveries,
    run_periodic_tasks,
    send_delivery_reminders,
    update_delivery_estimates,
)


@shared_task
def periodic_delivery_reminders():
    return send_delivery_reminders()


@shared_task
def periodic_cleanup():
    return cleanup_expired_deliveries()


@shared_task
def periodic_estimate_updates():
    return update_delivery_estimates()


@shared_task
def run_all_periodic_tasks():
    return run_periodic_tasks()
