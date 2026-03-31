# Generated migration for is_delivery_free field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("producer", "0062_marketplaceproduct_discount_percentage"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketplaceproduct",
            name="is_delivery_free",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, shipping cost is set to zero and delivery is shown as free to buyers.",
                verbose_name="Free Delivery",
            ),
        ),
    ]
