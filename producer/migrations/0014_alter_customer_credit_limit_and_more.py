# Generated by Django 4.2.16 on 2024-09-17 07:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("producer", "0013_remove_order_payment_due_date_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customer",
            name="credit_limit",
            field=models.FloatField(default=0.0, verbose_name="Credit Limit"),
        ),
        migrations.AlterField(
            model_name="customer",
            name="current_balance",
            field=models.FloatField(default=0.0, verbose_name="Current Balance"),
        ),
        migrations.AlterField(
            model_name="marketplaceproduct",
            name="listed_price",
            field=models.FloatField(verbose_name="Listed Price"),
        ),
        migrations.AlterField(
            model_name="order",
            name="total_price",
            field=models.FloatField(blank=True, null=True, verbose_name="Total Price"),
        ),
        migrations.AlterField(
            model_name="product",
            name="cost_price",
            field=models.FloatField(verbose_name="Cost Price"),
        ),
        migrations.AlterField(
            model_name="product",
            name="price",
            field=models.FloatField(verbose_name="Price"),
        ),
        migrations.AlterField(
            model_name="sale",
            name="sale_price",
            field=models.FloatField(verbose_name="Sale Price"),
        ),
    ]
