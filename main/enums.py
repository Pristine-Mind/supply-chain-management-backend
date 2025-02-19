from django.conf import settings
from rest_framework import serializers

from market import enums as market_enums
from producer import enums as producer_enums

apps_enum_register = [("market", market_enums.enum_register), ("product", producer_enums.enum_registe)]


def underscore_to_camel(text):
    return text.replace("_", " ").title().replace(" ", "")


def generate_global_enum_register():
    enum_map = {}
    enum_names = set()
    for app_prefix, app_enum_register in apps_enum_register:
        for enum_field, enum in app_enum_register.items():
            _enum_field = f"{app_prefix}_{enum_field}"
            enum_name = f"{underscore_to_camel(_enum_field)}EnumSerializer"
            if enum_name in enum_names:
                raise Exception(f"Duplicate enum_names found for {enum_name} in {enum_names}")
            enum_names.add(enum_name)
            enum_map[_enum_field] = (enum_name, enum)
    return enum_map


global_enum_registers = generate_global_enum_register()


def generate_enum_global_serializer(name):
    def _get_enum_key_value_serializer(enum, enum_name):
        _enum_name = enum_name.replace("EnumSerializer", "EnumKey")
        settings.SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"][_enum_name] = enum

        # Determine the choices to use in the ChoiceField
        if hasattr(enum, "choices"):
            choices = enum.choices
        else:
            choices = enum

        return type(
            enum_name,
            (serializers.Serializer,),
            {
                "key": serializers.ChoiceField(choices=choices),
                "value": serializers.CharField(),
            },
        )

    fields = {}
    for enum_field, enum_value in global_enum_registers.items():
        if isinstance(enum_value, tuple):
            enum_name, enum = enum_value
        else:
            enum = enum_value
            enum_name = f"{enum_field.capitalize()}EnumSerializer"

        fields[enum_field] = _get_enum_key_value_serializer(enum, enum_name)(many=True, required=False)
    return type(name, (serializers.Serializer,), fields)


GlobalEnumSerializer = generate_enum_global_serializer("GlobalEnumSerializer")


def get_enum_values():
    enum_data = {}
    for enum_field, (_, enum) in global_enum_registers.items():
        if hasattr(enum, "choices"):
            choices = enum.choices
        else:
            choices = enum

        enum_data[enum_field] = [
            {
                "key": key,
                "value": value,
            }
            for key, value in choices
        ]
    return GlobalEnumSerializer(enum_data).data
