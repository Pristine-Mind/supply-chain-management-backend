# Generated by Django 4.2.16 on 2024-10-23 14:11

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("market", "0009_alter_marketplaceuserproduct_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketplaceuserproduct",
            name="user",
            field=models.ForeignKey(
                default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name="Sender"
            ),
            preserve_default=False,
        ),
    ]
