from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    # Store the actual user message for this request.
    user_message: str

    # Allow an explicit output language when available.
    response_language: str | None = None