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
)


def prepare_flight_request(prompt: str) -> dict:
    """
    Prepare a flight request for airport resolution.
    """

    # Extract cities from the user request
    flight = extract_flight_request(prompt)

    conn = get_db_connection()

    try:

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

        departure = resolve_airport_selection(
            conn, 
            flight.departure_city
        )

        arrival = resolve_airport_selection(
            conn,
            flight.arrival_city
        )

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