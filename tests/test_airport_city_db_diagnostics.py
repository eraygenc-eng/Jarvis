"""Read-only diagnostics for global airport city name matching."""

import pytest

from core.database import get_db_connection
from core.airport_resolver import find_city_matches, resolve_airports


@pytest.fixture(scope="module")
def conn():
    # Use one database connection for both diagnostic tests.
    connection = get_db_connection()
    try:
        yield connection
    finally:
        connection.close()


def test_airport_city_records(conn):
    # Inspect airport records for Vienna and São Paulo.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT municipality, iso_country, iata_code
            FROM public.airports
            WHERE scheduled_service = TRUE
              AND iata_code IS NOT NULL
              AND (
                  municipality ILIKE '%Vienna%'
                  OR municipality ILIKE '%Paulo%'
              )
            ORDER BY municipality, iso_country, iata_code
            LIMIT 20
            """
        )
        rows = cur.fetchall()

    print("\n[AIRPORT RECORDS] Vienna / Paulo")
    if not rows:
        print("No matching airport records found.")
    for municipality, country_code, iata_code in rows:
        print(f"City: {municipality} | Country: {country_code} | IATA: {iata_code}")


def test_verified_city_aliases(conn):
    # Inspect the stored aliases and their verification statuses.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT alias, status
            FROM public.airport_city_aliases
            WHERE alias IN ('viyana', 'wien', 'sao paulo')
            ORDER BY alias, status
            """
        )
        rows = cur.fetchall()

    print("\n[CITY ALIASES] Viyana / Wien / Sao Paulo")
    if not rows:
        print("No matching aliases found.")
    for alias, status in rows:
        print(f"Alias: {alias} | Status: {status}")



def test_sao_paulo_normalized_match():
    # Check Unicode-insensitive city matching
    conn = get_db_connection()

    try:
        matches = find_city_matches(
            conn,
            ["São Paulo", "SAO PAULO"]
        )

        assert "sao paulo" in matches
    finally:
        conn.close()



def test_sao_paulo_airport_resolution():
    # Check airport resolution with accented city names
    conn = get_db_connection()

    try:
        airports = resolve_airports(
            conn,
            "SÃO PAULO",
            "BR"
        )

        codes = {
            airport["iata_code"]
            for airport in airports
        }

        assert "GRU" in codes
        assert "CGH" in codes

    finally:
        conn.close()
