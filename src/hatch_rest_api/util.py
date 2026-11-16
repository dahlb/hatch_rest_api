"""Conversion and payload helpers shared by the device classes."""

from collections.abc import Callable, Mapping
import logging
from typing import Any

from .const import MAX_IOT_VALUE, SENSITIVE_FIELD_NAMES

_LOGGER = logging.getLogger(__name__)


def clean_dictionary_for_logging(dictionary: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``dictionary`` with sensitive values masked.

    Args:
        dictionary: Payload to sanitize. Nested dicts and lists are handled.

    Returns:
        A sanitized copy that is safe to log.
    """
    mutable_dictionary = dict(dictionary)
    for key in dictionary:
        if key.lower() in SENSITIVE_FIELD_NAMES:
            mutable_dictionary[key] = "***"
        if isinstance(mutable_dictionary[key], dict):
            mutable_dictionary[key] = clean_dictionary_for_logging(mutable_dictionary[key].copy())
        if isinstance(mutable_dictionary[key], list):
            new_array = []
            for item in mutable_dictionary[key]:
                if isinstance(item, dict):
                    new_array.append(clean_dictionary_for_logging(item.copy()))
                else:
                    new_array.append(item)
            mutable_dictionary[key] = new_array

    return mutable_dictionary


def convert_from_percentage(percentage: int) -> int:
    """Convert a 0-100 percentage into the device's 16-bit IoT scale."""
    return round(percentage / 100.0 * MAX_IOT_VALUE) & 0xFFFF


def convert_to_percentage(value: int) -> int:
    """Convert a 16-bit IoT value into a 0-100 percentage."""
    return round((value & 0xFFFF) / (1.0 * MAX_IOT_VALUE) * 100)


def convert_from_hex(percentage: int) -> int:
    """Convert a 0-255 color channel value into the device's 16-bit IoT scale."""
    return round(percentage / 255.0 * MAX_IOT_VALUE) & 0xFFFF


def convert_to_hex(value: int) -> int:
    """Convert a 16-bit IoT value into a 0-255 color channel value."""
    return round((value & 0xFFFF) / (1.0 * MAX_IOT_VALUE) * 255)


def safely_get_json_value(
    json: Any, key: str, callable_to_cast: Callable[[Any], Any] | None = None
) -> Any:
    """Look up a dotted ``key`` path in nested JSON without raising.

    Args:
        json: Decoded JSON payload to search.
        key: Dot-separated path; numeric parts also index into lists.
        callable_to_cast: Optional converter applied to a found value.

    Returns:
        The value at ``key``, converted if requested, or ``None`` if missing.
    """
    value = json
    for x in key.split("."):
        if value is not None:
            try:
                value = value[x]
            except TypeError, KeyError:
                try:
                    value = value[int(x)]
                except TypeError, KeyError, ValueError:
                    value = None
    if callable_to_cast is not None and value is not None:
        value = callable_to_cast(value)
    return value
