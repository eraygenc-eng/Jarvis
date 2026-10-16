
from core.flight.flight_preprocessor import prepare_flight_request
from core.airport_resolver import apply_airport_choice
from core.research.task_classifier import is_flight_request


def test_istanbul_londra_flight():
    # Prepare a flight request
    result = prepare_flight_request(
        "İstanbul'dan Londra'ya uçak bileti bul"
    )

    
    # Show the full preprocessing result
    print("\nPreprocessor result:", result)


    # Get the extracted flight information
    flight = result["flight_request"]

    # Check departure and arrival cities
    assert flight.departure_city == "İstanbul"
    assert flight.arrival_city == "Londra"

    # Get departure airport codes
    departure_codes = {
        airport["iata_code"]
        for airport in result["departure"]["airports"]
    }

    # Get arrival airport codes
    arrival_codes = {
        airport["iata_code"]
        for airport in result["arrival"]["airports"]
    }

    # Check departure airports
    assert "IST" in departure_codes
    assert "SAW" in departure_codes

    # Check arrival airports
    assert "LHR" in arrival_codes
    assert "LGW" in arrival_codes

    # Check if airport selection is required
    assert result["departure"]["status"] == "airport_choice_required"
    assert result["arrival"]["status"] == "airport_choice_required"

    # Check preprocessing status
    assert result["status"] == "airport_choice_required"

    # Show test results
    print("\nDeparture airports:", departure_codes)
    print("Arrival airports:", arrival_codes)
    print("Preprocessor status:", result["status"])



def test_user_airport_choice():
    # Prepare a flight request
    result = prepare_flight_request(
        "İstanbul'dan Londra'ya uçak bileti bul"
    )

    # Get departure airport options
    departure = result["departure"]

    # Select Istanbul Airport
    selected = apply_airport_choice(
        departure,
        "IST"
    )

    # Check if the selection was successful
    assert selected["status"] == "resolved"

    # Check the selected airport
    assert selected["airport"]["iata_code"] == "IST"

    # Check the selection mode
    assert selected["selection_mode"] == "single"

    # Test the "any airport" option
    all_airports = apply_airport_choice(
        departure,
        "fark etmez"
    )

    # Check if all airports are allowed
    assert all_airports["status"] == "resolved"
    assert all_airports["selection_mode"] == "all"

    print("\nSelected airport:", selected["airport"]["iata_code"])
    print("Any airport mode:", all_airports["selection_mode"])



def test_real_pegasus_request():
    # Use the original live test request
    prompt = (
        "Jarvis bana istanbul-Frankfurt arası uçak bileti "
        "bak pegasustan. Gidiş tarihi 25 ekim, "
        "dönüş tarihi ise 30 ekim olacak "
        "ve tek kişi bagajsız olacak"
    )

    # Check if Jarvis detects a flight request
    assert is_flight_request(prompt)

    # Extract cities and search for airports
    result = prepare_flight_request(prompt)

    # Get flight information
    flight = result["flight_request"]

    # Check extracted cities
    assert flight.departure_city == "istanbul"
    assert flight.arrival_city == "Frankfurt"

    # Check if airport lookup was executed
    assert "departure" in result
    assert "arrival" in result

    # Check if Istanbul was found
    assert result["departure"]["status"] != "not_found"

    # Show airport resolution results
    print("\nDeparture:", result["departure"]["status"])
    print("Arrival:", result["arrival"]["status"])
    print("Flight status:", result["status"])

    
    # Check if Frankfurt was resolved
    assert result["arrival"]["status"] == "resolved"

    # Get arrival airport codes
    arrival_codes = {
        airport["iata_code"]
        for airport in result["arrival"]["airports"]
    }

    # Check Frankfurt Main Airport
    assert "FRA" in arrival_codes

    # Check if departure selection is required
    assert result["departure"]["status"] == "airport_choice_required"

    # Check the final preprocessing status
    assert result["status"] == "airport_choice_required"


