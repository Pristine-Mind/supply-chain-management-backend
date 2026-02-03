import dataclasses

import strawberry

ENUM_TO_STRAWBERRY_ENUM_MAP: dict[str, type] = {}


class AppEnumData:
    def __init__(self, enum):
        self.enum = enum

    @property
    def key(self):
        return self.enum

    @property
    def label(self):
        return str(self.enum.label)


def generate_app_enum_collection_data(name):
    return type(
        name,
        (),
        {field_name: [AppEnumData(e) for e in enum] for field_name, enum in ENUM_TO_STRAWBERRY_ENUM_MAP.items()},
    )


AppEnumCollectionData = generate_app_enum_collection_data("AppEnumCollectionData")


def generate_type_for_enum(name, Enum):
    return strawberry.type(
        dataclasses.make_dataclass(
            f"AppEnumCollection{name}",
            [
                ("key", Enum),
                ("label", str),
            ],
        )
    )


def _enum_type(name, Enum):
    EnumType = generate_type_for_enum(name, Enum)

    @strawberry.field
    def _field() -> list[EnumType]:  # type: ignore[reportGeneralTypeIssues]
        return [
            EnumType(
                key=e,
                label=e.label,
            )
            for e in Enum
        ]

    return list[EnumType], _field


def generate_type_for_enums():
    enum_fields = [
        (
            enum_field_name,
            *_enum_type(enum_field_name, enum),
        )
        for enum_field_name, enum in ENUM_TO_STRAWBERRY_ENUM_MAP.items()
    ]
    # Ensure at least one field exists for the type
    if not enum_fields:
        enum_fields = [("_placeholder", str, dataclasses.field(default=""))]
    return strawberry.type(
        dataclasses.make_dataclass(
            "AppEnumCollection",
            enum_fields,
        )
    )


AppEnumCollection = generate_type_for_enums()
