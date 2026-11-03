from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("market", "0057_rfqdelivery"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quoterequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("quoted", "Quoted"),
                    ("accepted", "Accepted"),
                    ("ordered", "Ordered"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="rfqdelivery",
            name="buyer_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="rfqdelivery",
            name="supplier_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="rfqdelivery",
            constraint=models.UniqueConstraint(fields=("rfq",), name="unique_rfq_delivery"),
        ),
    ]
