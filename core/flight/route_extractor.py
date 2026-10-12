
import re

from core.flight.flight_request import FlightRequest


# Match Turkish routes with apostrophes
TURKISH_ROUTE_PATTERN = re.compile(
    r"(?P<departure>[^\W\d_]+)['’](?:dan|den|tan|ten)"
    r"\s+"
    r"(?P<arrival>[^\W\d_]+)['’](?:ya|ye|a|e)\b",
    re.IGNORECASE,
)


def extract_flight_request(prompt: str) -> FlightRequest:
    """
    Extract flight route information from a user request.
    """

    # Create a new flight request
    request = FlightRequest(original_prompt=prompt)

    # Find the departure and arrival cities
    match = TURKISH_ROUTE_PATTERN.search(prompt)

    if match is None:
        return request

    # Storing
    request.departure_city = match.group("departure")
    request.arrival_city =  match.group("arrival")

    return request