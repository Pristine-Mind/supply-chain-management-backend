# Generated by Django 4.2.16 on 2024-09-12 06:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0002_remove_bid_bid_end_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='bid',
            name='max_bid_amount',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=10, verbose_name='Maximum Bid Amount'),
            preserve_default=False,
        ),
    ]