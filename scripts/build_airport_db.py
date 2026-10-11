import csv
import os
import psycopg # Connection between python-sql

from pathlib import Path
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]

# Set the path of the airports CSV file
CSV_PATH = ROOT_DIR / "data" / "airports.csv"

# Load database settings from the .env file
load_dotenv(ROOT_DIR / ".env")


def clean_text(value):
    # Remove spaces from the text
    value = (value or "").strip()

    return value or None

def clean_float(value):
    # Clean the input value
    value = clean_text(value)

    # Convert the value to float if it exists
    return float(value) if value else None



def get_db_connection():
    # Read database settings from environment variables
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "jarvis_db"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD"),
    }

    # Check if the database password exists
    if not db_config["password"]:
        raise ValueError("DB_PASSWORD is missing in .env")

    # Connect to PostgreSQL.
    return psycopg.connect(**db_config)


def create_airports_table(conn):
    # Create a cursor to run SQL commands
    with conn.cursor() as cur:

        # Create the airports table if it does not exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS airports (
                id BIGINT PRIMARY KEY,
                ident TEXT,
                name TEXT,
                type TEXT,
                municipality TEXT,
                iso_country TEXT,
                scheduled_service BOOLEAN,
                iata_code TEXT,
                icao_code TEXT,
                gps_code TEXT,
                latitude_deg DOUBLE PRECISION,
                longitude_deg DOUBLE PRECISION,
                keywords TEXT
            );
        """)

    print("Airports table is ready!")


def check_airports_csv():
    # Check if the CSV file exists
    if not CSV_PATH.is_file():
        raise FileNotFoundError(f"CSV file not found: {CSV_PATH}")

    # Open the CSV file
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        # Read the CSV file as dictionaries
        reader = csv.DictReader(file)

        # Define the columns
        required_columns = {
            "id", "ident", "name", "type",
            "municipality", "iso_country",
            "scheduled_service", "iata_code",
            "icao_code", "gps_code",
            "latitude_deg", "longitude_deg",
            "keywords"
        }

        # Find missing ones
        missing_columns = required_columns - set(reader.fieldnames or [])

        # Stop if a column is missing
        if missing_columns:
            raise ValueError(f"Missing columns: {missing_columns}")

        # Read the first airport
        first_airport = next(reader, None)

        # Check if the CSV file has data
        if first_airport is None:
            raise ValueError("CSV file is empty")

        print("CSV file is ready!")
        print(f"First airport: {first_airport['name']}")



def import_airports(conn):
    # Count imported airports
    imported_count = 0

    # Open the CSV file
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        # Read CSV rows as dictionaries
        reader = csv.DictReader(file)

        # Create a database cursor
        with conn.cursor() as cur:
            # Remove old airport records
            cur.execute("TRUNCATE TABLE airports;")

            # Start the bulk import
            with cur.copy("""
                COPY airports (
                    id, ident, name, type,
                    municipality, iso_country,
                    scheduled_service, iata_code,
                    icao_code, gps_code,
                    latitude_deg, longitude_deg,
                    keywords
                )
                FROM STDIN
            """) as copy:

                # Read each airport from the CSV file
                for row in reader:
                    # Prepare and import the airport data
                    copy.write_row((
                        int(row["id"]),
                        clean_text(row["ident"]),
                        clean_text(row["name"]),
                        clean_text(row["type"]),
                        clean_text(row["municipality"]),
                        clean_text(row["iso_country"]),
                        (row["scheduled_service"] or "").strip().lower() == "yes",
                        clean_text(row["iata_code"]),
                        clean_text(row["icao_code"]),
                        clean_text(row["gps_code"]),
                        clean_float(row["latitude_deg"]),
                        clean_float(row["longitude_deg"]),
                        clean_text(row["keywords"])
                    ))

                    imported_count += 1


        return imported_count



def create_airport_indexes(conn):
    # Create a cursor for SQL commands
    with conn.cursor() as cur:

        # Index for IATA airport codes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_airports_iata
            ON public.airports (iata_code)
            WHERE iata_code IS NOT NULL;
        """)

        # Index for ICAO airport codes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_airports_icao
            ON public.airports (icao_code)
            WHERE icao_code IS NOT NULL;
        """)

        # Index for city and country searches
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_airports_city_country
            ON public.airports (LOWER(municipality), iso_country)
            WHERE municipality IS NOT NULL;
        """)

        print("Airport indexes are ready!")




if __name__ == "__main__":
    # Check the CSV file.
    check_airports_csv()

    # Connect to PostgreSQL.
    with get_db_connection() as conn:

        # Create the airports table.
        create_airports_table(conn)

        # Import airports into PostgreSQL.
        total = import_airports(conn)

        # Create indexes for faster airport searches
        create_airport_indexes(conn)

    # Show the result after the database transaction.
    print(f"Imported airports: {total}")
    print("Airport database setup completed!")


