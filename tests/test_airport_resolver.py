
from scripts.build_airport_db import get_db_connection
from core.airport_resolver import resolve_airports



def test_airport_resolver():
    # Define cities and expected airport codes
    test_cases = [
        ("İstanbul", "TR", {"IST", "SAW"}),
        ("London", "GB", {"LHR"}),
        ("Paris", "FR", {"CDG"}),
        ("İzmir", "TR", {"ADB"}),
    ]

    # Connect to PostgreSQL
    with get_db_connection() as conn:

        # Test each city
        for city, country, expected_codes in test_cases:
            airports = resolve_airports(conn, city, country)

            # Collect the returned airport codes
            codes = {
                airport["iata_code"]
                for airport in airports
            }

            # Display the results
            print(f"\n{city} ({country}):")
            print(sorted(codes))

            # Verify the expected airports
            assert expected_codes.issubset(codes), (
                f"Missing airports for {city}: "
                f"{expected_codes - codes}"
            )

    print("\nAll airport resolver tests passed!")



if __name__ == "__main__":
    test_airport_resolver()
