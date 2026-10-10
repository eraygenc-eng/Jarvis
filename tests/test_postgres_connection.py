
import os
import psycopg
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

# Get PostgreSQL connection settings
db_host = os.getenv("POSTGRES_HOST")
db_port = os.getenv("POSTGRES_PORT")
db_name = os.getenv("POSTGRES_DB")
db_user = os.getenv("POSTGRES_USER")
db_password = os.getenv("POSTGRES_PASSWORD")

# Check required settings
if not all([
    db_host,
    db_port,
    db_name,
    db_user,
    db_password,
]):
    raise RuntimeError("PostgreSQL settings are missing!")

try:
    # Connect to the PostgreSQL database
    with psycopg.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        connect_timeout=5,
    ) as conn:

        # Create a cursor to run SQL queries
        with conn.cursor() as cursor:

            # Check the current database
            cursor.execute("SELECT current_database()")
            current_db = cursor.fetchone()[0]

            print("Connected database:", current_db)

            # Check the airports table
            cursor.execute(
                "SELECT COUNT(*) FROM public.airports"
            )

            airport_count = cursor.fetchone()[0]

            print("Airport records:", airport_count)
            print("PostgreSQL connection successful!")

except psycopg.Error as error:
    print("Connection failed:", type(error).__name__)
