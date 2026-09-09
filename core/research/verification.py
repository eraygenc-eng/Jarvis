from urllib.parse import urlparse


def normalize_host(host: str) -> str:
    # Ignore common www prefix differences
    return host.casefold().removeprefix("www.")


def urls_match(
    expected_url: str,
    current_url: str,
) -> bool:
    # Compare offer URLs without tracking parameters
    expected = urlparse(expected_url.strip())
    current = urlparse(current_url.strip())

    same_host = (
        normalize_host(expected.netloc)
        == normalize_host(current.netloc)
    )

    same_path = (
        expected.path.rstrip("/")
        == current.path.rstrip("/")
    )

    return same_host and same_path


def validate_money_values(
    **values,
) -> str | None:
    # Monetary values cannot be negative
    for name, value in values.items():
        if value is None:
            continue

        if value < 0:
            return (
                f"{name} cannot be negative."
            )

    return None