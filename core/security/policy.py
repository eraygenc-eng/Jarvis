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

    # Tools that always need user confirmation
    "open_application": ToolPermission.CONFIRM,
    "close_application": ToolPermission.CONFIRM,
    "launch_game": ToolPermission.CONFIRM,
    "browser_file_upload": ToolPermission.CONFIRM,
    "browser_drop": ToolPermission.CONFIRM,
    "browser_evaluate": ToolPermission.CONFIRM,

    # Tools that are always blocked
    "browser_run_code_unsafe": ToolPermission.BLOCK,
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

    # Check sensitive browser actions
    if tool_name in {
        "browser_click",
        "browser_press_key",
        "browser_select_option",
        "browser_type",
        "browser_fill_form",
        "browser_drag",
    }:
        arguments_text = str(arguments).lower()

        for keyword in SENSITIVE_KEYWORDS:
            if keyword in arguments_text:
                return SecurityDecision(
                    action=SecurityAction.CONFIRM,
                    reason=f"Sensitive action detected: {keyword}",
                )

    # Allow the action if no risk was found
    return SecurityDecision(
        action=SecurityAction.ALLOW,
        reason="No security risk was detected.",
    )