# Generated by Django 4.2.16 on 2024-09-07 01:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("producer", "0002_alter_order_payment_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="total_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Total Price"),
        ),
    ]
