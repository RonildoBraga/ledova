import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from authentication.security.v2_challenges import ip_rate_digests
from ledova_backend.environment import parse_canonical_cidrs

_CONFIGURATION_ERROR = "Invalid v2 trusted proxy configuration."
_MAX_FORWARDED_HEADER_BYTES = 2048
_MAX_FORWARDED_HOPS = 10


class V2TrustedProxyConfigurationError(ImproperlyConfigured):
    pass


@dataclass(frozen=True, repr=False, init=False)
class V2TrustedProxyConfiguration:
    networks: tuple

    def __init__(self, *_args, **_kwargs):
        raise V2TrustedProxyConfigurationError(_CONFIGURATION_ERROR)

    @classmethod
    def _create(cls, cidr_values):
        try:
            canonical = parse_canonical_cidrs(cidr_values)
            networks = tuple(ipaddress.ip_network(value, strict=True) for value in canonical)
        except (ImproperlyConfigured, TypeError, ValueError):
            raise V2TrustedProxyConfigurationError(_CONFIGURATION_ERROR) from None
        instance = object.__new__(cls)
        object.__setattr__(instance, "networks", networks)
        return instance

    def __repr__(self):
        return "V2TrustedProxyConfiguration(networks=<redacted>)"


def resolve_trusted_proxy_config(cidr_values):
    return V2TrustedProxyConfiguration._create(cidr_values)


def load_trusted_proxy_config():
    try:
        cidr_values = settings.V2_TRUSTED_PROXY_CIDRS
    except Exception:
        raise V2TrustedProxyConfigurationError(_CONFIGURATION_ERROR) from None
    return resolve_trusted_proxy_config(cidr_values)


def _validated_configuration(configuration):
    try:
        if not isinstance(configuration, V2TrustedProxyConfiguration):
            raise V2TrustedProxyConfigurationError(_CONFIGURATION_ERROR)
        cidr_values = tuple(str(network) for network in configuration.networks)
    except Exception:
        raise V2TrustedProxyConfigurationError(_CONFIGURATION_ERROR) from None
    return V2TrustedProxyConfiguration._create(cidr_values)


def _parsed_address(value):
    if not isinstance(value, str) or not value or "%" in value:
        return None
    try:
        value.encode("ascii")
        address = ipaddress.ip_address(value)
    except (UnicodeEncodeError, ValueError):
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_trusted(address, configuration):
    return any(address.version == network.version and address in network for network in configuration.networks)


def _forwarded_addresses(value):
    if not isinstance(value, str):
        return None
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        return None
    if not encoded or len(encoded) > _MAX_FORWARDED_HEADER_BYTES:
        return None
    values = value.split(",")
    if len(values) > _MAX_FORWARDED_HOPS:
        return None
    addresses = []
    for raw_value in values:
        token = raw_value.strip(" \t")
        address = _parsed_address(token)
        if address is None:
            return None
        addresses.append(address)
    return tuple(addresses)


def _resolved_address(request, configuration):
    try:
        metadata = getattr(request, "META", None)
        if not isinstance(metadata, Mapping):
            return None
        direct_value = metadata.get("REMOTE_ADDR")
    except Exception:
        return None
    direct_address = _parsed_address(direct_value)
    if direct_address is None:
        return None
    if not _is_trusted(direct_address, configuration):
        return direct_address
    try:
        forwarded_value = metadata.get("HTTP_X_FORWARDED_FOR")
    except Exception:
        return None
    forwarded_addresses = _forwarded_addresses(forwarded_value)
    if forwarded_addresses is None:
        return None
    for address in reversed(forwarded_addresses):
        if not _is_trusted(address, configuration):
            return address
    return None


def _rate_material(address):
    if isinstance(address, ipaddress.IPv4Address):
        return 4, 32, address.packed
    if isinstance(address, ipaddress.IPv6Address):
        network = ipaddress.ip_network((address, 64), strict=False)
        return 6, 64, network.network_address.packed
    return 0, 0, b""


def request_ip_rate_digests(
    request,
    *,
    trusted_proxy_configuration,
    challenge_configuration,
):
    configuration = _validated_configuration(trusted_proxy_configuration)
    return ip_rate_digests(
        *_rate_material(_resolved_address(request, configuration)),
        configuration=challenge_configuration,
    )
