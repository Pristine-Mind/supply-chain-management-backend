# user/migrations/0011_add_role_model.py

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_default_roles(apps, schema_editor):
    """Create default roles if they don't exist"""
    Role = apps.get_model("user", "Role")
    # Create default roles
    Role.objects.get_or_create(
        code="general_user",
        defaults={"name": "General User", "level": 0, "description": "Default role for all users with basic permissions."},
    )
    Role.objects.get_or_create(
        code="business_staff",
        defaults={
            "name": "Business Staff",
            "level": 1,
            "description": "Basic access level for business employees with limited permissions.",
        },
    )
    Role.objects.get_or_create(
        code="business_owner",
        defaults={
            "name": "Business Owner",
            "level": 2,
            "description": "Owner of a business with full access to their organization.",
        },
    )
    Role.objects.get_or_create(
        code="agent",
        defaults={"name": "Agent", "level": 3, "description": "Platform agent with elevated permissions to assist users."},
    )
    Role.objects.get_or_create(
        code="admin",
        defaults={
            "name": "Administrator",
            "level": 4,
            "description": "System administrator with full access to all features.",
        },
    )


def assign_default_role(apps, schema_editor):
    """Assign default role to existing users"""
    UserProfile = apps.get_model("user", "UserProfile")
    Role = apps.get_model("user", "Role")

    # Get the default role (general_user)
    default_role = Role.objects.get(code="general_user")

    # Assign the default role to all existing user profiles
    UserProfile.objects.filter(role__isnull=True).update(role=default_role)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("user", "0010_alter_userprofile_latitude_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50, unique=True, verbose_name="Role Name")),
                ("code", models.SlugField(max_length=20, unique=True, verbose_name="Role Code")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                (
                    "level",
                    models.PositiveIntegerField(
                        default=0, help_text="Hierarchy level (higher number means higher privileges)"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this role",
                        to="auth.permission",
                        verbose_name="Permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "Role",
                "verbose_name_plural": "Roles",
                "ordering": ["level"],
            },
        ),
        migrations.RunPython(create_default_roles),
        migrations.AddField(
            model_name="userprofile",
            name="role",
            field=models.ForeignKey(
                null=True,  # Make it nullable first
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_profiles",
                to="user.role",
                verbose_name="Role",
            ),
        ),
        migrations.RunPython(assign_default_role),
        migrations.AlterField(
            model_name="userprofile",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_profile",
                to=settings.AUTH_USER_MODEL,
                verbose_name="User",
            ),
        ),
        # Make the role field non-nullable after we've assigned roles
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_profiles",
                to="user.role",
                verbose_name="Role",
            ),
        ),
    ]
