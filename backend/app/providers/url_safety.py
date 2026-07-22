"""Public URL validation shared by extraction providers."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlparse

AddressResolver = Callable[[str], Iterable[str]]


def validate_public_http_url(url: str, *, resolver: AddressResolver | None = None) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("only public http/https URLs may be extracted")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise ValueError("URL hostname is required")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("localhost URLs are not allowed")

    addresses = list((resolver or _resolve_addresses)(hostname))
    if not addresses:
        raise ValueError("URL hostname did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError(f"non-public target address is not allowed: {ip.compressed}")


def _resolve_addresses(hostname: str) -> list[str]:
    try:
        return list(dict.fromkeys(
            item[4][0]
            for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        ))
    except socket.gaierror as exc:
        raise ValueError(f"URL hostname could not be resolved: {hostname}") from exc
