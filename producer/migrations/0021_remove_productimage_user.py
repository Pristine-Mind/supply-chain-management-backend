# Generated by Django 4.2.16 on 2024-10-24 00:48

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("producer", "0020_customer_user_order_user_producer_user_product_user_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="productimage",
            name="user",
        ),
    ]
