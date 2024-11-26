from . import models

enum_register = {
    "payment_status": models.Payment.PAYMENT_STATUS_CHOICES,
    "payment_method": models.Payment.PAYMENT_METHOD_CHOICES,
    "product_categogry": models.MarketplaceUserProduct.ProductCategory,
}
