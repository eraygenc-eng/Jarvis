import os
import psycopg

from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """
    Create a new PostgreSQL connection.
    """

    password = os.getenv("DB_PASSWORD")

    if not password:
        raise RuntimeError("DB_PASSWORD is missing in .env")


    # Connect to the Jarvis database
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "jarvis_db"),
        user=os.getenv("DB_USER", "jarvis_app"),
        password=password,
        connect_timeout=5,
    )