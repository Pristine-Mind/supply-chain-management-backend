# Data migration to populate category hierarchy and add new fields to Product

import django.db.models.deletion
from django.db import migrations, models


def populate_categories(apps, schema_editor):
    """Populate the category hierarchy with predefined data"""
    Category = apps.get_model("producer", "Category")
    Subcategory = apps.get_model("producer", "Subcategory")
    SubSubcategory = apps.get_model("producer", "SubSubcategory")

    # Basic category mapping (simplified for migration)
    categories_data = [
        {
            "code": "FA",
            "name": "Fashion & Apparel",
            "subcategories": [
                {
                    "code": "FA_CL",
                    "name": "Clothing",
                    "sub_subcategories": [
                        {"code": "FA_CL_MW", "name": "Men's Wear"},
                        {"code": "FA_CL_WW", "name": "Women's Wear"},
                        {"code": "FA_CL_KW", "name": "Kids' Wear"},
                    ],
                },
                {
                    "code": "FA_FW",
                    "name": "Footwear",
                    "sub_subcategories": [
                        {"code": "FA_FW_CS", "name": "Casual Shoes"},
                        {"code": "FA_FW_FS", "name": "Formal Shoes"},
                    ],
                },
            ],
        },
        {
            "code": "EG",
            "name": "Electronics & Gadgets",
            "subcategories": [
                {
                    "code": "EG_MB",
                    "name": "Mobile & Computing",
                    "sub_subcategories": [
                        {"code": "EG_MB_SP", "name": "Smartphones"},
                        {"code": "EG_MB_LP", "name": "Laptops"},
                    ],
                },
            ],
        },
        {
            "code": "GE",
            "name": "Groceries & Essentials",
            "subcategories": [
                {
                    "code": "GE_FD",
                    "name": "Food & Beverages",
                    "sub_subcategories": [
                        {"code": "GE_FD_FR", "name": "Fresh Produce"},
                    ],
                },
            ],
        },
        {
            "code": "HB",
            "name": "Health & Beauty",
            "subcategories": [
                {
                    "code": "HB_SK",
                    "name": "Skincare",
                    "sub_subcategories": [
                        {"code": "HB_SK_FC", "name": "Face Care"},
                    ],
                },
            ],
        },
        {
            "code": "HL",
            "name": "Home & Living",
            "subcategories": [
                {
                    "code": "HL_FR",
                    "name": "Furniture",
                    "sub_subcategories": [
                        {"code": "HL_FR_LR", "name": "Living Room"},
                    ],
                },
            ],
        },
        {
            "code": "TT",
            "name": "Travel & Tourism",
            "subcategories": [
                {
                    "code": "TT_LG",
                    "name": "Luggage & Bags",
                    "sub_subcategories": [
                        {"code": "TT_LG_SC", "name": "Suitcases"},
                    ],
                },
            ],
        },
        {
            "code": "IS",
            "name": "Industrial Supplies",
            "subcategories": [
                {
                    "code": "IS_TL",
                    "name": "Tools & Equipment",
                    "sub_subcategories": [
                        {"code": "IS_TL_PT", "name": "Power Tools"},
                    ],
                },
            ],
        },
        {
            "code": "OT",
            "name": "Other",
            "subcategories": [
                {
                    "code": "OT_SP",
                    "name": "Specialty Items",
                    "sub_subcategories": [
                        {"code": "OT_SP_CO", "name": "Collectibles"},
                    ],
                },
            ],
        },
    ]

    for category_data in categories_data:
        category, created = Category.objects.get_or_create(
            code=category_data["code"], defaults={"name": category_data["name"]}
        )

        for subcategory_data in category_data.get("subcategories", []):
            subcategory, created = Subcategory.objects.get_or_create(
                code=subcategory_data["code"], defaults={"name": subcategory_data["name"], "category": category}
            )

            for sub_subcategory_data in subcategory_data.get("sub_subcategories", []):
                SubSubcategory.objects.get_or_create(
                    code=sub_subcategory_data["code"],
                    defaults={"name": sub_subcategory_data["name"], "subcategory": subcategory},
                )


def reverse_populate_categories(apps, schema_editor):
    """Remove all categories"""
    Category = apps.get_model("producer", "Category")
    Subcategory = apps.get_model("producer", "Subcategory")
    SubSubcategory = apps.get_model("producer", "SubSubcategory")

    SubSubcategory.objects.all().delete()
    Subcategory.objects.all().delete()
    Category.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("producer", "0042_create_category_models"),
    ]

    operations = [
        # Step 1: Rename existing category field to old_category
        migrations.RenameField(
            model_name="product",
            old_name="category",
            new_name="old_category",
        ),
        # Step 2: Add new foreign key fields for the hierarchy
        migrations.AddField(
            model_name="product",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="producer.category",
                verbose_name="Category",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="subcategory",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="producer.subcategory",
                verbose_name="Subcategory",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="sub_subcategory",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="producer.subsubcategory",
                verbose_name="Sub-subcategory",
            ),
        ),
        # Step 3: Populate the category hierarchy
        migrations.RunPython(populate_categories, reverse_populate_categories),
    ]
