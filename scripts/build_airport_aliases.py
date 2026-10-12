from core.airport_resolver import build_airport_alias_candidates


def save_airport_aliases(conn, airport_id, municipality, keywords):
    # Generate alias candidates for the airport
    candidates = build_airport_alias_candidates(
        airport_id,
        municipality,
        keywords
    )

    # Create a database cursor
    with conn.cursor() as cur:

        # Save each alias candidate
        for candidate in candidates:
            cur.execute("""
                INSERT INTO public.airport_city_aliases (
                    airport_id,
                    alias,
                    source
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (airport_id, alias, source)
                DO NOTHING;
            """, (
                candidate["airport_id"],
                candidate["alias"],
                candidate["source"]
            ))

    return len(candidates)



def import_all_airport_aliases(conn, batch_size=500, limit=None):
    # Validate input values
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    if limit is not None and limit < 0:
        raise ValueError("limit cannot be negative")


    total_airports = 0
    total_candidates = 0
    last_id = 0


    with conn.cursor() as read_cur, conn.cursor() as write_cur:

        while limit is None or total_airports < limit:
            # Calculate how many airports to read
            current_batch_size = batch_size


            if limit is not None:
                remaining = limit - total_airports
                current_batch_size = min(batch_size, remaining)

            # Read the next batches
            read_cur.execute("""
                SELECT id, municipality, keywords
                FROM public.airports
                WHERE id > %s
                AND iata_code IS NOT NULL
                AND TRIM(iata_code) <> ''
                AND scheduled_service = TRUE
                ORDER BY id
                LIMIT %s
            """, (last_id, current_batch_size))

            # Get all rows from the sql query result
            airports = read_cur.fetchall()

            
            # Stop when there are no more airports
            if not airports:
                break

            alias_rows = []

            # Generate aliases for each airport
            for airport_id, municipality, keywords in airports:
                candidates = build_airport_alias_candidates(
                    airport_id,
                    municipality,
                    None
                )

                # Collect generated aliases
                for candidate in candidates:
                    alias_rows.append((
                        candidate["airport_id"],
                        candidate["alias"],
                        candidate["source"]
                    ))

            # Insert aliases into PostgreSQL
            if alias_rows:
                write_cur.executemany("""
                    INSERT INTO public.airport_city_aliases (
                        airport_id,
                        alias,
                        source
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (airport_id, alias, source)
                    DO NOTHING;
                """, alias_rows)

            # Save the current batch
            conn.commit()

            # Update counters
            total_airports += len(airports)
            total_candidates += len(alias_rows)

            # Remember the last processed airport
            last_id = airports[-1][0]

            print(
                f"Processed airports: {total_airports}, "
                f"Generated aliases: {total_candidates}"
            )

    return {
        "total_airports": total_airports,
        "total_candidates": total_candidates
    }
