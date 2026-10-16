
from core.database import get_db_connection
from core.tools.airport_tools import create_airport_tools
from core.airport_resolver import apply_airport_choice


def test_london_airport_lookup():
    # Create airport tools with database connection
    tools = create_airport_tools(get_db_connection)

    # Get the airport lookup tool
    airport_lookup = tools[0]

    # Search airports in London, United Kingdom
    result = airport_lookup.invoke({
        "city": "London",
        "country_code": "GB"
    })

    # Show the result
    print("\nLondon airports:", result)

    # Check the response structure
    assert isinstance(result, dict)

    # Check if the city was resolved
    assert result.get("status") == "resolved"

    # Check if airports were found
    assert len(result.get("airports", [])) > 0


    
    # Collect airport IATA codes
    airport_codes = {
        airport["iata_code"]
        for airport in result["airports"]
    }

    # Check expected London airports
    expected_codes = {"LHR", "LGW", "LTN", "STN", "LCY"}

    assert expected_codes.issubset(airport_codes)

    # Check the country code
    assert result["country_codes"] == ["GB"]



def test_turkish_city_name_londra():
    # Create airport tools
    tools = create_airport_tools(get_db_connection)
    airport_lookup = tools[0]

    # Search using the Turkish city name
    result = airport_lookup.invoke({
        "city": "Londra",
        "country_code": "GB"
    })

    print("\nLondra result:", result)

    # Check if the Turkish name is resolved
    assert result["status"] == "resolved"

    # Check if Heathrow Airport is found
    airport_codes = {
        airport["iata_code"]
        for airport in result["airports"]
    }

    assert "LHR" in airport_codes



def test_natural_airport_selection():
    # Create sample airport options
    result = {
        "status": "airport_choice_required",
        "airports": [
            {
                "iata_code": "IST",
                "name": "Istanbul Airport",
            },
            {
                "iata_code": "SAW",
                "name": "Istanbul Sabiha Gokcen International Airport",
            },
        ],
        "country_codes": ["TR"],
    }

    # Test different answers for the same airport
    answers = [
        "SAW",
        "SAW.",
        "SAW olsun",
        "sabiha gökçen olsun",
    ]

    for answer in answers:
        # Apply the user's answer
        selected = apply_airport_choice(result, answer)

        # Check if the airport was selected
        assert selected["status"] == "resolved", answer
        assert selected["airport"]["iata_code"] == "SAW"
