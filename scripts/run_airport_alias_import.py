
import getpass
import psycopg

from scripts.build_airport_aliases import import_all_airport_aliases


# Ask for the database password
password = getpass.getpass("PostgreSQL password: ")

# Connect to the database
with psycopg.connect(
    host="localhost",
    port=5432,
    dbname="jarvis_db",
    user="jarvis_app",
    password=password
) as conn:

    # Import aliases in batches of 500 airports
    result = import_all_airport_aliases(
        conn,
        batch_size=500,
        limit=None
    )

    # Show the final results
    print("Full alias import completed!")
    print(result)
