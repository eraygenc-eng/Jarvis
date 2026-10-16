from core.database import get_db_connection
from core.airport_resolver import (
    resolve_airport_selection,
    apply_airport_choice
)

from core.airport_resolver import (
    get_airport_words,
    get_airport_name_tokens,
    normalize_city
)

def test_real_airport_selection():
    # Connect to the real PostgreSQL database
    with get_db_connection() as conn:

        # Get airports from the database
        result = resolve_airport_selection(
            conn,
            "Istanbul",
            "TR"
        )

    # Check if airport selection is required
    assert result["status"] == "airport_choice_required"

    # Get available airport codes
    codes = {
        airport["iata_code"]
        for airport in result["airports"]
    }

    # Check Istanbul airports
    assert {"IST", "SAW"}.issubset(codes)

    # Test natural language choices
    choices = [
        ("SAW olsun", "SAW"),
        ("Sabiha Gökçen olsun", "SAW"),
        ("IST seçelim", "IST"),
        ("IST veya SAW", None),
        ("SAW istemiyorum", None),
    ]

    for message, expected in choices:
        # Process the user's choice
        response = apply_airport_choice(result, message)

        if expected is None:
            # Reject ambiguous or negative choices
            assert response.get("error") == "invalid_choice"

        else:
            # Check the selected airport
            assert response["status"] == "resolved"
            assert response["airport"]["iata_code"] == expected

        print(f"{message} -> {expected}")


def test_london_paris_selection():
    # Test airports in different countries
    test_cases = [
        ("London", "GB", "Heathrow olsun", "LHR"),
        ("London", "GB", "Gatwick seçelim", "LGW"),
        ("Paris", "FR", "Charles de Gaulle olsun", "CDG"),
        ("Paris", "FR", "Orly tercih ediyorum", "ORY"),
    ]

    with get_db_connection() as conn:

        for city, country, choice, expected in test_cases:
            # Get real airports from PostgreSQL
            result = resolve_airport_selection(
                conn, city, country
            )

            # Check that multiple airports are found
            assert result["status"] == "airport_choice_required"

            # Process the user's airport choice
            response = apply_airport_choice(result, choice)

            # Show which airport choice failed
            print(f"\nCity: {city}")
            print(f"User choice: {choice}")
            print(f"Status: {response['status']}")
            print(f"Error: {response.get('error')}")

            # Show available airport names
            print("Available airports:")
            for airport in result["airports"]:
                print(airport["iata_code"], "-", airport["name"])

            # Verify the selected airport
            assert response["status"] == "resolved", (
                f"City: {city}, "
                f"Choice: {choice}, "
                f"Error: {response.get('error')}, "
                f"Airports: {[(a['iata_code'], a['name']) for a in result['airports']]}"
            )
            assert response["airport"]["iata_code"] == expected

            print(f"{city}: {choice} -> {expected}")


def test_izmir_airport_resolution():
    with get_db_connection() as conn:

        # Find airports in Izmir
        result = resolve_airport_selection(
            conn, "Izmir", "TR"
        )



def test_paris_city_is_not_airport_choice():
    with get_db_connection() as conn:
        result = resolve_airport_selection(
            conn, "Paris", "FR"
        )

    # City name alone must not select an airport
    response = apply_airport_choice(result, "Paris")
    assert response.get("error") == "invalid_choice"

    # Distinctive airport name should work
    response = apply_airport_choice(
        result, "Orly tercih ediyorum"
    )

    assert response["status"] == "resolved"
    assert response["airport"]["iata_code"] == "ORY"



def test_official_airport_name():
    # Get real Istanbul airports
    with get_db_connection() as conn:
        result = resolve_airport_selection(
            conn, "Istanbul", "TR"
        )

    assert result["status"] == "airport_choice_required"

    # Match the complete official airport name
    response = apply_airport_choice(
        result, "İstanbul Airport olsun"
    )

    assert response["status"] == "resolved"
    assert response["airport"]["iata_code"] == "IST"

    # Do not select using only the city name
    response = apply_airport_choice(
        result, "İstanbul"
    )

    assert response.get("error") == "invalid_choice"


def test_multilingual_airport_names():
    # Load real Istanbul airports
    with get_db_connection() as conn:
        result = resolve_airport_selection(
            conn, "Istanbul", "TR"
        )

    assert result["status"] == "airport_choice_required"

    # Test airport names in different forms
    test_cases = [
        ("İstanbul Havalimanı olsun", "IST"),
        ("Istanbul Airport olsun", "IST"),
        ("Sabiha Gökçen Havalimanı", "SAW"),
        ("Sabiha Gokcen Airport", "SAW"),
    ]

    # Check multilingual normalization
    message = "İstanbul Havalimanı olsun"

    print("\nRaw words:", get_airport_words(message))
    print("Normalized words:", get_airport_name_tokens(message))
    print("After city normalization:",
        get_airport_name_tokens(normalize_city(message)))

    # Check the real airport names
    for airport in result["airports"]:
        print(
            airport["iata_code"],
            get_airport_name_tokens(airport["name"])
        )

    for choice, expected in test_cases:
        response = apply_airport_choice(result, choice)

        # Verify the selected airport
        assert response["status"] == "resolved", choice
        assert response["airport"]["iata_code"] == expected

    # A city name alone must not select an airport
    response = apply_airport_choice(result, "İstanbul")

    assert response.get("error") == "invalid_choice"