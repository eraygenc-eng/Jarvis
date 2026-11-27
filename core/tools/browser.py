import re
import asyncio

from typing import Literal

from contextlib import AsyncExitStack # For Playwright Connection
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools


from langchain_core.tools import tool
from mcp.types import TextContent, CallToolResult

from core.research.evidence import (
    ObservationStore,
    get_focused_snapshot,
    get_interactive_snapshot
)

from urllib.parse import urlparse


def read_ucuzabilet_calendar(page_text: str) -> tuple[list[str], str | None]:
    month_names = (
        "Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|"
        "Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık"
    )

    months = re.findall(
        rf"(?m)^\s*- generic \[ref=[\w-]+\]: ((?:{month_names}) \d{{4}})\s*$",
        page_text,
    )

    next_refs = re.findall(
        r'(?m)^\s*- generic "ileri(?:&#x3e;?|>)" \[ref=([\w-]+)\]',
        page_text,
    )

    next_ref = next_refs[0] if len(next_refs) == 1 else None
    return months, next_ref



class BrowserManager:
    def __init__(self, *, headless: bool = False):
        self.client = MultiServerMCPClient(
            {
                "playwright": {
                    "command": "cmd",
                    "args": [
                        "/c",
                        "npx",
                        "-y",
                        "@playwright/mcp@0.0.80",
                        "--isolated",
                        *(["--headless"] if headless else []),
                    ],
                    "transport": "stdio",
                }
            }
        )

        # Keep async connections open
        self.exit_stack = AsyncExitStack()

        # Store the active MCP session
        self.session = None

        # Store Playwright browser tools
        self.tools = None

        # Keep browser observations in this browser session.
        self.observations = ObservationStore()
        self._action_lock = asyncio.Lock()

        # Track whether the current page may have changed
        self._page_changed = True

        # Pause browser automation during human verification
        self._waiting_for_human_verification = False

        # Remember the latest semantic snapshot focus so page-changing
        # browser actions can reuse the same target for automatic observations.
        self._last_snapshot_focus: str | None = None

        # Remember which snapshot mode was used last.
        self._last_snapshot_mode = "focused"

        # Get the active research controller when needed
        self._research_controller_getter = None


    def reset_request_focus(self) -> None:
        # Do not carry a semantic snapshot focus into a new user request.
        self._last_snapshot_focus = None
        self._last_snapshot_mode = "focused"



    def set_research_controller_getter(self, getter):
        # Store a func that returns the active controller
        self._research_controller_getter = getter



    def _get_research_controller(self):
        # Research guard is disabled when no getter exits
        if self._research_controller_getter is None:
            return None

        return self._research_controller_getter()


    def _get_source_from_url(self, url: str) -> str | None:
        if not url:
            return None

        try:
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname

            if not hostname:
                return None

            # Normalize hostname
            hostname = hostname.lower().strip()

            # Treat www.example.com and example.com as the same source
            if hostname.startswith("www."):
                hostname = hostname[4:]

            return hostname

        except ValueError:
            return None


    def _can_visit_source(self, url: str) -> bool:
        source = self._get_source_from_url(url)

        if source is None:
            return True

        controller = self._get_research_controller()

        # No active research means normal browsing
        if controller is None:
            return True

        # Block domains outside the current research plan
        if not controller.is_domain_allowed(source):
            return False

        # Allow navigation inside an already visited source
        if controller.has_visited_source(source):
            return True

        # Register a completely new source
        return controller.register_source(source)


    def _browser_action_may_change_page(self, tool_name: str) -> bool:
        # These tools only read browser state
        read_only_tools = {
            "browser_find",
            "browser_snapshot",
            "browser_take_screenshot",
        }

        # Unknown tools are treated as page-changing for safety
        return tool_name not in read_only_tools


    def _should_auto_observe_after_action(self, tool_name: str) -> bool:
        # Requires a fresh observation before the next decision
        return tool_name in {
            "browser_click",
            "browser_navigate",
            "browser_type",
            "browser_fill_form"
        }


    def _detect_page_interruption(self, page_text: str) -> tuple[str | None, str | None]:
        """
        Detect common page interruptions.

        This only detects interruptions.
        It does not click or bypass anything.
        """

        if not page_text:
            return None, None

        text = page_text.lower()

        # Human verification must never be bypassed automatically.
        captcha_patterns = [
            r"verify you are human",
            r"confirm you are human",
            r"prove you are human",
            r"i am human",
            r"i'm not a robot",
            r"not a robot",
            r"insan olduğunuzu doğrulayın",
            r"insan oldugunuzu dogrulayin",
            r"robot olmadığınızı",
            r"robot olmadiginizi",
            r"\bcaptcha\b",
            r"\brecaptcha\b",
            r"\bhcaptcha\b",
            r"\bturnstile\b",
            r"yoksa robot mu",
        ]

        # Check all CAPTCHA patterns first.
        for pattern in captcha_patterns:
            if re.search(pattern, text, re.IGNORECASE):

                # Stop automatic actions during human verification.
                self._waiting_for_human_verification = True

                return (
                    "captcha",
                    "Human verification was detected. "
                    "Do not try to bypass it automatically. "
                    "Ask the user to complete the verification manually, "
                    "then continue from the same page."
                )

        # Check if human verification was active.
        if getattr(self, "_waiting_for_human_verification", False):
            self._waiting_for_human_verification = False

            print(
                "[BrowserInterruption] "
                "human_verification_cleared=True"
            )

        # Detect cookie consent banners.
        cookie_context_patterns = [
            r"\bcookie\b",
            r"\bconsent\b",
            r"\bçerez\b",
            r"\bcerez\b",
            r"çerez tercihleri",
            r"cerez tercihleri",
            r"çerez ayarları",
            r"cerez ayarlari",
            r"zorunlu çerez",
            r"zorunlu cerez",
        ]

        cookie_action_patterns = [
            r"accept all",
            r"accept cookies",
            r"allow all",
            r"reject all",
            r"only necessary",
            r"necessary only",
            r"kabul et",
            r"tümünü kabul et",
            r"tumunu kabul et",
            r"reddet",
            r"tümünü reddet",
            r"tumunu reddet",
            r"çerezler ayarları",
            r"cerezler ayarlari",
        ]

        has_cookie_context = any(
            re.search(
                pattern,
                text,
                re.IGNORECASE,
            )
            for pattern in cookie_context_patterns
        )

        has_cookie_action = any(
            re.search(
                pattern,
                text,
                re.IGNORECASE,
            )
            for pattern in cookie_action_patterns
        )

        if has_cookie_context and has_cookie_action:
            return (
                "cookie",
                "A cookie consent banner appears to be blocking the page. "
                "Handle the consent controls before continuing."
            )

        # Detect common blocking dialogs and newsletter popups.
        popup_context_patterns = [
            r"\bdialog\b",
            r"\bmodal\b",
            r"newsletter",
            r"subscribe",
            r"sign up",
            r"kampanyalardan haberdar",
            r"bildirimlere izin",
        ]

        close_control_patterns = [
            r'button[^\n]{0,80}"close',
            r'button[^\n]{0,80}"kapat',
            r'button[^\n]{0,80}"dismiss',
            r'button[^\n]{0,80}"not now',
            r'button[^\n]{0,80}"şimdi değil',
            r'button[^\n]{0,80}"simdi degil',
        ]

        has_popup_context = any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in popup_context_patterns
        )

        has_close_control = any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in close_control_patterns
        )

        if has_popup_context and has_close_control:
            return (
                "popup",
                "A blocking popup or dialog appears to be open. "
                "Close or dismiss it before continuing with the main task."
            )

        return None, None


    def _debug_interruption_candidates(self, page_text: str) -> None:
        """
        Print only lines that may belong to a cookie banner or popup.
        """

        if not page_text:
            return

        keywords = (
            "cookie",
            "çerez",
            "cerez",
            "kabul",
            "reddet",
            "accept",
            "reject",
            "consent",
            "privacy",
            "gizlilik",
        )

        matching_lines = []

        for line in page_text.splitlines():
            normalized_line = line.casefold()

            if any(
                keyword in normalized_line
                for keyword in keywords
            ):
                matching_lines.append(line.strip())

        print(
            "[InterruptionDebug] "
            f"candidate_lines={len(matching_lines)}"
        )

        # Keep terminal output small
        for line in matching_lines[:30]:
            print(
                "[InterruptionDebug] "
                f"{line}"
            )


    def _find_safe_interruption_action(self, page_text: str) -> tuple[str, str, str] | None:
        """
        Find a safe button for cookie banners or normal popups.

        Returns:
            (interruption_kind, element_label, ref)
        """

        if not page_text:
            return None

        # Detect the current interruption.
        interruption_kind, _ = self._detect_page_interruption(
            page_text
        )

        # Never automate CAPTCHA or human verification.
        if interruption_kind not in {"cookie", "popup"}:
            return None

        controls: list[tuple[str, str]] = []

        # Normal clickable controls:
        # - button "Accept all" [ref=e10]
        # - link "Reject all" [ref=e11]
        named_control_pattern = re.compile(
            r'^\s*-\s+(?:button|link)\s+"([^"]+)"'
            r'[^\n]*\[ref=([^\]]+)\]',
            re.IGNORECASE,
        )

        # Some websites expose clickable items as generic nodes:
        # - generic [ref=e12] [cursor=pointer]: Accept all
        generic_control_pattern = re.compile(
            r'^\s*-\s+generic\s+'
            r'\[ref=([^\]]+)\]'
            r'[^\n]*\[cursor=pointer\]'
            r'\s*:\s*(.+?)\s*$',
            re.IGNORECASE,
        )

        for line in page_text.splitlines():

            named_match = named_control_pattern.search(line)

            if named_match is not None:
                label = named_match.group(1).strip()
                ref = named_match.group(2).strip()

                controls.append(
                    (label, ref)
                )

                continue

            generic_match = generic_control_pattern.search(line)

            if generic_match is not None:
                ref = generic_match.group(1).strip()
                label = generic_match.group(2).strip()

                controls.append(
                    (label, ref)
                )

        if not controls:
            return None

        if interruption_kind == "cookie":

            # Prefer privacy-friendly actions.
            preferred_cookie_patterns = [
                r"^reject all$",
                r"^decline all$",
                r"^reject$",
                r"^decline$",
                r"^only necessary$",
                r"^necessary only$",
                r"^essential only$",
                r"^continue without accepting$",
                r"^tümünü reddet$",
                r"^tumunu reddet$",
                r"^reddet$",
                r"^yalnızca gerekli$",
                r"^yalnizca gerekli$",
                r"^sadece gerekli$",
                r"^gerekli çerezler$",
                r"^gerekli cerezler$",
            ]

            # Check ALL controls for a safer option first.
            for label, ref in controls:
                normalized_label = label.casefold()

                if any(
                    re.fullmatch(
                        pattern,
                        normalized_label,
                        re.IGNORECASE,
                    )
                    for pattern in preferred_cookie_patterns
                ):
                    return (
                        "cookie",
                        label,
                        ref,
                    )

            # Only accept cookies if no safer option exists.
            fallback_cookie_patterns = [
                r"^accept all$",
                r"^allow all$",
                r"^accept cookies$",
                r"^accept all cookies$",
                r"^tümünü kabul et$",
                r"^tumunu kabul et$",
                r"^çerezleri kabul et$",
                r"^cerezleri kabul et$",
                r"^kabul et$",
            ]

            for label, ref in controls:
                normalized_label = label.casefold()

                if any(
                    re.fullmatch(
                        pattern,
                        normalized_label,
                        re.IGNORECASE,
                    )
                    for pattern in fallback_cookie_patterns
                ):
                    return (
                        "cookie",
                        label,
                        ref,
                    )

        if interruption_kind == "popup":

            close_patterns = [
                r"^close$",
                r"^dismiss$",
                r"^not now$",
                r"^no thanks$",
                r"^maybe later$",
                r"^kapat$",
                r"^şimdi değil$",
                r"^simdi degil$",
                r"^hayır teşekkürler$",
                r"^hayir tesekkurler$",
            ]

            for label, ref in controls:
                normalized_label = label.casefold()

                if any(
                    re.fullmatch(
                        pattern,
                        normalized_label,
                        re.IGNORECASE,
                    )
                    for pattern in close_patterns
                ):
                    return (
                        "popup",
                        label,
                        ref,
                    )

        return None


    async def _handle_safe_interruption(self, page_text: str, page_url: str) -> bool:
        """
        Handle a safe cookie banner or normal popup.

        Returns True only when a safe control was clicked.
        """

        action = self._find_safe_interruption_action(page_text)

        if action is None:
            return False

        interruption_kind, label, ref = action

        # Ucuzabilet's passenger selector also has a "Close" button.
        if (
            self._get_source_from_url(page_url) == "ucuzabilet.com"
            and interruption_kind == "popup"
            and label.strip().casefold() in {"close", "kapat"}
        ):
            panel_text = page_text.casefold()
            if all(word in panel_text for word in ("yetişkin", "çocuk", "bebek", "uygula")):
                print("[UcuzabiletPassengers] Yolcu paneli açık, seçim bekleniyor.")
                return False

        print(
            "[BrowserInterruption] "
            f"auto_action={interruption_kind} | "
            f"label={label!r} | "
            f"ref={ref}"
        )

        # Click directly through the current MCP session
        response = await self.session.call_tool(
            "browser_click",
            arguments={
                "element": label,
                "target": ref,
            },
        )

        # Do not pretend the interruption was removed if click failed
        if response.isError:
            print(
                "[BrowserInterruption] "
                f"auto_action_failed={interruption_kind} | "
                f"ref={ref}"
            )

            return False

        # The page may have changed after the click
        self._page_changed = True
        self.observations.invalidate_current()

        print(
            "[BrowserInterruption] "
            f"auto_action_success={interruption_kind} | "
            f"ref={ref}"
        )

        return True
    

    async def _track_browser_action(self, request, handler):
        # One shared browser must not navigate and capture different pages at once.
        async with self._action_lock:
            tool_name = getattr(request, "name", "")
            arguments = getattr(request, "args", {})
            url = arguments.get("url", "")

            
            # Normalize incorrectly formatted Playwright snapshot references.
            if tool_name == "browser_click":
                target = arguments.get("target")

                if isinstance(target, str):
                    match = re.fullmatch(
                        r"ref=([A-Za-z0-9_-]+)",
                        target.strip()
                    )

                    if match:
                        arguments["target"] = match.group(1)

                        print(
                            f"[BrowserTarget] normalized: "
                            f"{target} -> {arguments['target']}"
                        )


            # Redirect the Pegasus homepage to the booking page.
            if (
                tool_name == "browser_navigate"
                and url.rstrip("/") in {
                    "https://www.flypgs.com",
                    "https://flypgs.com",
                    "https://www.flypgs.com/en",
                    "https://www.flypgs.com/tr",
                }
            ):
                url = "https://web.flypgs.com/booking?language=tr"
                arguments["url"] = url

            # Pause page-changing actions during human verification.
            # Read-only browser tools are still allowed
            if(
                self._waiting_for_human_verification
                and self._browser_action_may_change_page(tool_name)
            ):

                print(
                    "[BrowserInterruption] "
                    f"blocked_action={tool_name} | "
                    "reason=human_verification"
                )

                return CallToolResult(
                    content = [
                        TextContent(
                            type="text",
                            text=(
                                "BROWSER PAUSED: Human verification is active. "
                                "Do not click, type, fill forms, navigate, or retry "
                                "browser actions automatically. "
                                "Ask the user to complete the verification manually. "
                                "After the user finishes, request a fresh "
                                "browser_snapshot and continue from the same page."
                            ),
                        )
                    ],
                    isError=False,
                )

            # Get the controller only when research is active
            controller = self._get_research_controller()

            # Guard only real web navigation during active research
            if (
                controller is not None
                and tool_name == "browser_navigate"
                and url.startswith(("http://", "https://"))
            ):
                # Stop repeated navigation inside the same agent turn
                if controller.has_attempted_url(url):
                    return CallToolResult(
                        content=[
                            TextContent(
                                type="text",
                                text=(
                                    "NAVIGATION SKIPPED: "
                                    "This URL was already attempted "
                                    "during the current research turn."
                                ),
                            )
                        ],
                        isError=False,
                    )

                # Allow only valid research sources
                if not self._can_visit_source(url):
                    return CallToolResult(
                        content= [
                            TextContent(
                                type="text",
                                text=(
                                    "NAVIGATION SKIPPED: "
                                    "This source is not allowed for the current research."
                                ),
                            )
                        ],
                        isError=False
                    )
                

                # Remember this attempt before Playwright runs
                controller.register_navigation_attempt(url)

            log_ucuzabilet_type = False

            if tool_name == "browser_type":
                observation_id = self.observations.current_observation_id
                observation = self.observations.get(observation_id) if observation_id else None

                if observation is not None:
                    hostname = self._get_source_from_url(observation.page_url)
                    log_ucuzabilet_type = hostname == "ucuzabilet.com"

                    if log_ucuzabilet_type:
                        target = arguments.get("target", "")
                        for label in (
                            "Havalimanı Adı/Kodu, Şehir",
                            "Havalimanı adı/kodu, Şehir",
                        ):
                            pattern = (
                                rf'(?m)^\s*-\s+textbox "{re.escape(label)}"'
                                rf'[^\n]*\[ref={re.escape(target)}\](?=\s|:|$)'
                            )
                            if target and re.search(pattern, observation.page_text):
                                arguments["target"] = f'input[placeholder="{label}"]:visible'
                                print(f"[UcuzabiletInput] {target} -> {arguments['target']}")
                                break


            if tool_name == "browser_click":
                element = str(arguments.get("element", "")).casefold()
                observation_id = self.observations.current_observation_id
                observation = (
                    self.observations.get(observation_id)
                    if observation_id else None
                )

                if observation is not None:
                    page = urlparse(observation.page_url)
                    on_google_flights = (
                        page.hostname in {
                            "google.com", "www.google.com",
                            "google.com.tr", "www.google.com.tr",
                        }
                        and page.path.startswith("/travel/flights")
                    )
                    search_button = element in {
                        "google flights search button",
                        "google flights ara button",
                    }

                    if on_google_flights and search_button:
                        arguments["target"] = (
                            'role=button[name=/^(Ara|Uçuşları ara|Search|Search flights)$/i]'
                        )
                        print("[GoogleFlightsSearch] Arama düğmesi adıyla hedeflendi")


            # Invalidate the snapshot only when the action may change the page
            if self._browser_action_may_change_page(tool_name):
                self._page_changed = True
                self.observations.invalidate_current()

            # Run the real Playwright action
            response = await handler(request)

            click_label = str(arguments.get("element", "")).casefold()
            if tool_name == "browser_click" and (
                "google flights" in click_label
                or "date" in click_label
                or "tarih" in click_label
            ):
                click_reply = "\n".join(
                    block.text
                    for block in response.content
                    if block.type == "text"
                )
                print(
                    f"[GoogleFlightsClick] target={arguments.get('target')} "
                    f"is_error={response.isError}\n"
                    f"{click_reply[:1200]}"
                )

            if log_ucuzabilet_type:
                response_text = "\n".join(
                    block.text
                    for block in response.content
                    if block.type == "text"
                )

                print(
                    f"[UcuzabiletType] target={arguments.get('target')!r} "
                    f"text={arguments.get('text')!r} "
                    f"is_error={response.isError}"
                )
                print(f"[UcuzabiletType] response={response_text[:800]}")

            # Pause after opening Skyscanner for manual testing
            if (
                tool_name == "browser_navigate"
                and self._get_source_from_url(url) in {
                    "skyscanner.com",
                    "skyscanner.com.tr"
                }
            ):
                await asyncio.to_thread(
                    input,
                    "[BrowserDebug] Test Skyscanner manually, then press Enter..."
                )

            # Check network requests after typing and waiting
            if tool_name in {"browser_type", "browser_wait_for"}:
                network_result = await self.session.call_tool(
                    "browser_network_requests",
                    arguments={"static": False}
                )

                network_text = "\n".join(
                    block.text
                    for block in network_result.content
                    if block.type == "text"
                )

                print("[BrowserNetworkDebug] Network requests:")

                for line in network_text.splitlines()[-20:]:
                    # Hide URL query parameters in debug logs
                    safe_line = re.sub(r"\?[^\s]*", "?[hidden]", line)
                    print("[BrowserNetworkDebug]", safe_line[:250])

            # Debug
            if tool_name == "browser_find":
                find_text = "\n".join(
                    block.text
                    for block in response.content
                    if block.type == "text"
                )

                # Read the match count and searched text from Playwright output
                match_info = re.search(
                    r'Found\s+(\d+)\s+matches\s+for\s+"([^"]*)"',
                    find_text,
                    re.IGNORECASE,
                )

                match_count = None
                searched_text = None

                if match_info is not None:
                    match_count = int(match_info.group(1))
                    searched_text = match_info.group(2)

                print(
                    "[BrowserFind] "
                    f"response={len(find_text):,} chars | "
                    f"lines={len(find_text.splitlines()):,} | "
                    f"matches={match_count}"
                )

                # Do not send huge, overly broad find results to the model
                if len(find_text) > 12000:
                    compact_text = (
                        "BROWSER FIND RESULT TOO LARGE\n"
                        f"Matches: {match_count if match_count is not None else 'unknown'}\n"
                        f"Searched text: {searched_text or 'unknown'}\n\n"
                        "The full result was omitted from model context because "
                        "the search was too broad.\n"
                        "Run browser_find again with a more specific phrase such as "
                        "the exact product name, exact price, seller name, model, "
                        "or another distinctive text.\n"
                        "Do not conclude that the requested item is absent from "
                        "this broad find result."
                    )

                    response = response.model_copy(
                        update={
                            "content": [
                                TextContent(
                                    type="text",
                                    text=compact_text,
                                )
                            ]
                        }
                    )

            # Keep actual navigation failures, so a model cannot invent blockers
            if (
                getattr(response, "isError", False)
                and url.startswith(("http://", "https://"))
            ):
                text = "\n".join(
                    block.text
                    for block in response.content
                    if block.type == "text"
                )

                if text.strip():
                    observation = self.observations.capture(
                        url,
                        text,
                        kind="error",
                    )

                    response = response.model_copy(
                        update={
                            "content": [
                                *response.content,
                                TextContent(
                                    type="text",
                                    text=(
                                        "Browser error Observation ID: "
                                        f"{observation.observation_id}"
                                    ),
                                ),
                            ]
                        }
                    )

            # After a successful page-changing click, capture the new page state
            # immediately when an explicit semantic focus is already known.
            if (
                not getattr(response, "isError", False)
                and self._should_auto_observe_after_action(tool_name)
                and self._last_snapshot_focus
            ):
                auto_observation = await self._capture_snapshot(
                    focus=self._last_snapshot_focus,
                    mode=self._last_snapshot_mode
                )

                response = response.model_copy(
                    update={
                        "content": [
                            *response.content,
                            TextContent(
                                type="text",
                                text=(
                                    "AUTO CURRENT PAGE OBSERVATION\n"
                                    "A fresh browser observation was captured automatically "
                                    "after this action.\n"
                                    "Use this observation directly for the next decision. "
                                    "Do not request another browser_snapshot unless this "
                                    "observation lacks the information you need or the page "
                                    "changes again.\n\n"
                                    f"{auto_observation}"
                                ),
                            ),
                        ]
                    }
                )

            return response


    async def capture_snapshot(self, focus: str | None = None, mode: str = "focused") -> str:

        normalized_mode = mode.strip().lower()

        # Allow only known snapshot modes
        if normalized_mode not in {"focused", "interactive", "full"}:
            return(
                "OBSERVATION FAILED: Invalid snapshot mode. "
                "Use 'focused', 'interactive', or 'full'."
            )

        # Normalize and remember the latest meaningful focus
        normalized_focus = focus.strip() if focus else None

        if normalized_focus:
            self._last_snapshot_focus = normalized_focus

        # Remember the mode for auto observs
        self._last_snapshot_mode = normalized_mode

        async with self._action_lock:
            # Reuse the current snapshot only when human verification is not active.
            # During manual verification, the browser may change outside Jarvis.
            # Reuse a snapshot only when the page has not changed.
            if (
                not self._page_changed
                and not getattr(self, "_waiting_for_human_verification", False)
            ):
                observation_id = self.observations.current_observation_id

                if observation_id is not None:
                    observation = self.observations.get(observation_id)

                    if (
                        observation is not None
                        and observation.kind == "page"
                    ):
                        print(
                            "[BrowserSnapshot] cache_hit=True | "
                            f"focus={normalized_focus!r} | "
                            f"mode={normalized_mode}"
                        )

                        return self._format_observation(
                            observation,
                            focus=normalized_focus,
                            mode=normalized_mode
                        )

            # No reusable snapshot exists, so read the browser again
            return await self._capture_snapshot(
                focus=normalized_focus,
                mode=normalized_mode
            )


    def _format_observation(self, observation, focus: str | None = None, mode: str = "focused") -> str:
        # Start with the complete stored snapshot
        page_url = observation.page_url
        page_text = observation.page_text


        # Check the page URL and content for human verification
        interruption_kind, interruption_message = (
            self._detect_page_interruption(
                f"{page_url}\n{page_text}"
            )
        )

        # This text will be added to the model-facing observation
        interruption_notice = ""

        if interruption_kind is not None:
            print(
                "[BrowserInterruption] "
                f"kind={interruption_kind}"
            )

            interruption_notice = (
                "\n\n"
                "### Browser Interruption\n"
                f"Type: {interruption_kind}\n"
                f"{interruption_message}\n"
            )




        if mode == "interactive":
            # Keep only controls and nearby context needed for browser actions
            interactive_snapshot = get_interactive_snapshot(page_text)

            if self._get_source_from_url(page_url) == "ucuzabilet.com":
                field_lines = [
                    line.strip()
                    for line in page_text.splitlines()
                    if re.match(r"^\s*-\s+(textbox|combobox)\b", line)
                    and "[ref=" in line
                ]

                print(f"[UcuzabiletFields] count={len(field_lines)}")
                for line in field_lines:
                    print(f"[UcuzabiletFields] {line}")

                if field_lines:
                    interactive_snapshot = (
                        "Current input fields on Ucuzabilet. "
                        "Use the exact ref shown for the intended field. "
                        "If the field is unclear, inspect it before typing.\n"
                        + "\n".join(field_lines)
                        + "\n\n"
                        + interactive_snapshot
                    )

            # Debug calendar controls on Ucuzabilet.
            if "ucuzabilet.com" in page_url:
                for label, content in (
                    ("raw", page_text),
                    ("filtered", interactive_snapshot),
                ):
                    lines = content.splitlines()

                    calendar_indices = [
                        i
                        for i, line in enumerate(lines)
                        if "kasım 2026" in line.casefold()
                        and "uçak bileti" not in line.casefold()
                        and not re.match(r"^\s*-\s*link\b", line)
                        and len(line.strip()) < 100
                    ]

                    if not calendar_indices:
                        print(f"[CalendarDebug] {label}: header NOT FOUND")
                        continue

                    calendar_index = calendar_indices[-1]

                    print(f"[CalendarDebug] {label}: calendar found")

                    for line in lines[
                        max(0, calendar_index - 3):calendar_index + 85
                    ]:
                        print(f"[CalendarDebug] {label}: {line.strip()[:180]}")

            # Debug airport suggestions on Ucuzabilet.
            if "ucuzabilet.com" in page_url:
                pattern = re.compile(
                    r"\b(?:SAW|STN|option|listbox)\b|sabiha|stansted",
                    re.IGNORECASE,
                )

                for label, content in (
                    ("raw", page_text),
                    ("filtered", interactive_snapshot),
                ):
                    matches = [
                        line.strip()
                        for line in content.splitlines()
                        if pattern.search(line)
                    ]

                    print(f"[AirportDebug] {label}: {len(matches)} matches")

                    for line in matches[-12:]:
                        print(f"[AirportDebug] {label}: {line[:200]}")

            host = self._get_source_from_url(observation.page_url) or ""
            if host == "flypgs.com" or host.endswith(".flypgs.com"):
                for label, content in (
                    ("raw", page_text),
                    ("filtered", interactive_snapshot),
                ):
                    lines = content.splitlines()
                    for index, line in enumerate(lines):
                        if "nereye" in line.casefold():
                            print(f"[PegasusDebug] {label} | Nereye alanı")
                            for nearby in lines[max(0, index - 3):index + 6]:
                                print(f"[PegasusDebug] {nearby}")
                            break
                    else:
                        print(f"[PegasusDebug] {label} | Nereye bulunamadı")

            print(
                "[BrowserSnapshot] interactive_result="
                f"{len(interactive_snapshot):,} chars"
            )

            snapshot_mode = "interactive"

            if interactive_snapshot.strip():
                model_page_text = interactive_snapshot

            else:
                model_page_text = (
                    "INTERACTIVE BROWSER SNAPSHOT\n\n"
                    "No interactive controls were found on the current page.\n"
                    "The complete snapshot remains stored internally as evidence."
                )
        
        elif mode == "focused":
            # Full snapshots stay stored internally as evidence.
            # When a semantic focus exists, never fall back to sending
            # the complete page snapshot to the model.
            if focus:
                focused_snapshot = get_focused_snapshot(
                    page_text,
                    focus,
                    page_url=page_url,
                )

                print(
                    "[BrowserSnapshot] focused_result="
                    f"{len(focused_snapshot):,} chars"
                )

                if focused_snapshot.strip():
                    model_page_text = focused_snapshot

                else:
                    model_page_text = (
                        "FOCUSED BROWSER SNAPSHOT\n"
                        f"Focus: {focus}\n\n"
                        "No sufficiently relevant page region was found "
                        "for this focus.\n"
                        "The complete snapshot remains stored internally "
                        "as evidence and was not sent to the model.\n"
                        "Use browser_find with a more specific product name, "
                        "model, price, seller, or distinctive phrase if needed."
                    )

            else:
                model_page_text = (
                "FOCUSED BROWSER SNAPSHOT\n\n"
                "No focus was provided.\n"
                "Use a short, specific focus or choose another snapshot mode."
                )   

            snapshot_mode = "focused"

        elif mode == "full":
            # Full mode sends the complete stored page snapshot
            model_page_text = page_text
            snapshot_mode = "full"

        else:
            raise ValueError(
                f"Unsupported snapshot mode: {mode}"
            )

        print(
            "[BrowserSnapshot] "
            f"full={len(page_text):,} chars | "
            f"model={len(model_page_text):,} chars | "
            f"mode={snapshot_mode}"
        )

        return (
            f"Observation ID: {observation.observation_id}\n"
            f"Captured at: {observation.captured_at.isoformat()}\n"
            f"- Page URL: {page_url}\n"
            f"Snapshot mode: {snapshot_mode}\n"
            "This records page content, not a verified offer.\n"
            "The complete snapshot remains stored as evidence."
            f"{interruption_notice}\n\n"
            "### Snapshot\n"
            "```yaml\n"
            f"{model_page_text}\n"
            "```"
        )
    

    async def _capture_snapshot(self, focus: str | None = None, mode: str = "focused", auto_interruption_depth: int = 0) -> str:
        if self.session is None:
            return "OBSERVATION FAILED: Browser session is not started."


        print(
            "[BrowserSnapshot] "
            f"focus={focus!r} | "
            f"mode={mode}"
        )

        # Read directly from the existing MCP session.
        response = await self.session.call_tool(
            "browser_snapshot",
            arguments={},
        )

        text = "\n".join(
            block.text
            for block in response.content
            if block.type == "text"
        ).replace("\r\n", "\n")

        if response.isError:
            return f"OBSERVATION FAILED: Browser returned an error.\n{text}"

        # Read the URL from MCP page metadata, not from page links.
        page_match = re.search(
            r"(?m)^### Page(?: state)?\n- Page URL: (https?://[^\s]+)",
            text,
        )

        # Support the known MCP snapshot section formats.
        snapshot_match = re.search(
            r"(?ms)^(?:### Snapshot|- Page Snapshot:)[ \t]*\n"
            r"```(?:yaml)?\n(.*?)\n```",
            text,
        )

        if page_match is None or snapshot_match is None:
            return (
                "OBSERVATION NOT STORED: "
                "The browser output format could not be parsed. "
                "Do not use this response as a stored observation.\n\n"
                + text
            )

        page_url = page_match.group(1)
        page_text = snapshot_match.group(1)

        # Debug snapshot sizes before model-facing compaction
        print(
            "[BrowserSnapshot] "
            f"raw={len(text):,} chars | "
            f"snapshot={len(page_text):,} chars"
        )

        if not page_text.strip():
            return (
                "OBSERVATION NOT STORED: The page snapshot is empty.\n\n"
                + text
            )

        # Debug possible cookie and popup controls
        self._debug_interruption_candidates(page_text)

        # Handle safe page interruptions before stoping the observ
        if auto_interruption_depth < 3:
            interruption_handled = await self._handle_safe_interruption(page_text, page_url)  

            
            if interruption_handled:
                # Get a fresh snapshot after handling the interruption.
                refreshed_snapshot = await self._capture_snapshot(
                    focus=focus,
                    mode=mode,
                    auto_interruption_depth=auto_interruption_depth + 1
                )

                # Tell the agent that the interruption was already handled.
                # Avoid repeating consent actions without new evidence.
                return (
                    "BROWSER NOTICE: A cookie or popup control was clicked "
                    "automatically. Continue with the main task. "
                    "Do not retry consent unless a new blocking dialog "
                    "is visible in the current snapshot.\n\n"
                    + refreshed_snapshot
                )


        
        # Store the new browser observation.
        observation = self.observations.capture(
            page_url=page_url,
            page_text=page_text,
        )

        # The browser snapshot was captured successfully.
        self._page_changed = False

        # Format the result and detect possible interruptions.
        result = self._format_observation(
            observation,
            focus=focus,
            mode=mode,
        )

        # A CAPTCHA snapshot must not block future snapshots.
        if self._waiting_for_human_verification:
            # Keep the evidence, but mark the current view as stale.
            self.observations.invalidate_current()

            # Allow a fresh snapshot after manual verification.
            self._page_changed = True

            print(
                "[BrowserInterruption] "
                "human_verification_pending=True | "
                "snapshot_refresh_required=True"
            )

        return result


    async def start(self):
        # Open a persistent Playwright MCP session
        self.session = await self.exit_stack.enter_async_context(
            self.client.session("playwright")
        )

        # Load Playwright tools for LangChain
        self.tools = await load_mcp_tools(
            self.session,
            tool_interceptors=[self._track_browser_action],
        )

        @tool
        async def browser_snapshot(focus: str | None = None, mode: Literal["focused", "interactive", "full"] = "focused") -> str:
            """
            Read the current page and store a browser observation.

            Choose the snapshot mode based on what you need to do next.

            Use "interactive" when you need to interact with the page:
            - fill a form
            - type into a textbox
            - choose an autocomplete option
            - select an airport, hotel, date, passenger, or rental option
            - click buttons, checkboxes, radio buttons, or dropdowns

            Use "focused" when you need to read a specific result:
            - product prices
            - flight results and prices
            - hotel results
            - search results
            - offers or sellers

            Use "full" only when focused and interactive modes are not enough.

            For focused mode, focus should be a short and specific target.

            Good focused examples:
            - "iPhone 18 Pro prices"
            - "RTX 5070 offers"
            - "Istanbul to Izmir flight results"
            - "hotel room prices"

            For interactive mode, focus may describe the current form.

            Good interactive examples:
            - "Pegasus flight search form"
            - "airport autocomplete options"
            - "hotel booking form"
            - "car rental search form"

            Do not pass the whole user request as focus.

            The complete snapshot is preserved internally as evidence.
            """
            return await self.capture_snapshot(
                focus=focus,
                mode=mode
            )


        @tool
        async def ucuzabilet_go_to_month(year: int, month: int) -> str:
            """On Ucuzabilet, advance the open flight calendar to a target year
            and month in one call. Use this instead of clicking next month
            repeatedly. After it returns, select the requested day using the
            returned snapshot. This tool moves forward only.
            """
            month_names = (
                "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
            )

            if not 1 <= month <= 12 or not 1 <= year <= 9999:
                return "Geçersiz yıl veya ay."

            target = (year, month)
            target_label = f"{month_names[month - 1]} {year}"

            async with self._action_lock:
                if self._waiting_for_human_verification:
                    return "Tarayıcı kullanıcı doğrulaması bekliyor."

                previous_months = []
                clicks = 0

                while True:
                    snapshot = await self._capture_snapshot(
                        focus=f"Ucuzabilet takvimi: {target_label}",
                        mode="interactive",
                    )

                    observation_id = self.observations.current_observation_id
                    observation = self.observations.get(observation_id)
                    if self._waiting_for_human_verification or observation is None:
                        return "Güncel takvim görüntüsü alınamadı."

                    if self._get_source_from_url(observation.page_url) != "ucuzabilet.com":
                        return "Bu araç yalnızca Ucuzabilet takviminde kullanılabilir."

                    months, next_ref = read_ucuzabilet_calendar(observation.page_text)
                    print(f"[UcuzabiletCalendar] target={target_label} "
                          f"visible={months} clicks={clicks}")

                    if target_label in months:
                        return f"{target_label} görünür. İstenen günü seç.\n\n{snapshot}"

                    if not months or next_ref is None:
                        return "Açık takvim veya tek bir ileri oku bulunamadı."

                    if months == previous_months:
                        return f"Tıklama sonrası takvim ilerlemedi. Görünen aylar: {months}"

                    first_month, first_year = months[0].split()
                    first_visible = (int(first_year), month_names.index(first_month) + 1)
                    if target < first_visible:
                        return f"Hedef ay görünen takvimden önce. Görünen aylar: {months}"

                    if clicks >= 24:
                        return f"24 ay geçişinden sonra hedefe ulaşılamadı: {months}"

                    previous_months = months
                    self._page_changed = True
                    self.observations.invalidate_current()

                    result = await self.session.call_tool(
                        "browser_click",
                        arguments={"element": "Takvimde sonraki ay", "target": next_ref},
                    )
                    if result.isError:
                        detail = "\n".join(
                            block.text for block in result.content if block.type == "text"
                        )
                        return f"Takvim oku tıklanamadı: {detail[:400]}"

                    clicks += 1


        @tool
        async def ucuzabilet_set_adults(count: int) -> str:
            """Set the adult count in the OPEN Ucuzabilet passenger panel.
            Open Yolcular once, then call this tool with the requested adult
            count. On success click Uygula and check the passenger summary.
            """

            def report(message: str) -> str:
                print(f"[UcuzabiletAdults] {message}")
                return message

            print(f"[UcuzabiletAdults] started target={count}")

            if count < 1:
                return "Yetişkin sayısı en az 1 olmalı."

            async with self._action_lock:
                if self._waiting_for_human_verification:
                    return "Tarayıcı kullanıcı doğrulaması bekliyor."

                # Read the live value only from the visible adult counter.
                read_count_js = """() => {
                    const host = location.hostname.toLowerCase();
                    if (host !== 'ucuzabilet.com' &&
                        host !== 'www.ucuzabilet.com') return -1;

                    const inputs = [...document.querySelectorAll(
                        '.passenger-count-buttons input[name="ADULT"]'
                    )].filter(input => input.getClientRects().length > 0);

                    if (inputs.length !== 1) return -1;
                    const value = inputs[0].value.trim();
                    return /^\\d+$/.test(value) ? Number(value) : -1;
                }"""

                previous_count = None
                while True:
                    result = await self.session.call_tool(
                        "browser_evaluate",
                        arguments={"function": read_count_js},
                    )
                    text = "\n".join(
                        block.text for block in result.content if block.type == "text"
                    )
                    match = re.search(r"(?m)^### Result\s*\n(-?\d+)\s*$", text)
                    if result.isError or match is None:
                        return report(
                            f"Sayaç yanıtı okunamadı. is_error={result.isError}, "
                            f"response={text[:500]!r}"
                        )

                    current = int(match.group(1))
                    if current < 0:
                        return report("Açık ve görünür tek bir ADULT sayacı bulunamadı.")

                    print(f"[UcuzabiletAdults] current={current} target={count}")

                    if current == count:
                        return (
                            f"Yetişkin sayısı {current} olarak doğrulandı. "
                            "Uygula düğmesine tıkla ve formdaki yolcu özetini kontrol et."
                        )

                    if previous_count is not None:
                        expected = previous_count + (1 if count > previous_count else -1)
                        if current != expected:
                            return (
                                f"Sayaç beklenen şekilde değişmedi: "
                                f"önce={previous_count}, şimdi={current}, hedef={count}."
                            )

                    button_class = (
                        ".input-group-append" if current < count
                        else ".input-group-prepend"
                    )
                    target = (
                        '.passenger-count-buttons:has(input[name="ADULT"])'
                        f':visible > {button_class}:visible'
                    )

                    previous_count = current
                    self._page_changed = True
                    self.observations.invalidate_current()

                    click = await self.session.call_tool(
                        "browser_click",
                        arguments={"element": "Yetişkin sayacı", "target": target},
                    )
                    if click.isError:
                        detail = "\n".join(
                            block.text for block in click.content if block.type == "text"
                        )
                        return f"Yetişkin sayacı tıklanamadı: {detail[:350]}"
        

        # Replace only the agent-facing snapshot tool.
        self.tools = [
            existing_tool
            for existing_tool in self.tools
            if existing_tool.name != "browser_snapshot"
        ]

        self.tools.append(browser_snapshot)
        self.tools.append(ucuzabilet_go_to_month)
        self.tools.append(ucuzabilet_set_adults)

    async def stop(self):
        self.observations.invalidate_current()
        # Close all async connections
        await self.exit_stack.aclose()

        # Clear stored session and tools
        self.session = None
        self.tools = None


    def get_tools(self):
        # Return loaded browser tools
        if self.tools is None:
            raise RuntimeError("BrowserManager is not started.")

        return self.tools
