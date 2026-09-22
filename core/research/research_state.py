from dataclasses import dataclass, field



@dataclass
class ResearchState:
    # Original research request
    query: str

    visited_urls: set[str] = field(default_factory=set)  # set: Store visited URLs without duplicates.  

    visited_sources: set[str] = field(default_factory=set)  # set: Store visited sources without duplicates.

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


    def register_url(self, url: str) -> bool:
        cleaned_url = url.strip()

        if not cleaned_url:
            return False

        # Do not visit same url
        if cleaned_url in self.visited_urls:
            return False

        # Store new url
        self.visited_urls.add(cleaned_url)

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