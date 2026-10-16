import unicodedata
import re

from psycopg.rows import dict_row
from collections import Counter


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
                a.keywords,
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


def find_mentioned_iata_codes(choice, airports):
    # Store matching airport codes
    matches = []

    for airport in airports:
        code = airport.get("iata_code")

        if not code:
            continue

        # Match only complete IATA codes
        pattern = rf"(?<!\w){re.escape(code)}(?!\w)"

        if re.search(pattern, choice, re.IGNORECASE):
            matches.append(code.upper())

    return list(dict.fromkeys(matches))


def get_airport_words(text):
    text = text.casefold().replace("ı","i")

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )

    return re.findall(r"[a-z0-9]+", text)


def get_airport_name_tokens(text):
    # Get normalized words
    words = get_airport_words(text)

    # Map airport terms from different languages
    airport_terms = {
        "havalimani": "airport",
        "aeroport": "airport",
        "aeropuerto": "airport",
        "aeroporto": "airport",
        "flughafen": "airport",
    }

    # Convert airport terms to a common form
    return [
        airport_terms.get(word, word)
        for word in words
    ]


def find_mentioned_airport_names(choice, airports):
    # Words that do not identify a specific airport
    ignored_words = {
        "airport",
        "international",
        "havalimani",
        "aeroport",
        "airfield",
        "flughafen"
    }

    # Keep both ordered and unique words
    choice_tokens = get_airport_name_tokens(choice)
    choice_words = set(choice_tokens)

    # Extract words from airport names
    airport_words = [
        set(get_airport_words(airport.get("name") or ""))
        for airport in airports
    ]

    # Count how many airports contain each word
    word_counts = Counter(
        word
        for words in airport_words
        for word in words
    )

    # Extract municipality words
    municipality_words = [
        set(get_airport_words(airport.get("municipality") or ""))
        for airport in airports
    ]

    # Find words shared by multiple municipalities
    common_city_words = set()

    valid_municipalities = [
        words for words in municipality_words if words
    ]

    if len(valid_municipalities) >= 2:
        common_city_words = set.intersection(
            *valid_municipalities
        )

    matches = []

    for airport, words in zip(airports, airport_words):

        # Get the official airport name
        name_tokens = get_airport_words(
            airport.get("name") or ""
        )

        # Match the complete official name
        full_name_match = (
            len(name_tokens) >= 2
            and any(
                choice_tokens[i:i + len(name_tokens)] == name_tokens
                for i in range(
                    len(choice_tokens) - len(name_tokens) + 1
                )
            )
        )

        # Keep only distinctive airport words
        distinctive_words = {
            word for word in words
            if len(word) >= 4
            and word not in ignored_words
            and word not in common_city_words
            and word_counts[word] == 1
        }

        # Check if the user mentioned a distinctive word
        if full_name_match or distinctive_words.intersection(choice_words):
            code = airport.get("iata_code")

            if code:
                matches.append(code.upper())

    return list(dict.fromkeys(matches))



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

    # Find IATA codes in the message
    mentioned_codes = find_mentioned_iata_codes(
        choice,
        result["airports"]
    )

    # Find airport names in the message
    mentioned_names = find_mentioned_airport_names(
        choice,
        result["airports"]
    )

    # Combine matches without duplicates
    matched_codes = set(mentioned_codes) | set(mentioned_names)

    # Reject missing or ambiguous selections
    if len(matched_codes) != 1:
        return {**result, "error": "invalid_choice"}

    # Check common negative expressions
    negative_pattern = (
        r"\b(?:degil|değil|istem\w*|olmas\w*|"
        r"secme\w*|seçme\w*|not|no|never|"
        r"don't|dont|doesn't|doesnt)\b"
    )

    if re.search(negative_pattern, choice, re.IGNORECASE):
        return {**result, "error": "invalid_choice"}

    # Get the selected airport code
    selected_code = next(iter(matched_codes))

    # Find the matching airport
    for airport in result["airports"]:
        if airport["iata_code"].upper() == selected_code:
            return {
                "status": "resolved",
                "airport": airport,
                "airports": [airport],
                "country_codes": result["country_codes"],
                "selection_mode": "single"
            }

    # Ask again if no airport was selected
    return {**result, "error": "invalid_choice"}



if __name__ == "__main__":
    # Test city normalization
    assert normalize_city("İstanbul") == "istanbul"
    assert normalize_city("ISTANBUL") == "istanbul"
    assert normalize_city("İZMİR") == "izmir"
    assert normalize_city("München") == "munchen"

    print("All normalization tests passed!")