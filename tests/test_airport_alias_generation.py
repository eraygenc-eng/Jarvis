
from core.airport_resolver import build_airport_alias_candidates


def test_municipality_and_keywords():
    # Generate aliases for an Istanbul airport
    candidates = build_airport_alias_candidates(
        1,
        "Pendik, Istanbul",
        "IST, Istanbul"
    )

    # Check the generated aliases and their sources
    result = {
        (item["alias"], item["source"])
        for item in candidates
    }

    expected = {
        ("pendik, istanbul", "municipality"),
        ("istanbul", "municipality"),
        ("ist", "keywords"),
        ("istanbul", "keywords")
    }

    assert result == expected
    assert len(candidates) == 4


def test_missing_municipality():
    # Generate aliases without municipality information
    candidates = build_airport_alias_candidates(
        2,
        None,
        "Izmir, Adnan Menderes"
    )

    # Check that keywords still generate aliases
    aliases = {item["alias"] for item in candidates}

    assert aliases == {"izmir", "adnan menderes"}
    assert len(candidates) == 2
