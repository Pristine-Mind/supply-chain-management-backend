# Generated by Django 4.2.16 on 2024-09-25 09:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('producer', '0014_alter_customer_credit_limit_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='is_marketplace_created',
            field=models.BooleanField(default=False, verbose_name='Marketplace Created'),
        ),
        migrations.AlterField(
            model_name='product',
            name='producer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='producer.producer', verbose_name='Producer'),
        ),
    ]