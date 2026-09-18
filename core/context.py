from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    # Store the actual user message for this request
    user_message: str

    # Allow an explicit output language when available
    response_language: str | None = None

    # Mark whether this request is an active comparison research task
    research_active: bool = False

    # Mark whether user interaction is allowed
    interactive: bool = True

    # Identify the active task
    task_id: str | None = None

    # Identify the user turn for this task
    turn_id: int | None = None