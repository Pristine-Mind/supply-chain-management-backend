import datetime

import strawberry
import strawberry_django
from asgiref.sync import sync_to_async
from django.utils import timezone

from main.graphql.context import Info
from utils.strawberry.enums import enum_display_field, enum_field
from utils.strawberry.types import string_field

from .models import User


@strawberry.interface
class UserBaseType:
    # NOTE: Can't use strawberry.auto on interface
    id: strawberry.ID
    first_name = string_field(User.first_name)
    last_name = string_field(User.last_name)
    # display_name = string_field(User.display_name)  # type: ignore[reportArgumentType]


@strawberry_django.type(User)
class UserType(UserBaseType): ...


@strawberry_django.type(User)
class UserMeType(UserBaseType):
    email: strawberry.auto
    is_staff: strawberry.auto
    is_superuser: strawberry.auto
