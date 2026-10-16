
import re

from core.flight.flight_request import FlightRequest


# Match Turkish routes with apostrophes
TURKISH_ROUTE_PATTERN = re.compile(
    r"(?P<departure>[^\W\d_]+)['’](?:dan|den|tan|ten)"
    r"\s+"
    r"(?P<arrival>[^\W\d_]+)['’](?:ya|ye|a|e)\b",
    re.IGNORECASE,
)


# Match routes separated by a hyphen
HYPHEN_ROUTE_PATTERN = re.compile(
    r"(?P<departure>[^\W\d_]+)\s*[-–—]\s*"
    r"(?P<arrival>[^\W\d_]+)\s+arası\b",
    re.IGNORECASE,
)


def extract_flight_request(prompt: str) -> FlightRequest:
    """
    Extract flight route information from a user request.
    """

    # Create a new flight request
    request = FlightRequest(original_prompt=prompt)

    # Try the Turkish apostrophe format
    match = TURKISH_ROUTE_PATTERN.search(prompt)

    # Try the hyphen format if no match was found
    if match is None:
        match = HYPHEN_ROUTE_PATTERN.search(prompt)

    # Return if no route was found
    if match is None:
        return request

    # Store departure and arrival cities
    request.departure_city = match.group("departure")
    request.arrival_city = match.group("arrival")

    return request
