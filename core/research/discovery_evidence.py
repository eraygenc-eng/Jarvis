"""Separate actual product discovery from page-wide text and access failures."""

import re

from core.research.evidence import BrowserObservation
from core.research.quote_evidence import SnapshotIndex, visible_text
from core.research.research_utils import get_product_identity_conflict


ACCESS_FAILURE = re.compile(
    r"recaptcha|ben robot değilim|access denied|forbidden|you have been blocked|"
    r"unable to access|erişim engell|siteye erişemiyorsunuz|güvenlik doğrulaması|"
    r"verify you are|unusual traffic|sıra dışı bir trafik|page not available|"
    r"page not found|aradığın içeriğe şu an ulaşılamıyor|"
    r'heading [\"\']?(?:403|404|429)\b', re.I,
)


def access_failure_excerpt(observation: BrowserObservation) -> str | None:
    """Return copied evidence, never an LLM's description of the failure."""
    if observation.kind == "error":
        return observation.page_text.strip()
    return next((line.strip() for line in observation.page_text.splitlines()
                 if ACCESS_FAILURE.search(line)), None)


def has_discovery_identity(page: str, target: str, title: str) -> bool:
    """Match one visible candidate, not recommendations elsewhere on the page.

    This proves discovery only. Exact seller/price binding is checked later.
    """
    index = SnapshotIndex(page)
    candidates = []
    for node in index.nodes:
        if re.search(r"arama sonuç|search results|ürün bulundu|sonuç bulundu", node.line, re.I):
            continue
        # Shopping cards can render their title as a generic text node or a
        # YAML-quoted button. Never concatenate a generic container's children:
        # unrelated cards could supply missing identity tokens that way.
        if re.search(r"- ['\"]?(?:heading|link)\b", node.line):
            candidates.append(visible_text(index.text(node)))
        elif re.search(r"- ['\"]?(?:generic|text|button)\b", node.line):
            candidates.append(visible_text(node.line))
    if not index.nodes:  # Plain-text browser observations are also supported.
        candidates = [page]
    return any(candidate.strip()
               and get_product_identity_conflict(target, candidate) is None
               and get_product_identity_conflict(title, candidate) is None
               for candidate in candidates)
