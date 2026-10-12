
import getpass
import psycopg

from scripts.build_airport_aliases import import_all_airport_aliases


# Ask for the database password
password = getpass.getpass("PostgreSQL password: ")

# Connect to PostgreSQL
with psycopg.connect(
    host="localhost",
    port=5432,
    dbname="jarvis_db",
    user="jarvis_app",
    password=password
) as conn:

    # Import aliases for only 10 airports
    result = import_all_airport_aliases(
        conn,
        batch_size=5,
        limit=10
    )

    # Show the import results
    print("Import completed!")
    print(result)
