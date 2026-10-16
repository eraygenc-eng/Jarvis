import pytest
from core.airport_resolver import apply_airport_choice, find_mentioned_airport_names


@pytest.mark.parametrize("choice, expected", [
    ("SAW", "SAW"),
    ("SAW olsun", "SAW"),
    ("Bence IST daha iyi", "IST"),
    ("saw.", "SAW"),
    ("SAW istemiyorum", None),
    ("IST veya SAW", None),
    ("SAWIST", None),
])
def test_natural_airport_choice(choice, expected):
    # Create sample airport options
    result = {
        "status": "airport_choice_required",
        "airports": [
            {"iata_code": "IST"},
            {"iata_code": "SAW"}
        ],
        "country_codes": ["TR"]
    }

    # Process the user's message
    response = apply_airport_choice(result, choice)

    if expected is None:
        # Ambiguous or negative choices must be rejected
        assert response.get("error") == "invalid_choice"
    else:
        # Check the selected airport
        assert response["status"] == "resolved"
        assert response["airport"]["iata_code"] == expected



def test_airport_name_matching():
    # Sample airport data
    airports = [
        {
            "iata_code": "IST",
            "name": "Istanbul Airport"
        },
        {
            "iata_code": "SAW",
            "name": "Istanbul Sabiha Gokcen International Airport"
        }
    ]

    # Match the airport by its name
    assert find_mentioned_airport_names(
        "Sabiha Gökçen olsun", airports
    ) == ["SAW"]

    # Do not select using only a shared city name
    assert find_mentioned_airport_names(
        "Istanbul", airports
    ) == []


def test_heathrow_name():
    airports = [
        {"iata_code": "LHR", "name": "London Heathrow Airport"},
        {"iata_code": "LGW", "name": "London Gatwick Airport"}
    ]

    assert find_mentioned_airport_names(
        "Heathrow'u seç", airports
    ) == ["LHR"]


def test_charles_de_gaulle_name():
    airports = [
        {"iata_code": "CDG", "name": "Paris Charles de Gaulle Airport"},
        {"iata_code": "ORY", "name": "Paris Orly Airport"}
    ]

    assert find_mentioned_airport_names(
        "Charles de Gaulle tercih ediyorum", airports
    ) == ["CDG"]


@pytest.mark.parametrize("choice, expected", [
    ("Sabiha Gökçen olsun", "SAW"),
    ("IST seçelim", "IST"),
    ("SAW yani Sabiha Gökçen", "SAW"),
    ("IST veya Sabiha Gökçen", None),
    ("Sabiha Gökçen istemiyorum", None),
])
def test_airport_choice_integration(choice, expected):
    # Available airport options
    result = {
        "status": "airport_choice_required",
        "airports": [
            {
                "iata_code": "IST",
                "name": "Istanbul Airport"
            },
            {
                "iata_code": "SAW",
                "name": "Istanbul Sabiha Gokcen International Airport"
            }
        ],
        "country_codes": ["TR"]
    }

    # Process the user's choice
    response = apply_airport_choice(result, choice)

    if expected is None:
        assert response.get("error") == "invalid_choice"
    else:
        assert response["status"] == "resolved"
        assert response["airport"]["iata_code"] == expected