
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from producer.models import MarketplaceProduct
from decimal import Decimal

User = get_user_model()


class DailySalesReport(models.Model):
    """
    One report per calendar day.
    """
    report_date = models.DateField(unique=True, help_text="Date of sales covered")
    generated_at = models.DateTimeField(auto_now_add=True)
    total_items = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ['-report_date']
        verbose_name = "Daily Sales Report"
        verbose_name_plural = "Daily Sales Reports"
        indexes = [
            models.Index(fields=['report_date']),
        ]

    def clean(self):
        if self.report_date > timezone.localdate():
            raise ValidationError({'report_date': "Cannot generate report for a future date."})

    def __str__(self):
        return f"Sales Report {self.report_date.isoformat()}"

    def recalc_totals(self):
        """
        Recalculate total_items & total_revenue from related items.
        """
        agg = self.items.aggregate(
            items= models.Sum('quantity'),
            revenue= models.Sum('line_total')
        )
        self.total_items = agg['items'] or 0
        self.total_revenue = agg['revenue'] or Decimal('0.00')
        self.save(update_fields=['total_items', 'total_revenue'])


class DailySalesReportItem(models.Model):
    """
    One line per sold product/customer for a given DailySalesReport.
    """
    report = models.ForeignKey(
        DailySalesReport, on_delete=models.CASCADE, related_name='items'
    )
    date = models.DateField(help_text="Sale date (should match report.report_date)")
    product = models.ForeignKey(
        MarketplaceProduct, on_delete=models.PROTECT, related_name='daily_report_items'
    )
    product_owner = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='products_sold'
    )
    customer = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='purchases'
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ['-date', 'product']
        unique_together = ('report', 'product', 'customer', 'unit_price')
        verbose_name = "Daily Sales Report Item"
        verbose_name_plural = "Daily Sales Report Items"
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['product']),
        ]

    def clean(self):
        errors = {}
        if self.date != self.report.report_date:
            errors['date'] = "Line date must match report_date."
        if self.quantity < 1:
            errors['quantity'] = "Quantity must be at least 1."
        if self.unit_price <= 0:
            errors['unit_price'] = "Unit price must be greater than zero."
        expected = (self.unit_price * self.quantity).quantize(Decimal('0.01'))
        if self.line_total != expected:
            errors['line_total'] = f"Line total must equal quantity × unit_price ({expected})."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        computed = (self.unit_price * self.quantity).quantize(Decimal('0.01'))
        self.line_total = computed
        super().save(*args, **kwargs)
        try:
            self.report.recalc_totals()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Error recalculating totals")

    def __str__(self):
        return f"{self.quantity}×{self.product} @ {self.unit_price} on {self.date}"
