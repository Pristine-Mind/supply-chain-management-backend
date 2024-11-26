from . import models

enum_registe = {
    "customer_type": models.Customer.CUSTOMER_TYPE_CHOICES,
    "product_category": models.Product.ProductCategory,
    "order_status": models.Order.Status,
    "payment_status": models.Sale.Status,
}