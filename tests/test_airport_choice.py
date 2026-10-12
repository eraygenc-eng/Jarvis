
import pytest

from core.airport_resolver import apply_airport_choice


@pytest.fixture
def airport_result():
    # Create sample airport selection data
    return {
        "status": "airport_choice_required",
        "airport": None,
        "airports": [
            {"iata_code": "IST", "name": "Istanbul Airport"},
            {"iata_code": "SAW", "name": "Sabiha Gokcen Airport"}
        ],
        "country_codes": ["TR"]
    }


@pytest.mark.parametrize("choice", [
    "fark etmez",
    "farketmez",
    "hepsi",
    "tüm havalimanları",
    "ikisi de"
])
def test_select_all_airports(airport_result, choice):
    # Select all available airports
    result = apply_airport_choice(airport_result, choice)

    # Check the selection result
    assert result["status"] == "resolved"
    assert result["selection_mode"] == "all"
    assert result["airport"] is None
    assert len(result["airports"]) == 2


def test_select_single_airport(airport_result):
    # Select Istanbul Airport
    result = apply_airport_choice(airport_result, "IST")

    # Check the selected airport
    assert result["status"] == "resolved"
    assert result["selection_mode"] == "single"
    assert result["airport"]["iata_code"] == "IST"
    assert len(result["airports"]) == 1


def test_invalid_airport_choice(airport_result):
    # Try an unknown airport code
    result = apply_airport_choice(airport_result, "ABC")

    # Check the error
    assert result["status"] == "airport_choice_required"
    assert result["error"] == "invalid_choice"


def test_selection_not_required():
    # Create an already resolved result
    original = {
        "status": "resolved",
        "airports": [{"iata_code": "ADB"}]
    }

    # Selection should not change the result
    result = apply_airport_choice(original, "IST")

    assert result == original



def test_ikisi_de_with_three_airports(airport_result):
    # Add a third airport
    airport_result["airports"].append({
        "iata_code": "ADB",
        "name": "Adnan Menderes Airport"
    })

    # Try selecting both with three airports
    result = apply_airport_choice(
        airport_result,
        "ikisi de"
    )

    # Check that the choice is rejected
    assert result["status"] == "airport_choice_required"
    assert result["error"] == "invalid_choice"
    assert len(result["airports"]) == 3

