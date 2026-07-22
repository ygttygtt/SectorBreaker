import pytest

from backend.app.providers.url_safety import validate_public_http_url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://127.0.0.1/private",
        "http://[::1]/private",
        "http://169.254.169.254/latest/meta-data",
        "https://user:password@example.com/private",
    ],
)
def test_url_safety_rejects_non_public_targets(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_http_url(url, resolver=lambda host: [host] if host[0].isdigit() or ":" in host else ["127.0.0.1"])


def test_url_safety_rejects_hostname_resolving_to_private_address() -> None:
    with pytest.raises(ValueError, match="non-public"):
        validate_public_http_url("https://internal.example/path", resolver=lambda host: ["10.0.0.7"])


def test_url_safety_accepts_public_http_address() -> None:
    validate_public_http_url("https://example.com/path", resolver=lambda host: ["93.184.216.34"])
