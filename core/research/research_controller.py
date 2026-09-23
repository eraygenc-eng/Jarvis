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