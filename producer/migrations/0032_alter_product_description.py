# Generated by Django 4.2.23 on 2025-07-10 03:53

import ckeditor.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("producer", "0031_marketplaceproduct_listed_price"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="description",
            field=ckeditor.fields.RichTextField(verbose_name="Product Description"),
        ),
    ]
