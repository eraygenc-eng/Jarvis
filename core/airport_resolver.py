import unicodedata

from psycopg.rows import dict_row


def normalize_city(city: str) -> str:
    # Check if the input is a valid city name
    if not isinstance(city, str) or not city.strip():
        raise ValueError("City name cannot be empty")


    city = city.strip().lower()

    # Conver Turkish dotless i
    city = city.replace("ı","i")

    # Separate letters from their accent marks
    city = unicodedata.normalize("NFKD", city)

    # Remove accent marks
    city = "".join(
        char for char in city
        if not unicodedata.combining(char)
    )

    # Remove extra spaces between words
    city = " ".join(city.split())

    return city


# municipality -> yerleşim yeri
# Alias -> Takma ad
def extract_city_aliases(municipality, keywords):
    # Store unique city alias candidates
    aliases = set()

    if municipality:
        # Add the full municipality name
        aliases.add(normalize_city(municipality))

        # Handle names such as "Paris (Orly, Val-de-Marne)"
        main_city = municipality.split("(")[0].strip()

        if main_city:
            aliases.add(normalize_city(main_city))

         # Handle names such as "Pendik, Istanbul"
        if "," in municipality and "(" not in municipality:
            last_part = municipality.rsplit(",", 1)[-1].strip()
            aliases.add(normalize_city(last_part))

    if keywords:
        # Extract possible aliases from airport keywords
        for keyword in keywords.split(","):
            keyword = keyword.strip()

            if keyword:
                aliases.add(normalize_city(keyword))

    return aliases


def build_airport_alias_candidates(airport_id, municipality, keywords):
    candidates = []

    # Extract aliases from municipality
    municipality_aliases = extract_city_aliases(municipality, None)

    # Sort aliases in alphabetical order
    for alias in sorted(municipality_aliases):
        candidates.append({
            "airport_id": airport_id,
            "alias": alias,
            "source": "municipality"
        })

    # Extract aliases from keywords
    keyword_aliases = extract_city_aliases(None, keywords)

    # Sort aliases in alphabetical order
    for alias in sorted(keyword_aliases):
        candidates.append({
        "airport_id": airport_id,
        "alias": alias,
        "source": "keywords"
    })

    return candidates



def resolve_airports(conn, city: str, country_code: str = None):
    city = normalize_city(city)

    if country_code:
        country_code = country_code.strip().upper()

    with conn.cursor(row_factory = dict_row) as cur:

        # Find airports by city and country
        cur.execute("""
            SELECT
                a.iata_code,
                a.icao_code,
                a.name,
                a.municipality,
                a.iso_country,
                a.type,
                a.scheduled_service

            FROM public.airports AS a

            WHERE a.iata_code IS NOT NULL
              AND TRIM(a.iata_code) <> ''
              AND a.scheduled_service = TRUE

              AND (
                  (
                      a.municipality IS NOT NULL
                      AND (
                          LOWER(a.municipality) = %s
                          OR LOWER(a.municipality) LIKE %s
                          OR LOWER(a.municipality) LIKE %s
                      )
                  )

                  OR EXISTS (
                      SELECT 1
                      FROM public.airport_city_aliases AS ac
                      WHERE ac.airport_id = a.id
                        AND ac.alias = %s
                        AND ac.status = 'verified'
                  )
              )

              AND (
                  %s::text IS NULL
                  OR a.iso_country = %s
              )

            ORDER BY
                CASE
                    WHEN a.type = 'large_airport' THEN 0
                    WHEN a.type = 'medium_airport' THEN 1
                    ELSE 2
                END,
                a.name;
        """, (
            city,
            f"%, {city}",
            f"{city} (%",
            city,
            country_code,
            country_code
        ))

        # Return the matching airports
        return cur.fetchall()


def resolve_airports_with_country_check(conn, city, country_code=None):
    airports = resolve_airports(conn, city, country_code)

    if not airports:
        return {
            "status": "not_found",
            "airports": [],
            "country_codes": []
        }

    # Get unique country codes
    country_codes = sorted({
        airport["iso_country"]
        for airport in airports
        if airport["iso_country"]
    })

    # Check if the city exists in multiple countries
    if not country_code and len(country_codes) > 1:
        return {
            "status": "country_required",
            "airports": [],
            "country_codes": country_codes
        }

    return {
        "status": "resolved",
        "airports": airports,
        "country_codes": country_codes
    }



def resolve_airport_selection(conn, city, country_code=None):
    result = resolve_airports_with_country_check(conn, city, country_code)

    if result["status"] != "resolved":
        return result

    # Get matches
    airports = result["airports"]

    # Select auto if there is only one airport
    if len(airports) == 1:
        return {
            "status": "resolved",
            "airport": airports[0],
            "airports": airports,
            "country_codes": result["country_codes"]
        }

    # If there are more then one
    return {
        "status": "airport_choice_required",
        "airport": None,
        "airports": airports,
        "country_codes": result["country_codes"]
    }



def apply_airport_choice(result, choice):
    if result["status"] != "airport_choice_required":
        return result


    # Check if the choice is valid
    if not isinstance(choice, str) or not choice.strip():
        return {**result, "error": "invalid_choice"}

    # Normalize
    choice = normalize_city(choice)

    all_options = {
        "fark etmez",
        "farketmez",
        "hepsi",
        "tum havalimanlari",
        "it doesnt matter",
        "it doesn't matter",
        "doesnt matter",
        "doesn't matter",
        "it does not matter",
        "does not matter",
        "you pick",
        "u pick",
        "all of them",
        "all",
        "all airports",
    }


    if choice in {"ikisi de", "both"}:
        if len(result["airports"]) != 2:
            return {**result, "error": "invalid_choice"}

        choice = "hepsi"


    if choice in all_options:
        return {
            "status": "resolved",
            "airport": None,
            "airports": result["airports"],
            "country_codes": result["country_codes"],
            "selection_mode": "all"
        }

    # Find the airport by IATA code
    for airport in result["airports"]:
        if airport["iata_code"].lower() == choice:
            return {
                "status": "resolved",
                "airport": airport,
                "airports": [airport],
                "country_codes": result["country_codes"],
                "selection_mode": "single"
            }

    # Ask again if the choice is not recognized
    return {**result, "error": "invalid_choice"}



if __name__ == "__main__":
    # Test city normalization
    assert normalize_city("İstanbul") == "istanbul"
    assert normalize_city("ISTANBUL") == "istanbul"
    assert normalize_city("İZMİR") == "izmir"
    assert normalize_city("München") == "munchen"

    print("All normalization tests passed!")