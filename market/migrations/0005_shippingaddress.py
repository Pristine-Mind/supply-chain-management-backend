# Generated by Django 4.2.16 on 2024-09-15 06:53

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("market", "0004_payment"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShippingAddress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("address_line_1", models.CharField(max_length=255)),
                ("address_line_2", models.CharField(blank=True, max_length=255, null=True)),
                ("city", models.CharField(max_length=100)),
                ("state", models.CharField(max_length=100)),
                ("postal_code", models.CharField(max_length=20)),
                ("country", models.CharField(max_length=100)),
                ("phone_number", models.CharField(max_length=15)),
                ("payment", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to="market.payment")),
            ],
            options={
                "verbose_name": "Shipping Address",
                "verbose_name_plural": "Shipping Addresses",
            },
        ),
    ]
