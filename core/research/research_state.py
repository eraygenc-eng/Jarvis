from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit



TRACKING_QUERY_KEYS = {
    "gclid",
    "fbclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
}


def normalize_url(url: str) -> str:
    cleaned_url = url.strip()

    if not cleaned_url:
        return ""

    try:
        parsed = urlsplit(cleaned_url)

    except ValueError:
        return cleaned_url

    # Keep non-web URLs unchanged
    if parsed.scheme.lower() not in {"http", "https"}:
        return cleaned_url

    # Keep useful query parameters
    query_items = []

    for key, value in parse_qsl(
        parsed.query,
        keep_blank_values=True
    ):
        normalized_key = key.lower()

        # Ignore UTM tracking parameters
        if normalized_key.startswith("utm_"):
            continue

        # Ignore other known tracking parameters
        if normalized_key in TRACKING_QUERY_KEYS:
            continue

        query_items.append((key, value))

    normalized_query = urlencode(
        query_items,
        doseq=True  # Convert query items back into a valid URL query string
    )

    # Scheme and domain are case-insensitive
    normalized_scheme = parsed.scheme.lower()
    normalized_domain = parsed.netloc.lower()

    # Url'yi tekrar birleştir
    return urlunsplit(
        (
            normalized_scheme,
            normalized_domain,
            parsed.path,
            normalized_query,
            parsed.fragment,
        )
    )


@dataclass
class ResearchState:
    # Original research request
    query: str

    visited_urls: set[str] = field(default_factory=set)  # set: Store visited URLs without duplicates.  

    # Store URLs attempted during the current agent turn
    navigation_attempt_urls: set[str] = field(default_factory=set)

    visited_sources: set[str] = field(default_factory=set)

    # Number of research actions
    step_count: int = 0

    max_steps: int = 20
    max_sites: int = 6


    # Detect research that is not making progress
    no_progress_count: int = 0
    max_no_progress: int = 3


    # Final research state
    finished: bool = False
    finish_reason: str | None = None


    def reset_navigation_attempts(self) -> None:
        # Start a fresh navigation history for a new agent turn
        self.navigation_attempt_urls.clear()


    def has_attempted_url(self, url: str) -> bool:
        normalized_url = normalize_url(url)

        if not normalized_url:
            return False


        # Check whether this URL was already attempted in this turn
        return normalized_url in self.navigation_attempt_urls


    def register_navigation_attempt(self, url: str) -> bool:
        normalized_url = normalize_url(url)

        if not normalized_url:
            return False

        # Don't register the same attempt twice
        if normalized_url in self.navigation_attempt_urls:
            return False


        # Store this navigation attempt for the current turn
        self.navigation_attempt_urls.add(normalized_url)

        return True
    


    def has_visited_url(self, url: str) -> bool:
        normalized_url = normalize_url(url)

        if not normalized_url:
            return False

        # Check without changing the research state
        return normalized_url in self.visited_urls


    def register_url(self, url: str) -> bool:
        # Create one stable URL for duplicate detection
        normalized_url = normalize_url(url)

        if not normalized_url:
            return False

        # Do not visit the same URL twice
        if normalized_url in self.visited_urls:
            return False

        # Store the normalized URL
        self.visited_urls.add(normalized_url)

        return True


    def register_source(self, source: str) -> bool:

        cleaned_source = source.strip().lower()

        if not cleaned_source:
            return False

        if cleaned_source in self.visited_sources:
            return False


        # Stop adding new source after the limit
        if len(self.visited_sources) >= self.max_sites:
            return False


        # Store new sources
        self.visited_sources.add(cleaned_source)

        return True



    # Blocking endless browsing loop
    def record_step(self) -> bool:

        if self.step_count >= self.max_steps:
            return False

        # Count this research action
        self.step_count += 1

        return True



    def record_progress(self) -> None:
        # Reset the counter when useful progress is made
        self.no_progress_count = 0


    def record_no_progress(self) -> None:
        # Count a research action that made no useful progress
        self.no_progress_count += 1


    def should_stop(self) -> bool:
        # Stop if research is already finished
        if self.finished:
            return True # Has to stop


        if self.step_count >= self.max_steps:
            self.finished = True
            self.finish_reason = "max_steps_reached"
            return True # Has to stop

        if self.no_progress_count >= self.max_no_progress:
            self.finished = True
            self.finish_reason = "no_progress"
            return True # Has to stop

        return False