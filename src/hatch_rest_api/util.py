import logging

from .const import SENSITIVE_FIELD_NAMES, MAX_IOT_VALUE

from math import ceil, floor

_LOGGER = logging.getLogger(__name__)


def clean_dictionary_for_logging(dictionary: dict[str, any]) -> dict[str, any]:
    mutable_dictionary = dictionary.copy()
    for key in dictionary.keys():
        if key.lower() in SENSITIVE_FIELD_NAMES:
            mutable_dictionary[key] = "***"
        if type(mutable_dictionary[key]) is dict:
            mutable_dictionary[key] = clean_dictionary_for_logging(
                mutable_dictionary[key].copy()
            )
        if type(mutable_dictionary[key]) is list:
            new_array = []
            for item in mutable_dictionary[key]:
                if type(item) is dict:
                    new_array.append(clean_dictionary_for_logging(item.copy()))
                else:
                    new_array.append(item)
            mutable_dictionary[key] = new_array

    return mutable_dictionary


def convert_from_percentage(percentage: int):
    return ceil((percentage / 100) * MAX_IOT_VALUE)


def convert_to_percentage(value: int):
    return floor((value * 100) / MAX_IOT_VALUE)


def convert_from_hex(percentage: int):
    return ceil((percentage / 255) * MAX_IOT_VALUE)


def convert_to_hex(value: int):
    return floor((value * 255) / MAX_IOT_VALUE)


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
