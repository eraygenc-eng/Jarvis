from core.research.research_state import ResearchState


class ResearchController:
    """Control the research flow with deterministic rules."""

    def __init__(self, state: ResearchState):
        # Store the current research state
        self.state = state


    def should_stop(self) -> bool:
        # Check if research should stop
        return self.state.should_stop()

    def start_step(self) -> bool:
        if self.should_stop():
            return False

        # Record the new research step
        return self.state.record_step()


    def reset_navigation_attempts(self) -> None:
        # Start a fresh navigation history for a new agent turn
        self.state.reset_navigation_attempts()


    def has_attempted_url(self, url: str) -> bool:
        # Check whether this URL was already attempted in this turn
        return self.state.has_attempted_url(url)


    def register_navigation_attempt(self, url: str) -> bool:
        # Store this navigation attempt for the current turn
        return self.state.register_navigation_attempt(url)


    def has_visited_url(self, url: str) -> bool:
        # Check the URL without changing research state
        return self.state.has_visited_url(url)


    def register_url(self, url: str) -> bool:
        # Do not accept new URLs after research stops
        if self.should_stop():
            return False

        return self.state.register_url(url)


    def register_source(self, source: str) -> bool:
        # Do not accept new sources after research stops
        if self.should_stop():
            return False

        return self.state.register_source(source)


    def has_visited_source(self, source: str) -> bool:
        # Check if this source was already visited
        return self.state.has_visited_source(source)


    def is_domain_allowed(self, source: str) -> bool:
        # Check if this domain is allowed by the research plan
        return self.state.is_domain_allowed(source)


    def has_dynamic_sources(self) -> bool:
        # Check if this research contains dynamic sources
        return self.state.has_dynamic_sources()


    def register_dynamic_domain(self, source: str, domain: str) -> bool:
        # Register a domain for a planned dynamic source
        return self.state.register_dynamic_domain(source, domain)


    def is_dynamic_domain_allowed(self, domain: str) -> bool:
        # Check if a dynamic domain was already registered
        return self.state.is_dynamic_domain_allowed(domain)


    def record_progress(self) -> None:
        # Reset the no-progress counter
        self.state.record_progress()

    def record_no_progress(self) -> None:
        # Increase the no-progress counter
        self.state.record_no_progress()


    def finish(self, reason: str) -> None:
        # Mark research as a finished
        self.state.finished = True

        # Save why the research finished
        self.state.finish_reason = reason


    def get_status(self) -> dict:
        return {
            "steps": self.state.step_count,
            "max_steps": self.state.max_steps,
            "sites": len(self.state.visited_sources),
            "max_sites": self.state.max_sites,
            "no_progress": self.state.no_progress_count,
            "max_no_progress": self.state.max_no_progress,
            "finished": self.state.finished,
        }