# Generated migration for category hierarchy implementation

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('producer', '0041_alter_product_category'),
    ]

    operations = [
        # Step 1: Create the new category hierarchy models
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=5, unique=True, verbose_name='Category Code')),
                ('name', models.CharField(max_length=100, verbose_name='Category Name')),
                ('description', models.TextField(blank=True, verbose_name='Category Description')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active Status')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Creation Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last Update Time')),
            ],
            options={
                'verbose_name': 'Category',
                'verbose_name_plural': 'Categories',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Subcategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=10, unique=True, verbose_name='Subcategory Code')),
                ('name', models.CharField(max_length=100, verbose_name='Subcategory Name')),
                ('description', models.TextField(blank=True, verbose_name='Subcategory Description')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active Status')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Creation Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last Update Time')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subcategories', to='producer.category', verbose_name='Category')),
            ],
            options={
                'verbose_name': 'Subcategory',
                'verbose_name_plural': 'Subcategories',
                'ordering': ['category__name', 'name'],
            },
        ),
        migrations.CreateModel(
            name='SubSubcategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=15, unique=True, verbose_name='Sub-subcategory Code')),
                ('name', models.CharField(max_length=100, verbose_name='Sub-subcategory Name')),
                ('description', models.TextField(blank=True, verbose_name='Sub-subcategory Description')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active Status')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Creation Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last Update Time')),
                ('subcategory', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sub_subcategories', to='producer.subcategory', verbose_name='Subcategory')),
            ],
            options={
                'verbose_name': 'Sub-subcategory',
                'verbose_name_plural': 'Sub-subcategories',
                'ordering': ['subcategory__category__name', 'subcategory__name', 'name'],
            },
        ),
    ]