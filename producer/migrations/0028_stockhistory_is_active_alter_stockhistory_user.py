# Generated by Django 4.2.23 on 2025-07-03 01:38

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("producer", "0027_stockhistory_stock_after"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockhistory",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="Is Active"),
        ),
        migrations.AlterField(
            model_name="stockhistory",
            name="user",
            field=models.ForeignKey(
                default=1, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL, verbose_name="User"
            ),
            preserve_default=False,
        ),
    ]
