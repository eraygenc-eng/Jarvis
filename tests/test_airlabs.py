
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get the AirLabs API key
api_key = os.getenv("AIRLABS_API_KEY")

if not api_key:
    raise RuntimeError("AirLabs API key not found!")

# Airport database endpoint
api_url = "https://airlabs.co/api/v9/nearby"

# Search airports by city code
params = {
    "api_key": api_key,
    "lat": 51.5074,
    "lng": -0.1278,
    "distance": 80,
    "_fields": "name,iata_code,city_code,city,country_code,distance,connections,departures,is_major",
}

try:
    # Send the API request
    response = requests.get(
        api_url,
        params=params,
        timeout=15,
    )

    print("HTTP Status:", response.status_code)

    # Check the response status
    response.raise_for_status()

    # Convert JSON to Python data
    data = response.json()

    # Check pagination information without showing the API key
    request_info = data.get("request", {})

    if isinstance(request_info, dict):
        print("Has more results:", request_info.get("has_more"))

    # Check API errors
    if data.get("error"):
        print("API Error:", data["error"])

    else:
        # Get the nearby search results
        result = data.get("response", {})

        # Check the response format
        if not isinstance(result, dict):
            raise ValueError("Unexpected response format")

        # Extract the airport list
        airports = result.get("airports", [])

        if not isinstance(airports, list):
            raise ValueError("Unexpected airport data format")

        # Store unique airports by IATA code
        unique_airports = {}

        for airport in airports:
            code = airport.get("iata_code")

            if code:
                unique_airports[code] = airport

        # Show the airport results
        print("Unique airports found:", len(unique_airports))

        # Show airport details for filtering
        for code, airport in unique_airports.items():
            print(
                f"\nAirport: {airport.get('name')}",
                f"\nIATA: {code}",
                f"\nCity code: {airport.get('city_code')}",
                f"\nConnections: {airport.get('connections')}",
                f"\nDepartures: {airport.get('departures')}",
                f"\nIs major: {airport.get('is_major')}",
            )

except requests.RequestException as error:
    print("Request failed:", type(error).__name__)

except ValueError as error:
    print("Data error:", error)
