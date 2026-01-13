import logging
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import numpy as np
import pandas as pd
from celery import group, shared_task
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, F, Sum
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from market.models import MarketplaceProduct
from notification.models import Notification
from producer.models import Product, Sale

from .models import CustomerRFMSegment, WeeklyBusinessHealthDigest

User = get_user_model()
logger = logging.getLogger(__name__)


@shared_task
def generate_weekly_business_digests(target_date_str=None):
    """
    Coordinator task to trigger individual digests for all business owners.
    `target_date_str`: ISO string of any date in the week we want to report.
    """
    owners = User.objects.filter(user_profile__role__code="business_owner", is_active=True).values_list("id", flat=True)

    job = group(generate_single_user_digest.s(owner_id, target_date_str) for owner_id in owners)
    job.apply_async()
    return f"Triggered digests for {len(owners)} owners."


@shared_task
def cleanup_old_reports(days_to_keep=365):
    """
    Edge Case: Storage Management. Delete reports older than a year.
    """
    cutoff = timezone.now() - timedelta(days=days_to_keep)
    old_reports = WeeklyBusinessHealthDigest.objects.filter(generated_at__lt=cutoff, is_archived=False)

    deleted_count = 0
    for report in old_reports:
        if report.report_file:
            report.report_file.delete(save=False)
        if report.excel_report:
            report.excel_report.delete(save=False)
        report.is_archived = True
        report.save()
        deleted_count += 1

    return f"Archived {deleted_count} old reports."


@shared_task
def automated_rfm_segmentation():
    """Coordinator task for RFM segmentation."""
    owners = User.objects.filter(user_profile__role__code="business_owner", is_active=True).values_list("id", flat=True)
    job = group(calculate_owner_rfm_segments.s(owner_id) for owner_id in owners)
    job.apply_async()
    return f"Triggered RFM for {len(owners)} owners."


@shared_task(bind=True, max_retries=3)
def generate_single_user_digest(self, user_id, target_date_str=None):
    """Generates a robust digest for a single user."""
    try:
        owner = User.objects.get(id=user_id)
        shop_id = getattr(owner.user_profile, "shop_id", None)
        if not shop_id:
            return

        if target_date_str:
            base_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        else:
            base_date = timezone.localdate()

        monday = base_date - timedelta(days=base_date.weekday())
        start_date = monday - timedelta(days=7)
        end_date = monday - timedelta(days=1)

        if WeeklyBusinessHealthDigest.objects.filter(user=owner, start_date=start_date).exists():
            return f"Digest already exists for {owner.username} week {start_date}"

        sales_in_period = Sale.objects.filter(
            user__user_profile__shop_id=shop_id, sale_date__date__range=[start_date, end_date]
        )
        stats = sales_in_period.aggregate(total_rev=Sum("sale_price"), count=Count("id"))
        total_rev = stats["total_rev"] or Decimal("0.00")
        total_orders = stats["count"] or 0

        new_customers = (
            User.objects.filter(purchases__date__range=[start_date, end_date], purchases__report__items__product_owner=owner)
            .distinct()
            .count()
        )

        top_p_data = sales_in_period.values("order__product").annotate(units=Sum("quantity")).order_by("-units").first()
        top_product = MarketplaceProduct.objects.filter(id=top_p_data["order__product"]).first() if top_p_data else None

        with transaction.atomic():
            digest = WeeklyBusinessHealthDigest.objects.create(
                user=owner,
                start_date=start_date,
                end_date=end_date,
                total_revenue=total_rev,
                total_orders=total_orders,
                new_customers=new_customers,
                top_product=top_product,
            )

            pdf_buffer = BytesIO()
            doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
            styles = getSampleStyleSheet()
            elements = [
                Paragraph(f"Business Health: {owner.username}", styles["Title"]),
                Paragraph(f"Period: {start_date} to {end_date}", styles["Normal"]),
                Spacer(1, 12),
            ]

            data = [
                ["Metric", "Value"],
                ["Total Revenue", f"NPR {total_rev:,}"],
                ["Total Orders", str(total_orders)],
                ["New Customers", str(new_customers)],
                ["Top Product", str(top_product.product.name) if top_product else "N/A"],
            ]

            t = Table(data, colWidths=[200, 200])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
                    ]
                )
            )
            elements.append(t)
            doc.build(elements)
            digest.report_file.save(f"weekly_{start_date}.pdf", ContentFile(pdf_buffer.getvalue()))
            pdf_buffer.close()

            xlsx_buffer = BytesIO()
            detailed = list(sales_in_period.values("sale_date", "order__product__name", "quantity", "sale_price"))
            if detailed:
                pd.DataFrame(detailed).to_excel(xlsx_buffer, index=False)
                digest.excel_report.save(f"weekly_{start_date}.xlsx", ContentFile(xlsx_buffer.getvalue()))
            xlsx_buffer.close()

            profile = getattr(owner, "user_profile", None)
            if profile and profile.order_updates:
                Notification.objects.create(
                    user=owner,
                    notification_type="in_app",
                    title="Summary Ready",
                    body=f"Your summary for week starting {start_date} is ready.",
                    action_url="/api/v1/reports/health/",
                    content_type=ContentType.objects.get_for_model(digest),
                    object_id=digest.id,
                )
                digest.notification_sent = True
                digest.save(update_fields=["notification_sent"])

    except Exception as exc:
        logger.error(f"Digest failed for {user_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task
def calculate_owner_rfm_segments(owner_id):
    """Performs quantile-based segmentation for a specific owner's customers."""
    try:
        owner = User.objects.get(id=owner_id)

        sales_data = (
            Sale.objects.filter(order__product__user=owner)
            .select_related("order__customer__user")
            .values("order__customer__user_id", "sale_date", "sale_price")
        )

        if not sales_data:
            return

        df = pd.DataFrame(sales_data)
        if df.empty:
            return

        df["sale_date"] = pd.to_datetime(df["sale_date"])

        now = timezone.now()
        rfm = (
            df.groupby("order__customer__user_id")
            .agg(
                {
                    "sale_date": lambda x: (now - x.max()).days,
                    "order__customer__user_id": "count",
                    "sale_price": "sum",
                }
            )
            .rename(columns={"sale_date": "recency", "order__customer__user_id": "frequency", "sale_price": "monetary"})
        )

        if len(rfm) < 5:
            return

        rfm["r_score"] = pd.qcut(rfm["recency"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1], duplicates="drop").astype(
            int
        )
        rfm["f_score"] = pd.qcut(rfm["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5], duplicates="drop").astype(
            int
        )
        rfm["m_score"] = pd.qcut(rfm["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5], duplicates="drop").astype(
            int
        )

        for customer_id, row in rfm.iterrows():
            total_score = row["r_score"] + row["f_score"] + row["m_score"]

            if total_score >= 13:
                segment = "champions"
            elif total_score >= 10:
                segment = "loyal"
            elif total_score >= 7:
                segment = "potential_loyalist"
            elif total_score >= 4:
                segment = "at_risk"
            else:
                segment = "hibernating"

            CustomerRFMSegment.objects.update_or_create(
                customer_id=customer_id,
                shop_owner=owner,
                defaults={
                    "recency_score": row["r_score"],
                    "frequency_score": row["f_score"],
                    "monetary_score": row["m_score"],
                    "segment": segment,
                },
            )
    except Exception as e:
        logger.error(f"RFM calc failed for owner {owner_id}: {e}")


@shared_task
def check_inventory_and_alert():
    """Predictive inventory alerts with anti-spam logic."""
    low_stock_products = Product.objects.filter(is_active=True, stock__lte=F("reorder_point")).select_related("user")

    for product in low_stock_products:
        yesterday = timezone.now() - timedelta(hours=24)
        exists = Notification.objects.filter(
            user=product.user, title__icontains=product.name, created_at__gte=yesterday
        ).exists()

        if not exists:
            severity = "Urgent" if product.stock <= product.safety_stock else "Warning"
            Notification.objects.create(
                user=product.user,
                notification_type="push",
                title=f"Inventory {severity}: {product.name}",
                body=f"Stock ({product.stock}) is low. Reorder point: {product.reorder_point}.",
                event_data={"product_id": str(product.id)},
            )
