
import getpass
import psycopg
import pytest

from core.airport_resolver import (
    resolve_airports,
    resolve_airports_with_country_check,
    resolve_airport_selection,
    apply_airport_choice
)


@pytest.fixture(scope="module")
def db_connection():
    # Ask for the database password
    password = getpass.getpass("PostgreSQL password: ")

    # Connect to PostgreSQL
    with psycopg.connect(
        host="localhost",
        port=5432,
        dbname="jarvis_db",
        user="jarvis_app",
        password=password
    ) as conn:
        yield conn


@pytest.mark.parametrize(
    "city, country, expected",
    [
        ("Izmir", "TR", {"ADB"}),
        ("İstanbul", "TR", {"IST", "SAW"}),
        ("London", "GB", {"LHR", "LGW", "LCY", "LTN", "STN"}),
        ("Paris", "FR", {"CDG", "ORY"}),
    ]
)
def test_resolve_airports(db_connection, city, country, expected):
    # Find airports for the given city
    airports = resolve_airports(
        db_connection,
        city,
        country
    )

    # Get IATA codes from the results
    codes = {airport["iata_code"] for airport in airports}

    # Check expected airports
    assert expected.issubset(codes)

    # Check country codes
    assert all(
        airport["iso_country"] == country
        for airport in airports
    )

    # Check for duplicate airports
    assert len(codes) == len(airports)



def test_country_required(db_connection):
    # Search London without a country
    result = resolve_airports_with_country_check(
        db_connection, "London"
    )

    # Check if a country is required
    assert result["status"] == "country_required"
    assert "GB" in result["country_codes"]
    assert "CA" in result["country_codes"]
    assert result["airports"] == []


def test_country_resolved(db_connection):
    # Search London in the United Kingdom
    result = resolve_airports_with_country_check(
        db_connection, "London", "GB"
    )

    # Check the resolved airports
    assert result["status"] == "resolved"

    codes = {
        airport["iata_code"]
        for airport in result["airports"]
    }

    assert {"LHR", "LGW", "LCY", "LTN", "STN"}.issubset(codes)


def test_city_not_found(db_connection):
    # Search for a city that does not exist
    result = resolve_airports_with_country_check(
        db_connection, "nonexistentcity987654", "TR"
    )

    # Check the not found status
    assert result["status"] == "not_found"
    assert result["airports"] == []



def test_single_airport_selection(db_connection):
    # Search for airports in Izmir
    result = resolve_airport_selection(
        db_connection, "Izmir", "TR"
    )

    # Check automatic airport selection
    assert result["status"] == "resolved"
    assert result["airport"]["iata_code"] == "ADB"
    assert len(result["airports"]) == 1


def test_multiple_airport_selection(db_connection):
    # Search for airports in Istanbul
    result = resolve_airport_selection(
        db_connection, "Istanbul", "TR"
    )

    # Check if user selection is required
    assert result["status"] == "airport_choice_required"
    assert result["airport"] is None

    # Check available airports
    codes = {
        airport["iata_code"]
        for airport in result["airports"]
    }

    assert {"IST", "SAW"}.issubset(codes)


def test_country_check_before_selection(db_connection):
    # Search London without a country
    result = resolve_airport_selection(
        db_connection, "London"
    )

    # Check country ambiguity
    assert result["status"] == "country_required"
    assert "GB" in result["country_codes"]
    assert "CA" in result["country_codes"]




def test_full_flow_all_airports(db_connection):
    # Find airports in Istanbul
    result = resolve_airport_selection(
        db_connection, "Istanbul", "TR"
    )

    # Check if airport selection is needed
    assert result["status"] == "airport_choice_required"

    # Get the available airport codes
    available_codes = {
        airport["iata_code"]
        for airport in result["airports"]
    }

    assert {"IST", "SAW"}.issubset(available_codes)

    # User accepts all airports
    selected = apply_airport_choice(result, "fark etmez")

    # Check the final selection
    assert selected["status"] == "resolved"
    assert selected["selection_mode"] == "all"

    selected_codes = {
        airport["iata_code"]
        for airport in selected["airports"]
    }

    assert selected_codes == available_codes


def test_full_flow_single_airport(db_connection):
    # Find airports in Istanbul
    result = resolve_airport_selection(
        db_connection, "Istanbul", "TR"
    )

    # User selects Sabiha Gokcen
    selected = apply_airport_choice(result, "SAW")

    # Check the selected airport
    assert selected["status"] == "resolved"
    assert selected["selection_mode"] == "single"
    assert selected["airport"]["iata_code"] == "SAW"
    assert len(selected["airports"]) == 1


def test_full_flow_automatic_selection(db_connection):
    # Find airports in Izmir
    result = resolve_airport_selection(
        db_connection, "Izmir", "TR"
    )

    # Check automatic airport selection
    assert result["status"] == "resolved"
    assert result["airport"]["iata_code"] == "ADB"
    assert len(result["airports"]) == 1
