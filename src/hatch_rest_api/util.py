import logging

from .const import SENSITIVE_FIELD_NAMES, MAX_IOT_VALUE

_LOGGER = logging.getLogger(__name__)


def clean_dictionary_for_logging(dictionary: dict[str, any]) -> dict[str, any]:
    mutable_dictionary = dictionary.copy()
    for key in dictionary:
        if key.lower() in SENSITIVE_FIELD_NAMES:
            mutable_dictionary[key] = "***"
        if isinstance(mutable_dictionary[key], dict):
            mutable_dictionary[key] = clean_dictionary_for_logging(
                mutable_dictionary[key].copy()
            )
        if isinstance(mutable_dictionary[key], list):
            new_array = []
            for item in mutable_dictionary[key]:
                if isinstance(item, dict):
                    new_array.append(clean_dictionary_for_logging(item.copy()))
                else:
                    new_array.append(item)
            mutable_dictionary[key] = new_array

    return mutable_dictionary


def convert_from_percentage(percentage: int):
    return int(round(percentage / 100.0 * MAX_IOT_VALUE)) & 0xFFFF


def convert_to_percentage(value: int):
    return round((value & 0xFFFF) / (1.0 * MAX_IOT_VALUE) * 100)


def convert_from_hex(percentage: int):
    return int(round(percentage / 255.0 * MAX_IOT_VALUE)) & 0xFFFF


def convert_to_hex(value: int):
    return round((value & 0xFFFF) / (1.0 * MAX_IOT_VALUE) * 255)


def safely_get_json_value(json, key, callable_to_cast=None):
    value = json
    for x in key.split("."):
        if value is not None:
            try:
                value = value[x]
            except (TypeError, KeyError):
                try:
                    value = value[int(x)]
                except (TypeError, KeyError, ValueError):
                    value = None
    if callable_to_cast is not None and value is not None:
        value = callable_to_cast(value)
    return value
