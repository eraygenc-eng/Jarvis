
import pytest

from core.flight.route_extractor import extract_flight_request


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
