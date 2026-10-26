
import re

from core.flight.flight_request import FlightRequest
from core.airport_resolver import normalize_city


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


def split_route_words(prompt: str) -> list[str]:
    words = re.findall(r"[^\W\d_]+", prompt)

    return words


def build_city_candidates(words: list[str], max_words: int = 4) -> list[str]:
    # Store possible city names
    candidates = []

    # Start from each word
    for start in range(len(words)):

        # Try different city name lengths
        for size in range(1, max_words + 1):

            if start + size > len(words):
                break

            # Combine neighboring words
            candidate = " ".join(words[start:start + size])
            candidates.append(candidate)

    return candidates


def locate_city_matches(words: list[str], matches: list[str]) -> list[tuple[int, str]]:
    # Store city names with their positions
    locations = []

    for city in matches:
        city_length = len(city.split())

        for start in range(len(words)):
            phrase = " ".join(words[start:start + city_length])

            if normalize_city(phrase) == normalize_city(city):
                locations.append((start, city))

    # Sort cities by their position
    locations.sort(key=lambda item: item[0])

    return locations


def detect_city_role(prompt: str, city: str) -> str | None:
    # Find a Turkish direction suffix after the city
    pattern = rf"(?<!\w){re.escape(city)}['’](dan|den|tan|ten|ya|ye|a|e)\b"

    match = re.search(pattern, prompt, re.IGNORECASE)

    # Return None if no direction suffix is found
    if match is None:
        return None

    suffix = match.group(1).lower()

    # Identify the departure city
    if suffix in {"dan", "den", "tan", "ten"}:
        return "departure"

    return "arrival"


def determine_route(prompt: str, locations: list[tuple[int, str]]) -> tuple[str | None, str | None]:

    # Require exactly two city matches
    if len(locations) != 2:
        return None, None

    first_city = locations[0][1]
    second_city = locations[1][1]

    # Detect Turkish direction suffixes
    first_role = detect_city_role(prompt, first_city)
    second_role = detect_city_role(prompt, second_city)

    # Cities are already in departure-arrival order
    if first_role == "departure" and second_role == "arrival":
        return first_city, second_city

    # Cities are in reverse order
    if first_role == "arrival" and second_role == "departure":
        return second_city, first_city

    # Use word order when there are no direction suffixes
    if first_role is None and second_role is None:
        return first_city, second_city

    # Do not guess when direction information is incomplete
    return None, None


def extract_verified_route(prompt: str, city_matches: list[str]) -> tuple[str | None, str | None]:

    # Split the request into words
    words = split_route_words(prompt)

    # Find city positions
    locations = locate_city_matches(words, city_matches)

    # Determine departure and arrival
    return determine_route(prompt, locations)


def extract_flight_request(prompt: str) -> FlightRequest:
    """
    Extract flight route information from a user request.
    """

    # Create a new flight request
    request = FlightRequest(original_prompt=prompt)

    # Extract airport codes explicitly provided in parentheses
    iata_codes = re.findall(r"\(([A-Za-z]{3})\)", prompt)

    # Store departure and arrival airport codes in route order
    if len(iata_codes) == 2:
        request.departure_airports = [iata_codes[0].upper()]
        request.arrival_airports = [iata_codes[1].upper()]

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
