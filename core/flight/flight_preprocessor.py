import re

from core.database import get_db_connection

from core.flight.route_extractor import (
    extract_flight_request,
    split_route_words,
    build_city_candidates,
    extract_verified_route,
)

from core.airport_resolver import (
    resolve_airport_selection,
    find_city_matches,
    apply_airport_choice,
    resolve_airport_by_iata
)

from core.global_city_resolver import resolve_city


def prepare_flight_request(prompt: str) -> dict:
    """
    Prepare a flight request for airport resolution.
    """

    # Extract cities from the user request
    flight = extract_flight_request(prompt)

    conn = get_db_connection()

    try:

        # Resolve explicit airport codes before city matching
        if (
            len(flight.departure_airports) == 1
            and len(flight.arrival_airports) == 1
        ):
            departure_airport = resolve_airport_by_iata(
                conn, flight.departure_airports[0]
            )

            arrival_airport = resolve_airport_by_iata(
                conn, flight.arrival_airports[0]
            )

            # Continue only when both airport codes are valid
            if departure_airport and arrival_airport:
                return {
                    "status": "ready",
                    "flight_request": flight,
                    "departure": {
                        "status": "resolved",
                        "airport": departure_airport,
                        "airports": [departure_airport],
                        "country_codes": [departure_airport["iso_country"]],
                        "selection_mode": "single",
                    },
                    "arrival": {
                        "status": "resolved",
                        "airport": arrival_airport,
                        "airports": [arrival_airport],
                        "country_codes": [arrival_airport["iso_country"]],
                        "selection_mode": "single",
                    },
                }

        # Use database matching if regex fails
        if not flight.departure_city or not flight.arrival_city:
            words = split_route_words(prompt)
            candidates = build_city_candidates(words)
            matches = find_city_matches(conn, candidates)

            flight.departure_city, flight.arrival_city = (
                extract_verified_route(prompt, matches)
            )

        # Stop if the route is still incomplete
        if not flight.departure_city or not flight.arrival_city:
            return {
                "status": "route_incomplete",
                "flight_request": flight,
            }

        departure_city = resolve_city(flight.departure_city)
        arrival_city = resolve_city(flight.arrival_city)

        city_statuses = {
            departure_city["status"],
            arrival_city["status"]
        }

        if "not_found" in city_statuses:
            return {
                "status": "not_found",
                "flight_request": flight
            }

        # Stop if a city is ambiguous
        if "ambiguous" in city_statuses:
            return {
                "status": "city_choice_required",
                "flight_request": flight,
                "departure_city": departure_city,
                "arrival_city": arrival_city
            }

        departure = resolve_airport_selection(
            conn, 
            departure_city["city"][1],
            country_code=departure_city["city"][2]
        )

        arrival = resolve_airport_selection(
            conn,
            arrival_city["city"][1],
            country_code=arrival_city["city"][2]
        )

        # Read explicit airport codes from the user request
        iata_codes = re.findall(r"\(([A-Z]{3})\)", prompt.upper())

        # Apply codes when departure and arrival are both specified
        if len(iata_codes) == 2:
            departure_code, arrival_code = iata_codes

            # Select the departure airport if a choice is required
            if departure["status"] == "airport_choice_required":
                selected = apply_airport_choice(departure, departure_code)

                if not selected.get("error"):
                    departure = selected

            # Select the arrival airport if a choice is required
            if arrival["status"] == "airport_choice_required":
                selected = apply_airport_choice(arrival, arrival_code)

                if not selected.get("error"):
                    arrival = selected

    finally:
        conn.close()


    statuses = {
        departure["status"],
        arrival["status"]
    }

    # Decide the next step
    if "not_found" in statuses:
        status = "not_found"

    elif "country_required" in statuses:
        status = "country_required"

    elif "airport_choice_required" in statuses:
        status = "airport_choice_required"

    else:
        status = "ready"

    return {
        "status": status,
        "flight_request": flight,
        "departure": departure,
        "arrival": arrival,
    }