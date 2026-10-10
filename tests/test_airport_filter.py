
import csv
import time
from pathlib import Path

# Find the airport CSV file
CSV_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "airports.csv"
)

# Airports we want to check
TEST_CODES = {
    "IST", "SAW", "ISL",
    "LHR", "LGW", "STN",
    "LTN", "LCY", "SEN",
    "NHT", "BQH", "TTK",
}

# Store matching airport records
airports = {}

# Start the timer
start_time = time.perf_counter()

# Open and read the CSV file
with CSV_PATH.open(
    "r",
    encoding="utf-8",
    newline=""
) as file:

    reader = csv.DictReader(file)

    for row in reader:
        code = row.get("iata_code", "").strip()

        # Save matching airports
        if code in TEST_CODES:
            airports[code] = row

# Show airport information
for code in sorted(TEST_CODES):
    airport = airports.get(code)

    if airport is None:
        print(f"{code}: Not found")
        continue

    print(
        f"{code} | "
        f"{airport['name']} | "
        f"Type: {airport['type']} | "
        f"Scheduled: {airport['scheduled_service']}"
    )

# Calculate total reading time
elapsed = time.perf_counter() - start_time

print(f"\nExecution time: {elapsed:.4f} seconds")
