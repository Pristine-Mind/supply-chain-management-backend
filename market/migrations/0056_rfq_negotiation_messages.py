from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_existing_rfq_opening_events(apps, schema_editor):
    QuoteRequest = apps.get_model("market", "QuoteRequest")
    RFQNegotiationMessage = apps.get_model("market", "RFQNegotiationMessage")
    database = schema_editor.connection.alias

    for rfq in QuoteRequest.objects.using(database).iterator():
        proposed_price = Decimal(str(rfq.proposed_price)) if rfq.proposed_price is not None else None
        message = RFQNegotiationMessage.objects.using(database).create(
            rfq_id=rfq.pk,
            sender_id=rfq.requested_by_id,
            message="RFQ initiated with a target price proposal." if proposed_price is not None else "RFQ created.",
            quoted_unit_price=proposed_price,
            quoted_quantity=rfq.quantity if proposed_price is not None else None,
            discount=Decimal("0.00") if proposed_price is not None else None,
            delivery_charge=Decimal("0.00") if proposed_price is not None else None,
            total_amount=proposed_price * rfq.quantity if proposed_price is not None else None,
            status_event="rfq_created",
        )
        RFQNegotiationMessage.objects.using(database).filter(pk=message.pk).update(timestamp=rfq.created_at)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("market", "0055_quoterequest_proposed_price"),
    ]

    operations = [
        migrations.CreateModel(
            name="RFQNegotiationMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField(blank=True)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("quoted_unit_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("quoted_quantity", models.PositiveIntegerField(blank=True, null=True)),
                ("discount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("delivery_charge", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("estimated_delivery", models.CharField(blank=True, max_length=255, null=True)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("total_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("status_event", models.CharField(blank=True, max_length=32, null=True)),
                (
                    "rfq",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="market.quoterequest",
                    ),
                ),
                (
                    "sender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rfq_negotiation_messages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["timestamp", "id"],
            },
        ),
        migrations.RunPython(create_existing_rfq_opening_events, migrations.RunPython.noop),
    ]
