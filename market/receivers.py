import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from reversion import set_comment

logger = logging.getLogger(__name__)


def get_marketplace_sale_model():
    from market.models import MarketplaceSale

    return MarketplaceSale


@receiver(post_save)
def create_sale_revision(sender, **kwargs):
    """Create a revision when a sale is saved."""
    MarketplaceSale = get_marketplace_sale_model()
    if sender != MarketplaceSale:
        return

    instance = kwargs.get("instance")
    created = kwargs.get("created", False)

    if created:
        message = f"Created sale {instance.order_number}"
    else:
        message = f"Updated sale {instance.order_number}"

    try:
        set_comment(message)
        logger.debug(f"Revision created for sale {instance.order_number}")
    except Exception as e:
        logger.error(f"Error creating revision for sale {instance.order_number}: {str(e)}")


@receiver(post_delete)
def delete_sale_revision(sender, **kwargs):
    """Create a revision when a sale is deleted."""
    MarketplaceSale = get_marketplace_sale_model()
    if sender != MarketplaceSale:
        return

    instance = kwargs.get("instance")

    try:
        set_comment(f"Deleted sale {instance.order_number}")
        logger.debug(f"Deletion revision created for sale {instance.order_number}")
    except Exception as e:
        logger.error(f"Error creating deletion revision for sale {instance.order_number}: {str(e)}")
