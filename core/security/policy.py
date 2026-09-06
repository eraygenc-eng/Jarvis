import ipaddress

from urllib.parse import urlparse
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SecurityAction(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    BLOCK = "block"


@dataclass
class SecurityDecision:
    action: SecurityAction
    reason: str


# Tools that are always blocked
BLOCKED_TOOLS = {
    "browser_run_code_unsafe",
}


# Tools that always need user confirmation
CONFIRM_TOOLS = {
    "browser_file_upload",
    "close_application",
}


# Tools that may perform sensitive actions
ACTION_TOOLS = {
    "browser_click",
    "browser_press_key",
    "browser_select_option",
}


# Keywords that may indicate a sensitive action
SENSITIVE_KEYWORDS = {
    "delete",
    "remove",
    "purchase",
    "buy",
    "checkout",
    "payment",
    "pay",
    "send",
    "submit",
    "publish",
    "cancel",
    "unsubscribe",
    "login",
    "sign in",
    "change password",
    "sil",
    "satın al",
    "ödeme",
    "öde",
    "gönder",
    "yayınla",
    "iptal",
    "giriş yap",
    "şifre değiştir",
}

def check_url_safety(url: str) -> SecurityDecision | None:
    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception:
        return SecurityDecision(
            action=SecurityAction.BLOCK,
            reason="The URL could not be parsed safely.",
        )

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()

    # Allow only normal web protocols
    if scheme not in {"http", "https"}:
        return SecurityDecision(
            action=SecurityAction.BLOCK,
            reason=f"URL scheme '{scheme}' is not allowed.",
        )

    # Block URLs with embedded credentials
    if parsed.username or parsed.password:
        return SecurityDecision(
            action=SecurityAction.BLOCK,
            reason="URLs with embedded credentials are not allowed.",
        )

    # Ask before accessing localhost
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return SecurityDecision(
            action=SecurityAction.CONFIRM,
            reason="The browser wants to access a local service.",
        )

    # Check direct IP addresses
    try:
        ip = ipaddress.ip_address(hostname)

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
        ):
            return SecurityDecision(
                action=SecurityAction.CONFIRM,
                reason="The browser wants to access a private or local network address.",
            )

    except ValueError:
        # The hostname is a domain name, not an IP address
        pass

    return None


def evaluate_tool_call(
    tool_name: str,
    arguments: Any,
) -> SecurityDecision:

    # Block dangerous tools
    if tool_name in BLOCKED_TOOLS:
        return SecurityDecision(
            action=SecurityAction.BLOCK,
            reason=f"{tool_name} is blocked for security reasons.",
        )

    # Ask for confirmation for sensitive tools
    if tool_name in CONFIRM_TOOLS:
        return SecurityDecision(
            action=SecurityAction.CONFIRM,
            reason=f"{tool_name} requires user confirmation.",
        )

    # Check URL safety
    if isinstance(arguments, dict):
        url = arguments.get("url")

        if isinstance(url, str):
            url_decision = check_url_safety(url)

            if url_decision is not None:
                return url_decision

    # Only check keywords for action tools
    if tool_name in ACTION_TOOLS:
        arguments_text = str(arguments).lower()

        for keyword in SENSITIVE_KEYWORDS:
            if keyword in arguments_text:
                return SecurityDecision(
                    action=SecurityAction.CONFIRM,
                    reason=f"Sensitive action detected: {keyword}",
                )

    # Allow low-risk actions
    return SecurityDecision(
        action=SecurityAction.ALLOW,
        reason="Low-risk action.",
    )