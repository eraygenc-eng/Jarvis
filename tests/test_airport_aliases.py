
from core.airport_resolver import extract_city_aliases
from core.airport_resolver import build_airport_alias_candidates


def test_airport_aliases():
    # Test Izmir airport aliases
    izmir = extract_city_aliases("Gaziemir", "İzmir")
    assert "izmir" in izmir

    # Test Istanbul airport aliases
    istanbul = extract_city_aliases("Pendik, Istanbul", None)
    assert "istanbul" in istanbul

    # Test Paris airport aliases
    paris = extract_city_aliases(
        "Paris (Orly, Val-de-Marne)", None
    )
    assert "paris" in paris

    print("All airport alias tests passed!")


def test_alias_candidates():
    # Create aliases for a sample airport
    candidates = build_airport_alias_candidates(
        123, "Gaziemir", "İzmir"
    )

    # Check municipality source
    assert {
        "airport_id": 123,
        "alias": "gaziemir",
        "source": "municipality"
    } in candidates

    # Check keyword source
    assert {
        "airport_id": 123,
        "alias": "izmir",
        "source": "keywords"
    } in candidates

    print("Airport alias candidates test passed!")


if __name__ == "__main__":
    test_airport_aliases()
    test_alias_candidates()
