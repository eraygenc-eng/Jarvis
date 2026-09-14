"""Resolve evidence from snapshot nodes and reject mixed offer containers."""

import re
from dataclasses import dataclass


def clean(value: str) -> str:
    return " ".join(value.split()).casefold()


@dataclass
class SnapshotNode:
    start: int
    end: int
    indent: int
    line: str
    parent: "SnapshotNode | None"


class SnapshotIndex:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.nodes = []
        self.refs = {}
        stack = []
        for position, line in enumerate(self.lines):
            match = re.match(r"^( *)- (.*)", line)
            if not match:
                continue
            indent = len(match[1])
            while stack and stack[-1].indent >= indent:
                stack.pop().end = position
            node = SnapshotNode(position, len(self.lines), indent, line,
                                stack[-1] if stack else None)
            self.nodes.append(node)
            stack.append(node)
            ref = re.search(r"\[ref=([^\]]+)\]", line)
            if ref:
                if ref[1] in self.refs:
                    raise ValueError("Snapshot reference must identify exactly one node.")
                self.refs[ref[1]] = node

    def node(self, ref: str) -> SnapshotNode:
        if ref not in self.refs:
            raise ValueError(f"Unknown snapshot reference {ref!r}. Take a fresh snapshot and select its refs.")
        return self.refs[ref]

    def text(self, node: SnapshotNode) -> str:
        return "\n".join(self.lines[node.start:node.end])

    def read(self, ref: str) -> str:
        return self.text(self.node(ref))

    def locate(self, excerpt: str, *, heading: bool = False) -> SnapshotNode:
        refs = re.findall(r"\[ref=([^\]]+)\]", excerpt)
        if refs:
            return self.node(refs[0])
        matches = [n for n in self.nodes if clean(excerpt) in clean(self.text(n))]
        if heading:
            headings = [n for n in matches if re.search(r"- heading\b", n.line)]
            matches = headings or matches
        if not matches:
            raise ValueError("Evidence is outside the selected offer subtree.")
        return min(matches, key=lambda n: n.end - n.start)


def contains(parent: SnapshotNode, child: SnapshotNode) -> bool:
    return parent.start <= child.start < parent.end


def validate_relationships(scope: str, identity: str, seller: str, price: str) -> None:
    """A broad root must not bridge independent product or seller cards.

    Product pages often keep their title outside the purchase controls. Permit
    that layout, but do not borrow a title/seller from another purchase card.
    """
    index = SnapshotIndex(scope)
    identity_node = index.locate(identity, heading=True)
    seller_node = index.locate(seller)
    price_nodes = [index.node(ref) for ref in re.findall(r"\[ref=([^\]]+)\]", price)]
    for price_node in price_nodes:
        ancestor = price_node.parent
        while ancestor:
            if contains(ancestor, identity_node) and contains(ancestor, seller_node):
                break
            text = index.text(ancestor)
            # An independently titled card owns its prices.
            if re.search(r"(?m)^ *- heading\b", text) and not contains(ancestor, identity_node):
                raise ValueError("Price and identity belong to different offer containers.")
            # Repeated marketplace seller cards may share the page's product title.
            has_purchase = re.search(r"button [\"']?(?:Sepete Ekle|Add to (?:cart|basket)|Buy now)", text, re.I)
            destinations = re.findall(r"(?m)^ *- /url: [\"']?([^\s\"']+)", text)
            navigable_links = [url for url in destinations if url.startswith(("http://", "https://", "/")) and url != "/"]
            if has_purchase and navigable_links and not contains(ancestor, seller_node):
                raise ValueError("Price and seller belong to different offer containers.")
            ancestor = ancestor.parent
        # Symmetric check: a title in a different priced article cannot be shared.
        ancestor = identity_node.parent
        while ancestor and not contains(ancestor, price_node):
            if re.search(r"(?m)^ *- (?:article|listitem)\b", ancestor.line):
                raise ValueError("Identity and price belong to different offer containers.")
            ancestor = ancestor.parent


def visible_text(snapshot: str) -> str:
    """Remove snapshot metadata/URLs, so reference numbers never become prices."""
    lines = []
    for line in snapshot.splitlines():
        if re.match(r"\s*- /url:", line):
            continue
        line = re.sub(r"\[[^\]]*\]", "", line)
        line = re.sub(r"^\s*- (?:generic|text|heading|link|textbox|spinbutton|paragraph|strong|button)\s*:?\s*", "", line)
        lines.append(line.strip().strip("\"'"))
    return " ".join(lines)
