# Generated by Django 4.2.16 on 2024-09-26 07:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("producer", "0015_product_is_marketplace_created_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="sku",
            field=models.CharField(
                blank=True, max_length=100, null=True, unique=True, verbose_name="Stock Keeping Unit (SKU)"
            ),
        ),
    ]
