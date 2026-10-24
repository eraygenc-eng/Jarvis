
from core.database import get_db_connection



def search_city(city_name, limit=5, country_code=None, admin1_code=None):
    conn = get_db_connection()

    try:
        query = """
            WITH matches AS (
                SELECT DISTINCT
                    p.geoname_id,
                    p.name,
                    p.country_code,
                    p.feature_code,
                    p.population
                FROM public.global_place_names n
                JOIN public.global_places p
                    ON p.geoname_id = n.geoname_id
                WHERE n.normalized_name = LOWER(unaccent(%s))
        """

        params = [city_name]

        if country_code:
            query += " AND p.country_code = %s"
            params.append(country_code.upper())

        # Filter cities by administrative region
        if admin1_code:
            query += " AND p.admin1_code = %s"
            params.append(admin1_code.upper())

        query += """
            )
            SELECT
                geoname_id,
                name,
                country_code,
                feature_code,
                population
            FROM matches
            ORDER BY
                CASE
                    WHEN feature_code = 'PPLC' THEN 0
                    WHEN feature_code = 'PPLA' THEN 1
                    ELSE 2
                END,
                CASE
                    WHEN LOWER(unaccent(name)) =
                         LOWER(unaccent(%s)) THEN 0
                    ELSE 1
                END,
                population DESC NULLS LAST,
                geoname_id
            LIMIT %s
        """

        params.extend([city_name, limit])

        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    finally:
        conn.close()


def resolve_city(city_name, country_code=None, admin1_code=None):
    candidates =  search_city(
        city_name,
        limit=5,
        country_code=country_code,
        admin1_code=admin1_code
    )

    if not candidates:
        return {
            "status": "not_found",
            "city": None,
            "candidates": []
        }

    if len(candidates) == 1:
        return {
            "status": "resolved",
            "city": candidates[0],
            "candidates": candidates
        }

    # Find cities with an exact main name
    exact_matches = []

    for candidate in candidates:

        # Compare the main city name
        if candidate[1].casefold() == city_name.casefold():
            exact_matches.append(candidate)

    # Check if the location is specific enough
    if country_code and admin1_code and len(exact_matches) == 1:
        return {
            "status": "resolved",
            "city": exact_matches[0],
            "candidates": candidates
        }

    # Get the first two cities
    first_city = candidates[0]
    second_city = candidates[1]

    # Get the city information
    first_feature = first_city[3]
    first_population = first_city[4] or 0
    second_population = second_city[4] or 0

    # Check if the city is a major administrative center
    is_major_city = (
        first_feature in ("PPLC", "PPLA") # !!
        and first_population >= 100_000
    )

    # Compare populations when both values are known
    population_is_decisive = (
        second_population > 0
        and first_population >= 10 * second_population
    )

    # Check the exact city name when a country is given
    exact_capital_in_country = (
        country_code is not None
        and first_city[1].casefold() == city_name.casefold()
        and second_population == 0
    )

    # Select the capital if the conditions are met
    if is_major_city and (
        population_is_decisive or exact_capital_in_country
    ):
        return {
            "status": "resolved",
            "city": first_city,
            "candidates": candidates
        }

    return {
        "status": "ambiguous",
        "city": None,
        "candidates": candidates
    }


if __name__ == "__main__":
    cities = [
        "Viyana",
        "Wien",
        "Vienna",
        "İstanbul",
        "Londra",
        "Münih"
    ]

    for city in cities:
        results = search_city(city)

        print(f"\nSearch: {city}")

        for result in results:
            print(result)