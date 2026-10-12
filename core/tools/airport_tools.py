from langchain_core.tools import tool
from core.airport_resolver import (resolve_airports_with_country_check)


# Connetion_factory is a connection when its needed
def create_airport_tools(connection_factory):
    """
    Create airport tools for the Jarvis agent.
    """

    @tool
    def airport_lookup(city: str, country_code: str | None =  None) -> dict:
        """
        Find airports for a city using the local database.
        """

        # Open a database connection
        conn = connection_factory()

        try:
            result = resolve_airports_with_country_check(
                conn,
                city,
                country_code
            )

            return result

        finally:
            conn.close()


    return [airport_lookup]