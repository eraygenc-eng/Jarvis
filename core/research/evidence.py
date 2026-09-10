import re

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class BrowserObservation:
    observation_id: str
    page_url: str
    page_text: str
    captured_at: datetime


class ObservationStore:
    def __init__(self):
        self._observations: dict[str, BrowserObservation] = {}
        self.current_observation_id: str | None = None

    def capture(
        self,
        page_url: str,
        page_text: str,
    ) -> BrowserObservation:
        # Call only with data returned by the browser.
        if not page_url.strip() or not page_text.strip():
            raise ValueError("Browser URL and page text are required.")

        observation = BrowserObservation(
            observation_id=str(uuid4()),
            page_url=page_url,
            page_text=page_text,
            captured_at=datetime.now(timezone.utc),
        )

        self._observations[observation.observation_id] = observation
        self.current_observation_id = observation.observation_id
        return observation

    def invalidate_current(self) -> None:
        """Browser actions invalidate the claim that an old snapshot is current."""
        self.current_observation_id = None

    def require_current(self, observation_id: str, max_age_seconds: int = 300) -> BrowserObservation:
        observation = self.get(observation_id.strip())
        if observation is None:
            raise ValueError("Browser observation not found. Call browser_snapshot first.")
        if observation.observation_id != self.current_observation_id:
            raise ValueError("The observation is no longer current. Call browser_snapshot again.")
        age = (datetime.now(timezone.utc) - observation.captured_at).total_seconds()
        if age < 0 or age > max_age_seconds:
            raise ValueError("The observation has expired. Call browser_snapshot again.")
        return observation

    def get(
        self,
        observation_id: str,
    ) -> BrowserObservation | None:
        return self._observations.get(observation_id)

def get_snapshot_subtree(
    page_text: str,
    ref: str,
) -> str:
    """Return one snapshot node and its descendants."""

    ref = ref.strip()

    if not ref:
        raise ValueError("Snapshot reference is required.")

    lines = page_text.splitlines()

    pattern = re.compile(
        r"^([ ]*)- .*\[ref=" + re.escape(ref) + r"\]"
    )

    matches = []

    for index, line in enumerate(lines):
        match = pattern.search(line)

        if match:
            matches.append((index, len(match.group(1))))

    if len(matches) != 1:
        raise ValueError(
            "Snapshot reference must identify exactly one node."
        )

    start, indent = matches[0]
    end = len(lines)

    # Stop at the next sibling or ancestor.
    for index in range(start + 1, len(lines)):
        line = lines[index]

        if not line.strip():
            continue

        current_indent = len(line) - len(line.lstrip(" "))

        if current_indent <= indent:
            end = index
            break

    return "\n".join(lines[start:end])
