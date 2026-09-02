"""Strict environment-variable parsing helpers."""

import ipaddress
import os
from collections.abc import Collection

from django.core.exceptions import ImproperlyConfigured

_CIDR_CONFIGURATION_ERROR = "Invalid CIDR configuration."
_IPV4_MAPPED_NETWORK = ipaddress.ip_network("::ffff:0:0/96")
_MAX_CIDR_ENTRIES = 32
_MAX_CIDR_LIST_BYTES = 2048


def read_bool(name: str, *, default: bool) -> bool:
    """Read an explicit ``true``/``false`` environment variable."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False

    raise ImproperlyConfigured(f"{name} must be either 'true' or 'false'")


def read_choice(name: str, *, choices: Collection[str], default: str) -> str:
    """Read and validate a case-insensitive environment choice."""
    allowed = frozenset(choice.lower() for choice in choices)
    value = os.environ.get(name, default).strip().lower()
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ImproperlyConfigured(f"{name} must be one of: {allowed_values}")
    return value


def parse_canonical_cidrs(values):
    try:
        if not isinstance(values, (list, tuple)) or len(values) > _MAX_CIDR_ENTRIES:
            raise ValueError
        canonical = []
        for value in values:
            if not isinstance(value, str) or not value or "/" not in value:
                raise ValueError
            value.encode("ascii")
            network = ipaddress.ip_network(value, strict=True)
            if str(network) != value:
                raise ValueError
            if isinstance(network, ipaddress.IPv6Network) and network.overlaps(_IPV4_MAPPED_NETWORK):
                raise ValueError
            if value in canonical:
                raise ValueError
            canonical.append(value)
        return tuple(canonical)
    except (UnicodeEncodeError, ValueError):
        raise ImproperlyConfigured(_CIDR_CONFIGURATION_ERROR) from None


def read_canonical_cidr_list(name):
    raw_value = os.environ.get(name, "")
    try:
        encoded = raw_value.encode("ascii")
        if len(encoded) > _MAX_CIDR_LIST_BYTES:
            raise ValueError
        values = [] if raw_value == "" else raw_value.split(",")
        return parse_canonical_cidrs(values)
    except (AttributeError, UnicodeEncodeError, ValueError):
        raise ImproperlyConfigured(_CIDR_CONFIGURATION_ERROR) from None


def resolve_storage_backend(*, debug: bool) -> str:
    """Resolve the media backend, with DEBUG forcing local storage."""
    configured_backend = read_choice(
        "STORAGE_BACKEND",
        choices=("local", "s3", "gcs"),
        default="local",
    )
    return "local" if debug else configured_backend
