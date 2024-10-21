from django.db import models
from threading import local

_thread_locals = local()


def get_current_shop():
    return getattr(_thread_locals, 'shop_id', None)


class ShopSpecificQuerySet(models.QuerySet):
    def _filter_by_shop(self):
        shop_id = get_current_shop()
        if shop_id:
            return self.filter(user__userprofile__shop_id=shop_id)
        return self.none()

    def all(self):
        return self._filter_by_shop()

    def filter(self, *args, **kwargs):
        return super().filter(*args, **kwargs)


def set_current_shop(shop_id):
    _thread_locals.shop_id = shop_id
