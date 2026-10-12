from dataclasses import dataclass, field


@dataclass
class FlightRequest:
    """
    Store flight request information.
    """

    # Keep original user request
    original_prompt: str

    # Store departure and arrival cities
    departure_city: str | None = None
    arrival_city: str | None = None

    # Store airport IATA codes
    departure_airports: list[str] = field(default_factory=list)
    arrival_airports: list[str] = field(default_factory=list)