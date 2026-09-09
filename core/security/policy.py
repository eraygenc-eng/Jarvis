import re
import ipaddress

from urllib.parse import urlparse
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SecurityAction(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    BLOCK = "block"


class ToolPermission(str, Enum):
    ALLOW = "allow"
    CONDITIONAL = "conditional"
    CONFIRM = "confirm"
    BLOCK = "block"


@dataclass
class SecurityDecision:
    action: SecurityAction
    reason: str


# Define the default permission for each tool
TOOL_PERMISSIONS = {
    # Safe tools
    "calculator": ToolPermission.ALLOW,
    "web_search": ToolPermission.ALLOW,

    "research_status": ToolPermission.ALLOW,
    "research_mark_source_checked": ToolPermission.ALLOW,
    "research_add_result": ToolPermission.ALLOW,

    "browser_close": ToolPermission.ALLOW,
    "browser_resize": ToolPermission.ALLOW,
    "browser_console_messages": ToolPermission.ALLOW,
    "browser_find": ToolPermission.ALLOW,
    "browser_navigate_back": ToolPermission.ALLOW,
    "browser_network_requests": ToolPermission.ALLOW,
    "browser_network_request": ToolPermission.ALLOW,
    "browser_take_screenshot": ToolPermission.ALLOW,
    "browser_snapshot": ToolPermission.ALLOW,
    "browser_hover": ToolPermission.ALLOW,
    "browser_wait_for": ToolPermission.ALLOW,
    

    # Safe research verification tools
    "research_verify_result": ToolPermission.ALLOW,
    "research_finalize": ToolPermission.ALLOW,
    "research_start_source": ToolPermission.ALLOW,
    "research_complete_source": ToolPermission.ALLOW,
    "research_rankings": ToolPermission.ALLOW,
    "research_confirm_final_page": ToolPermission.ALLOW,
    "research_set_offer_url": ToolPermission.ALLOW,
    "research_confirm_staging_page": ToolPermission.ALLOW,
    "research_mark_staging_blocked": ToolPermission.ALLOW,

    # Tools that need extra checks
    "browser_navigate": ToolPermission.CONDITIONAL,
    "browser_click": ToolPermission.CONDITIONAL,
    "browser_fill_form": ToolPermission.CONDITIONAL,
    "browser_press_key": ToolPermission.CONDITIONAL,
    "browser_type": ToolPermission.CONDITIONAL,
    "browser_drag": ToolPermission.CONDITIONAL,
    "browser_select_option": ToolPermission.CONDITIONAL,
    "browser_tabs": ToolPermission.CONDITIONAL,
    "browser_handle_dialog": ToolPermission.CONDITIONAL,
    "browser_evaluate": ToolPermission.CONDITIONAL,

    # Tools that always need user confirmation
    "open_application": ToolPermission.CONFIRM,
    "close_application": ToolPermission.CONFIRM,
    "launch_game": ToolPermission.CONFIRM,
    "browser_file_upload": ToolPermission.CONFIRM,
    "browser_drop": ToolPermission.CONFIRM,


    # Tools that are always blocked
    "browser_run_code_unsafe": ToolPermission.BLOCK,
}


# Actions that may create an external or irreversible effect
SENSITIVE_ACTION_KEYWORDS = {
    # Purchase and payment
    "purchase",
    "buy now",
    "place order",
    "confirm order",
    "complete order",
    "complete purchase",
    "payment",
    "pay now",
    "confirm payment",

    # Booking and reservation
    "book now",
    "confirm booking",
    "complete booking",
    "reserve now",
    "confirm reservation",

    # Turkish purchase and payment
    "satın al",
    "satin al",
    "sipariş ver",
    "siparis ver",
    "siparişi tamamla",
    "siparisi tamamla",
    "ödemeye geç",
    "odemeye gec",
    "ödeme yap",
    "odeme yap",
    "öde",
    "ode",

    # Turkish booking and reservation
    "rezervasyon yap",
    "rezervasyonu tamamla",
    "rezervasyonu onayla",
    "bilet al",

    # Messaging and publishing
    "send",
    "publish",
    "gönder",
    "gonder",
    "yayınla",
    "yayinla",

    # Destructive account actions
    "delete",
    "remove",
    "cancel",
    "unsubscribe",
    "sil",
    "iptal",

    # Authentication and credentials
    "login",
    "sign in",
    "change password",
    "giriş yap",
    "giris yap",
    "şifre değiştir",
    "sifre degistir",

    # Payment credentials
    "credit card",
    "debit card",
    "card number",
    "cvv",
    "cvc",
    "iban",
    "kart numarası",
    "kart numarasi",
    "son kullanma tarihi",
}


def contains_sensitive_action(
    arguments: Any,
) -> str | None:
    # Convert tool arguments into searchable text
    arguments_text = str(arguments).casefold()

    for keyword in SENSITIVE_ACTION_KEYWORDS:
        normalized_keyword = keyword.casefold()

        # Multi-word phrases can be matched directly
        if " " in normalized_keyword:
            if normalized_keyword in arguments_text:
                return keyword

            continue

        # Use word boundaries for single words
        pattern = (
            rf"(?<!\w)"
            rf"{re.escape(normalized_keyword)}"
            rf"(?!\w)"
        )

        if re.search(pattern, arguments_text):
            return keyword

    return None


def check_browser_evaluate_safety(
    arguments: Any,
) -> SecurityDecision:
    # Require structured tool arguments
    if not isinstance(arguments, dict):
        return SecurityDecision(
            action=SecurityAction.CONFIRM,
            reason="Browser evaluate arguments could not be inspected safely.",
        )

    function = str(
        arguments.get("function", "")
    ).strip()

    if not function:
        return SecurityDecision(
            action=SecurityAction.CONFIRM,
            reason="Browser evaluate function is empty.",
        )

    normalized = function.casefold()

    # Block JavaScript that may modify the page, browser state, or external state
    dangerous_patterns = (
        "fetch(",
        "xmlhttprequest",
        "localstorage",
        "sessionstorage",
        "document.cookie",
        ".click(",
        ".submit(",
        ".remove(",
        ".setattribute(",
        ".removeattribute(",
        "document.write",
        "window.open",
        "location.href",
        "location.assign",
        "location.replace",
        "history.pushstate",
        "history.replacestate",
        "eval(",
    )

    if any(
        pattern in normalized
        for pattern in dangerous_patterns
    ):
        return SecurityDecision(
            action=SecurityAction.CONFIRM,
            reason="Browser evaluate may modify browser or page state.",
        )

    # Keep automatic evaluation limited to simple expression-style reads
    if any(
        token in function
        for token in (";", "{", "}")
    ):
        return SecurityDecision(
            action=SecurityAction.CONFIRM,
            reason="Complex browser evaluate code requires confirmation.",
        )

    # Allow common read-only page text access
    read_only_patterns = (
        "innertext",
        "textcontent",
    )

    if any(
        pattern in normalized
        for pattern in read_only_patterns
    ):
        return SecurityDecision(
            action=SecurityAction.ALLOW,
            reason="Read-only browser text evaluation.",
        )

    return SecurityDecision(
        action=SecurityAction.CONFIRM,
        reason="Browser evaluate is not recognized as a safe read-only operation.",
    )


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
                reason=(
                    "The browser wants to access a private "
                    "or local network address."
                ),
            )

    except ValueError:
        # The hostname is a domain name, not an IP address
        pass

    return None


def evaluate_tool_call(
    tool_name: str,
    arguments: Any,
) -> SecurityDecision:

    # Get the default permission for the tool
    permission = TOOL_PERMISSIONS.get(
        tool_name,
        ToolPermission.CONFIRM,
    )

    # Inspect browser evaluate calls separately
    if tool_name == "browser_evaluate":
        return check_browser_evaluate_safety(arguments)

    # Block dangerous tools
    if permission == ToolPermission.BLOCK:
        return SecurityDecision(
            action=SecurityAction.BLOCK,
            reason=f"{tool_name} is blocked for security reasons.",
        )

    # Ask before using tools that always need confirmation
    if permission == ToolPermission.CONFIRM:
        return SecurityDecision(
            action=SecurityAction.CONFIRM,
            reason=f"{tool_name} requires user confirmation.",
        )

    # Allow safe tools directly
    if permission == ToolPermission.ALLOW:
        return SecurityDecision(
            action=SecurityAction.ALLOW,
            reason="Tool is allowed by the security policy.",
        )

    # Check URL safety for conditional tools
    if isinstance(arguments, dict):
        url = arguments.get("url")

        if isinstance(url, str):
            url_decision = check_url_safety(url)

            if url_decision is not None:
                return url_decision

    # Ask before accepting browser dialogs
    if (
        tool_name == "browser_handle_dialog"
        and isinstance(arguments, dict)
    ):
        accept = arguments.get("accept", False)

        if accept:
            return SecurityDecision(
                action=SecurityAction.CONFIRM,
                reason="The browser wants to accept a dialog.",
            )

        return SecurityDecision(
            action=SecurityAction.ALLOW,
            reason="The browser is rejecting a dialog.",
        )

    # Check browser tab actions
    if (
        tool_name == "browser_tabs"
        and isinstance(arguments, dict)
    ):
        tab_action = str(
            arguments.get("action", "")
        ).lower()

        if tab_action in {
            "list",
            "select",
            "close",
            "new",
        }:
            return SecurityDecision(
                action=SecurityAction.ALLOW,
                reason="Safe browser tab action.",
            )

    # Check browser actions that may create an external effect
    if tool_name in {
        "browser_click",
        "browser_press_key",
        "browser_select_option",
        "browser_type",
        "browser_fill_form",
        "browser_drag",
    }:
        sensitive_keyword = contains_sensitive_action(
            arguments
        )

        if sensitive_keyword is not None:
            return SecurityDecision(
                action=SecurityAction.CONFIRM,
                reason=(
                    "This browser action may create a sensitive "
                    "or irreversible external effect: "
                    f"{sensitive_keyword}"
                ),
            )

    # Allow the action if no risk was found
    return SecurityDecision(
        action=SecurityAction.ALLOW,
        reason="No security risk was detected.",
    )