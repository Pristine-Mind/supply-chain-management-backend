# Migration to migrate existing product categories to new hierarchy

from django.db import migrations


def migrate_product_categories(apps, schema_editor):
    """Migrate existing product categories to the new hierarchy"""
    Product = apps.get_model('producer', 'Product')
    Category = apps.get_model('producer', 'Category')
    
    # Mapping from old category codes to new Category objects
    category_mapping = {
        'FA': 'FA',  # Fashion & Apparel
        'EG': 'EG',  # Electronics & Gadgets
        'GE': 'GE',  # Groceries & Essentials
        'HB': 'HB',  # Health & Beauty
        'HL': 'HL',  # Home & Living
        'TT': 'TT',  # Travel & Tourism
        'IS': 'IS',  # Industrial Supplies
        'OT': 'OT',  # Other
    }
    
    # Get all categories for mapping
    categories = {cat.code: cat for cat in Category.objects.all()}
    
    # Update products with new category references
    for product in Product.objects.all():
        old_category_code = product.old_category
        if old_category_code in category_mapping:
            new_category_code = category_mapping[old_category_code]
            if new_category_code in categories:
                product.category = categories[new_category_code]
                product.save(update_fields=['category'])


def reverse_migrate_product_categories(apps, schema_editor):
    """Reverse the migration - clear new category fields"""
    Product = apps.get_model('producer', 'Product')
    
    Product.objects.update(
        category=None,
        subcategory=None,
        sub_subcategory=None
    )


class Migration(migrations.Migration):

    dependencies = [
        ('producer', '0043_add_product_category_fields'),
    ]

    operations = [
        migrations.RunPython(migrate_product_categories, reverse_migrate_product_categories),
    ]