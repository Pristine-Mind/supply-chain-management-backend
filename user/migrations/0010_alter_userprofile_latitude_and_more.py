# Generated by Django 4.2.23 on 2025-07-04 16:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0009_userprofile_business_type_userprofile_latitude_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="latitude",
            field=models.FloatField(blank=True, help_text="Geo-coordinate: latitude", null=True, verbose_name="Latitude"),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="longitude",
            field=models.FloatField(blank=True, help_text="Geo-coordinate: longitude", null=True, verbose_name="Longitude"),
        ),
    ]
