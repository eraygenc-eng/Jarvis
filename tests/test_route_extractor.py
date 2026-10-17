
import pytest

from core.flight.route_extractor import extract_flight_request
from core.flight.route_extractor import detect_city_role, determine_route, extract_verified_route


@pytest.mark.parametrize(
    "prompt, departure, arrival",
    [
        ("İstanbul'dan Londra'ya uçuş bul", "İstanbul", "Londra"),
        ("Ankara'dan İzmir'e bilet bul", "Ankara", "İzmir"),
        ("İstanbul’dan Paris’e uçak bileti bul", "İstanbul", "Paris"),
    ],
)
def test_extract_turkish_route(prompt, departure, arrival):
    # Extract cities from the user request
    result = extract_flight_request(prompt)

    # Check departure and arrival cities
    assert result.departure_city == departure
    assert result.arrival_city == arrival


def test_missing_departure_city():
    # The departure city is not provided
    result = extract_flight_request("Londra'ya uçuş bul")

    # Do not guess missing cities
    assert result.departure_city is None
    assert result.arrival_city is None


def test_airport_lists_start_empty():
    # Create a new flight request
    result = extract_flight_request(
        "İstanbul'dan Londra'ya uçuş bul"
    )

    # Airport resolution has not started yet
    assert result.departure_airports == []
    assert result.arrival_airports == []



def test_hyphen_route_with_arasi():
    # Test a flight request using a hyphen
    prompt = (
        "Jarvis bana istanbul-Frankfurt arası "
        "uçak bileti bak pegasustan."
    )

    # Extract the flight cities
    result = extract_flight_request(prompt)

    # Check both city names
    assert result.departure_city is not None
    assert result.arrival_city is not None

    assert result.departure_city.casefold() == "istanbul"
    assert result.arrival_city.casefold() == "frankfurt"


def test_space_separated_route():
    # Check a route without a separator
    result = extract_flight_request("İstanbul Frankfurt uçak bileti bak")

    assert result.departure_city == "İstanbul"
    assert result.arrival_city == "Frankfurt"


def test_turkish_city_roles():
    # Check direction independently of city order
    prompt = "Frankfurt'a İstanbul'dan uçak bileti bak"

    assert detect_city_role(prompt, "Frankfurt") == "arrival"
    assert detect_city_role(prompt, "İstanbul") == "departure"


def test_determine_route():
    # Check a route without direction suffixes
    result = determine_route(
        "İstanbul Frankfurt uçak bileti bak",
        [(0, "istanbul"), (1, "frankfurt")]
    )

    assert result == ("istanbul", "frankfurt")

    # Check a route with reversed city order
    result = determine_route(
        "Frankfurt'a İstanbul'dan uçak bileti bak",
        [(0, "frankfurt"), (1, "istanbul")]
    )

    assert result == ("istanbul", "frankfurt")


def test_extract_verified_route():
    # Check a route without direction suffixes
    result = extract_verified_route(
        "İstanbul Frankfurt uçak bileti bak",
        ["frankfurt", "istanbul"]
    )

    assert result == ("istanbul", "frankfurt")

    # Check reverse word order with direction suffixes
    result = extract_verified_route(
        "Frankfurt'a İstanbul'dan uçak bileti bak",
        ["frankfurt", "istanbul"]
    )

    assert result == ("istanbul", "frankfurt")