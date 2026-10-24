
from pathlib import Path
import zipfile
import sys


# Locate the GeoNames data directory
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Allow imports from the project root
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import get_db_connection
DATA_DIR = PROJECT_ROOT / "data" / "geonames"

files = [
    ("allCountries.zip", "allCountries.txt"),
    ("alternateNamesV2.zip", "alternateNamesV2.txt"),
]

for zip_name, txt_name in files:
    zip_path = DATA_DIR / zip_name

    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(txt_name) as file:
            first_line = file.readline().decode("utf-8")
            columns = first_line.rstrip("\r\n").split("\t")

            print(f"File: {txt_name}")
            print(f"Column count: {len(columns)}")
            print(f"First 4 fields: {columns[:4]}")
            print("-" * 40)



# Test PostgreSQL connection
conn = get_db_connection()

try:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM public.global_places),
                (SELECT COUNT(*) FROM public.global_place_names)
        """)

        places_count, names_count = cursor.fetchone()

        print("PostgreSQL connection successful!")
        print(f"Global places: {places_count}")
        print(f"Global place names: {names_count}")

finally:
    conn.close()




def read_sample_places(limit=100):
    records = []
    zip_path = DATA_DIR / "allCountries.zip"

    # Read records without extracting the ZIP
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("allCountries.txt") as file:

            for raw_line in file:
                fields = raw_line.decode("utf-8").rstrip("\r\n").split("\t")

                # Only include populated places
                if len(fields) != 19 or fields[6] != "P":
                    continue

                record = (
                    int(fields[0]),
                    fields[1],
                    fields[2] or None,
                    fields[8] or None,
                    fields[10] or None,
                    fields[11] or None,
                    fields[6],
                    fields[7],
                    float(fields[4]) if fields[4] else None,
                    float(fields[5]) if fields[5] else None,
                    int(fields[14]) if fields[14] else None,
                )

                records.append(record)

                if len(records) >= limit:
                    break

    return records



def insert_places_copy(records):
    if not records:
        return 0

    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:

            # Create a temporary staging table
            cursor.execute("""
                CREATE TEMP TABLE temp_global_places
                (LIKE public.global_places)
                ON COMMIT DROP
            """)

            # Copy records into the temporary table
            with cursor.copy("""
                COPY temp_global_places (
                    geoname_id,
                    name,
                    ascii_name,
                    country_code,
                    admin1_code,
                    admin2_code,
                    feature_class,
                    feature_code,
                    latitude,
                    longitude,
                    population
                )
                FROM STDIN
            """) as copy:

                for record in records:
                    copy.write_row(record)

            # Insert only records that do not exist
            cursor.execute("""
                INSERT INTO public.global_places (
                    geoname_id,
                    name,
                    ascii_name,
                    country_code,
                    admin1_code,
                    admin2_code,
                    feature_class,
                    feature_code,
                    latitude,
                    longitude,
                    population
                )
                SELECT
                    geoname_id,
                    name,
                    ascii_name,
                    country_code,
                    admin1_code,
                    admin2_code,
                    feature_class,
                    feature_code,
                    latitude,
                    longitude,
                    population
                FROM temp_global_places
                WHERE TRUE
                ON CONFLICT (geoname_id) DO NOTHING
            """)

            inserted = cursor.rowcount

        conn.commit()
        return inserted

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def import_all_places(batch_size=5000):
    zip_path = DATA_DIR / "allCountries.zip"

    batch = []
    processed = 0
    inserted = 0

    # Read ZIP without extracting
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("allCountries.txt") as file:

            for raw_line in file:
                fields = raw_line.decode("utf-8").rstrip("\r\n").split("\t")

                # Keep only populated places
                if len(fields) != 19 or fields[6] != "P":
                    continue

                record = (
                    int(fields[0]),
                    fields[1],
                    fields[2] or None,
                    fields[8] or None,
                    fields[10] or None,
                    fields[11] or None,
                    fields[6],
                    fields[7],
                    float(fields[4]) if fields[4] else None,
                    float(fields[5]) if fields[5] else None,
                    int(fields[14]) if fields[14] else None,
                )

                batch.append(record)

                # Insert every 5000 records
                if len(batch) >= batch_size:
                    inserted += insert_places_copy(batch)
                    processed += len(batch)
                    batch.clear()

                    if processed % 50000 == 0:
                        print(
                            f"Processed: {processed:,} | "
                            f"Inserted: {inserted:,}"
                        )

            # Insert remaining records
            if batch:
                inserted += insert_places_copy(batch)
                processed += len(batch)

    print("GeoNames import completed!")
    print(f"Total processed: {processed:,}")
    print(f"New records inserted: {inserted:,}")




def insert_place_names_copy(records):
    if not records:
        return 0

    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            # Create a temporary table
            cursor.execute("""
                CREATE TEMP TABLE temp_place_names (
                    alternate_name_id BIGINT,
                    geoname_id BIGINT,
                    language_code TEXT,
                    name TEXT,
                    is_preferred BOOLEAN,
                    is_short BOOLEAN,
                    is_colloquial BOOLEAN,
                    is_historic BOOLEAN
                ) ON COMMIT DROP
            """)

            # Copy records into staging table
            with cursor.copy("""
                COPY temp_place_names FROM STDIN
            """) as copy:
                for record in records:
                    copy.write_row(record)

            # Only import names of known populated places
            cursor.execute("""
                INSERT INTO public.global_place_names (
                    alternate_name_id,
                    geoname_id,
                    language_code,
                    name,
                    normalized_name,
                    is_preferred,
                    is_short,
                    is_colloquial,
                    is_historic
                )
                SELECT
                    n.alternate_name_id,
                    n.geoname_id,
                    n.language_code,
                    n.name,
                    LOWER(unaccent(n.name)),
                    n.is_preferred,
                    n.is_short,
                    n.is_colloquial,
                    n.is_historic
                FROM temp_place_names n
                JOIN public.global_places p
                    ON p.geoname_id = n.geoname_id
                ON CONFLICT (alternate_name_id) DO NOTHING
            """)

            inserted = cursor.rowcount

        conn.commit()
        return inserted

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def test_alternate_names(limit=5000):
    zip_path = DATA_DIR / "alternateNamesV2.zip"
    records = []

    # Read alternative names without extracting ZIP
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("alternateNamesV2.txt") as file:
            for raw_line in file:
                fields = raw_line.decode("utf-8").rstrip("\r\n").split("\t")

                if len(fields) != 10:
                    continue

                # Skip non-name identifiers
                if fields[2] in {
                    "link", "wkdt", "post",
                    "iata", "icao", "faac"
                }:
                    continue

                record = (
                    int(fields[0]),
                    int(fields[1]),
                    fields[2] or None,
                    fields[3],
                    fields[4] == "1",
                    fields[5] == "1",
                    fields[6] == "1",
                    fields[7] == "1",
                )

                records.append(record)

                if len(records) >= limit:
                    break

    inserted = insert_place_names_copy(records)

    print(f"Processed alternative names: {len(records)}")
    print(f"New names inserted: {inserted}")



def import_all_alternate_names(batch_size=5000):
    zip_path = DATA_DIR / "alternateNamesV2.zip"

    batch = []
    processed = 0
    inserted = 0

    # Read alternative names directly from ZIP
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("alternateNamesV2.txt") as file:

            for raw_line in file:
                fields = raw_line.decode("utf-8").rstrip("\r\n").split("\t")

                if len(fields) != 10:
                    continue

                # Skip non-name identifiers
                if fields[2] in {
                    "link", "wkdt", "post",
                    "iata", "icao", "faac"
                }:
                    continue

                record = (
                    int(fields[0]),
                    int(fields[1]),
                    fields[2] or None,
                    fields[3],
                    fields[4] == "1",
                    fields[5] == "1",
                    fields[6] == "1",
                    fields[7] == "1",
                )

                batch.append(record)

                # Insert records in batches
                if len(batch) >= batch_size:
                    inserted += insert_place_names_copy(batch)
                    processed += len(batch)
                    batch.clear()

                    if processed % 50000 == 0:
                        print(
                            f"Processed: {processed:,} | "
                            f"Inserted: {inserted:,}"
                        )

            # Insert remaining records
            if batch:
                inserted += insert_place_names_copy(batch)
                processed += len(batch)

    print("Alternative names import completed!")
    print(f"Total processed: {processed:,}")
    print(f"New names inserted: {inserted:,}")



if __name__ == "__main__":
    import_all_alternate_names(batch_size=5000)