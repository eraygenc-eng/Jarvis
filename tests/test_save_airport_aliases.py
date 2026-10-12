
from scripts.build_airport_db import get_db_connection
from scripts.build_airport_aliases import save_airport_aliases


def test_save_airport_aliases():
    # Connect to PostgreSQL
    with get_db_connection() as conn:

        # Create a database cursor
        with conn.cursor() as cur:

            # Find Izmir Adnan Menderes Airport
            cur.execute("""
                SELECT id, municipality, keywords
                FROM public.airports
                WHERE iata_code = 'ADB'
                  AND iso_country = 'TR';
            """)

            airport = cur.fetchone()

            # Check if the airport exists
            assert airport is not None, "ADB airport not found"

            airport_id, municipality, keywords = airport

        # Generate and save airport aliases
        count = save_airport_aliases(
            conn, airport_id, municipality, keywords
        )

        # Read saved aliases from PostgreSQL
        with conn.cursor() as cur:
            cur.execute("""
                SELECT alias, source, status
                FROM public.airport_city_aliases
                WHERE airport_id = %s
                ORDER BY alias;
            """, (airport_id,))

            aliases = cur.fetchall()

        # Check expected aliases
        saved_aliases = {
            (alias, source)
            for alias, source, status in aliases
        }

        assert ("izmir", "keywords") in saved_aliases
        assert ("gaziemir", "municipality") in saved_aliases

        # Show test results
        print(f"Generated candidates: {count}")

        for alias, source, status in aliases:
            print(f"{alias} - {source} - {status}")

    print("Airport alias database test passed!")


if __name__ == "__main__":
    test_save_airport_aliases()
