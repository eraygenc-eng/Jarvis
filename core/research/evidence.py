import re

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlparse


@dataclass(frozen=True)
class BrowserObservation:
    observation_id: str
    page_url: str
    page_text: str
    captured_at: datetime
    kind: str = "page"


class ObservationStore:
    def __init__(self):
        self._observations: dict[str, BrowserObservation] = {}
        self.current_observation_id: str | None = None

    def capture(
        self,
        page_url: str,
        page_text: str,
        kind: str = "page",
    ) -> BrowserObservation:
        # Call only with data returned by the browser.
        if not page_url.strip() or not page_text.strip():
            raise ValueError("Browser URL and page text are required.")

        observation = BrowserObservation(
            observation_id=str(uuid4()),
            page_url=page_url,
            page_text=page_text,
            captured_at=datetime.now(timezone.utc),
            kind=kind,
        )

        self._observations[observation.observation_id] = observation
        self.current_observation_id = observation.observation_id
        return observation

    def require_evidence(self, observation_id: str) -> BrowserObservation:
        """Read a real recorded page/error without pretending it is current."""
        observation = self.get(observation_id.strip())
        if observation is None:
            raise ValueError("A stored browser Observation ID is required as evidence.")
        return observation

    def invalidate_current(self) -> None:
        """Browser actions invalidate the claim that an old snapshot is current."""
        self.current_observation_id = None

    def require_current(self, observation_id: str, max_age_seconds: int = 300) -> BrowserObservation:
        observation = self.get(observation_id.strip())
        if observation is None:
            raise ValueError("Browser observation not found. Call browser_snapshot first.")
        if observation.kind != "page":
            raise ValueError("A browser error cannot verify an offer. Take a successful browser_snapshot.")
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



def _extract_ref_from_line(
    line: str,
) -> str | None:
    # Read the semantic ref from one snapshot line
    match = re.search(
        r"\[ref=([^\]]+)\]",
        line,
    )

    if match is None:
        return None

    return match.group(1)


def _find_parent_ref(
    lines: list[str],
    index: int,
) -> str | None:
    # Find the nearest parent node that has a semantic ref
    current_indent = (
        len(lines[index])
        - len(lines[index].lstrip(" "))
    )

    for parent_index in range(index - 1, -1, -1):
        line = lines[parent_index]

        if not line.strip():
            continue

        indent = (
            len(line)
            - len(line.lstrip(" "))
        )

        if indent >= current_indent:
            continue

        current_indent = indent

        ref = _extract_ref_from_line(line)

        if ref is not None:
            return ref

    return None


def get_interactive_snapshot(page_text: str, *, max_chars: int = 24000, max_controls: int = 120) -> str:
    """Build a small snapshot with interactive controls."""

    # Keep controls that can be used for browser actions
    interactive_roles = {
        "textbox",
        "searchbox",
        "combobox",
        "button",
        "checkbox",
        "radio",
        "option",
        "spinbutton",
        "switch",
        "gridcell",
        "link",
        "tab",
        "menuitem",
    }

    lines = page_text.splitlines()

    # Read the role from each snapshot line
    role_pattern = re.compile(
        r"^\s*-\s+([a-zA-Z][\w-]*)\b",
        re.IGNORECASE,
    )

    controls: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        role_match = role_pattern.search(line)

        if role_match is None:
            continue

        role = role_match.group(1).casefold()

        # Skip non-interactive roles
        if role not in interactive_roles:
            continue

        ref = _extract_ref_from_line(line)

        # Skip controls without a ref
        if ref is None:
            continue

        controls.append((index, ref))

    if not controls:
        return ""

    blocks: list[str] = []
    used_refs: set[str] = set()
    total_chars = 0

    
    # Preserve the original page order for ordinary form controls.
    ordered_controls = controls[:max_controls]

    # On large pages, reserve a small number of slots for confirmation controls.
    # Keep initial form fields visible and respect intentionally small limits.
    if (
        max_controls >= 8
        and max_chars >= 1000
        and (len(controls) > max_controls or len(page_text) > max_chars)
    ):
        prefix_count = min(4, max_controls)
        prefix = controls[:prefix_count]

        confirmation_pattern = re.compile(
            r"\b(?:tamam|onayla|uygula|confirm|apply|done|ok)\b",
            re.IGNORECASE,
        )

        confirmation_controls = [
            (index, ref)
            for index, ref in controls[prefix_count:]
            if (
                re.match(
                    r"^\s*-\s*(?:button|link|generic)\b",
                    lines[index],
                    re.IGNORECASE,
                )
                and confirmation_pattern.search(lines[index])
            )
        ][:2]

        if confirmation_controls:
            important_refs = {
                ref for _, ref in confirmation_controls
            }

            remaining_controls = [
                control
                for control in controls[prefix_count:]
                if control[1] not in important_refs
            ]

            remaining_slots = (
                max_controls
                - len(prefix)
                - len(confirmation_controls)
            )

            ordered_controls = (
                prefix
                + confirmation_controls
                + remaining_controls[:remaining_slots]
            )

    for index, ref in ordered_controls:

        # Do not add the same ref twice
        if ref in used_refs:
            continue


        try:
            # Read the control and its child nodes
            block = get_snapshot_subtree(
                page_text,
                ref
            )

        except ValueError:
            # Use only the current line if subtree reading fails
            block = lines[index]

        # Keep nearby text for labels
        context_start = max(
            0,
            index - 2,
        )

        context_lines: list[str] = []

        for context_line in lines[context_start:index]:
            context_role_match = role_pattern.search(
                context_line
            )

            if context_role_match is not None:
                context_role = (
                    context_role_match
                    .group(1)
                    .casefold()
                )

                # Do not add another control as context
                if context_role in interactive_roles:
                    continue

            context_lines.append(context_line)

        nearby_context = "\n".join(
            context_lines
        ).strip()

        if nearby_context:
            block = (
                f"{nearby_context}\n"
                f"{block}"
            )

        # Keep one control from becoming too large
        if len(block) > 3000:
            block = (
                block[:3000].rstrip()
                + "\n..."
            )

        # Stop before the final snapshot becomes too large
        if(total_chars and total_chars + len(block) > max_chars):
            break

        blocks.append(block)
        used_refs.add(ref)
        total_chars += len(block)

        # Stop if no blocks could be created
    if not blocks:
        return ""

    return (
        "INTERACTIVE BROWSER SNAPSHOT\n"
        "Only interactive controls and nearby context are shown here. "
        "The complete snapshot remains stored as evidence.\n\n"
        + "\n\n---\n\n".join(blocks)
    )




def get_focused_snapshot(
    page_text: str,
    focus: str,
    *,
    page_url: str | None = None,
    max_chars: int = 30000,
    max_matches: int = 8,
) -> str:
    """Build a smaller model-facing snapshot around relevant nodes."""

    cleaned_focus = " ".join(
        focus.casefold().split()
    )

    # Split the focus into meaningful search terms
    focus_terms = [
        term
        for term in re.findall(
            r"[\w+-]+",
            cleaned_focus,
        )
        if len(term) > 1 or term.isdigit()
    ]

    if not focus_terms:
        return ""

    lines = page_text.splitlines()
    matching_indices: list[int] = []

    # Words that describe the task, not the actual item identity
    ignored_terms = {
        "price",
        "prices",
        "fiyat",
        "fiyatı",
        "fiyati",
        "fiyatlar",
        "seller",
        "sellers",
        "satıcı",
        "satıcılar",
        "shipping",
        "kargo",
        "warranty",
        "garanti",
        "product",
        "products",
        "ürün",
        "ürünler",
        "offer",
        "offers",
        "teklif",
        "teklifler",
        "listing",
        "listings",
        "result",
        "results",
        "sonuç",
        "sonuçlar",
        "show",
        "göster",
        "find",
        "bul",
        "look",
        "bak",
        "current",
        "güncel",
        "page",
        "sayfa",
        "and",
        "ve",
        "with",
        "ile",
        "for",
        "için",
        "search",
        "arama",
        "searchbox",
        "sonucu",
        "sonuçları",
        "ilan",
        "ilanlar",
        "ilanı",
        "ilanları",
        "list",
        "liste",
        "listesi",
        "site",
        "website",
        "name",
        "names",
        "link",
        "links",
        "ana",
        "home",
        "homepage",
        "main",
    }

    # Do not treat the current website name as product identity
    if page_url:
        hostname = urlparse(page_url).hostname or ""

        source_terms = {
            part
            for part in re.split(
                r"[.\-_]+",
                hostname.casefold(),
            )
            if (
                len(part) > 2
                and part not in {
                    "www",
                    "com",
                    "net",
                    "org",
                }
            )
        }

        ignored_terms.update(source_terms)

    # Ignore inflected task words as well.
    # Example:
    # "ürünleri", "fiyatları", "satıcıları"
    # should not become part of the product identity.
    ignored_prefixes = {
        "fiyat",
        "ürün",
        "urun",
        "satıcı",
        "satici",
        "kargo",
        "garanti",
        "teklif",
        "sonuç",
        "sonuc",
        "ilan",
        "liste",
        "arama",
    }

    def is_identity_term(term: str) -> bool:
        if term in ignored_terms:
            return False

        if any(
            term.startswith(prefix)
            for prefix in ignored_prefixes
        ):
            return False

        return True

    identity_terms = [
        term
        for term in focus_terms
        if is_identity_term(term)
    ]

    if not identity_terms:
        identity_terms = focus_terms


    def term_matches_line(
        term: str,
        normalized_line: str,
    ) -> bool:
        # Common accessibility-tree names for UI controls
        aliases = {
            "search": (
                "search",
                "searchbox",
                "textbox",
                "arama",
                "ara",
            ),
            "arama": (
                "search",
                "searchbox",
                "textbox",
                "arama",
                "ara",
            ),
            "box": (
                "box",
                "textbox",
                "searchbox",
                "input",
            ),
            "kutusu": (
                "box",
                "textbox",
                "searchbox",
                "input",
            ),
        }

        candidates = aliases.get(
            term,
            (term,),
        )

        return any(
            candidate in normalized_line
            for candidate in candidates
        )


    term_count = len(identity_terms)

    if term_count == 1:
        minimum_matches = 1

    elif term_count == 2:
        minimum_matches = 2

    else:
        # Three strong identity terms are enough to find
        # a relevant product/container region.
        minimum_matches = 3


    for index, line in enumerate(lines):
        normalized_line = " ".join(
            line.casefold().split()
        )

        matched_terms = sum(
            1
            for term in identity_terms
            if term_matches_line(
                term,
                normalized_line,
            )
        )

        if matched_terms >= minimum_matches:
            matching_indices.append(index)

    if not matching_indices:
        return ""

    blocks: list[str] = []
    used_refs: set[str] = set()
    total_chars = 0

    for index in matching_indices[:max_matches]:
        own_ref = _extract_ref_from_line(
            lines[index]
        )

        parent_ref = _find_parent_ref(
            lines,
            index,
        )

        # Prefer the parent because price/seller are often siblings
        selected_ref = parent_ref or own_ref

        if selected_ref is None:
            continue

        if selected_ref in used_refs:
            continue

        try:
            block = get_snapshot_subtree(
                page_text,
                selected_ref,
            )
        except ValueError:
            continue

        # Avoid accidentally selecting a huge page-level container
        if len(block) > 12000:
            start = max(0, index - 6)
            end = min(
                len(lines),
                index + 25,
            )

            block = "\n".join(
                lines[start:end]
            )

        if (
            total_chars
            and total_chars + len(block)
            > max_chars
        ):
            break

        blocks.append(block)
        used_refs.add(selected_ref)
        total_chars += len(block)

    if not blocks:
        return ""

    return (
        "FOCUSED BROWSER SNAPSHOT\n"
        f"Focus: {focus}\n"
        "Only relevant page regions are shown here. "
        "The complete snapshot remains stored as evidence.\n\n"
        + "\n\n---\n\n".join(blocks)
    )