import json
from copy import deepcopy
import hashlib
import re

from typing import Callable

from langchain_core.tools import tool

from core.research.comparison_state import (
    ComparisonResult,
    ComparisonState,
    SourceStatus,
    VerificationStatus,
    MAX_VERIFICATION_ATTEMPTS,
    MAX_FINAL_PAGE_ATTEMPTS,
)
from core.research.ranking import (
    find_best_conditional,
    find_best_overall,
    find_best_public,
    get_conditional_total,
    get_public_total,
    refresh_source_rankings,
    find_best_public_for_source,
    find_best_conditional_for_source,
    get_unverified_source_winners,
    get_pending_verifications,
    normalize_currency,
    no_winner_reason,
)

from core.research.evidence import (
    ObservationStore,
    get_snapshot_subtree,
)

from core.research.offer_verification import OfferQuote, validate_quote, apply_quote, quote_prices
from core.research.product_quote import ProductQuoteSelection, build_product_quote
from core.research.discovery_evidence import ACCESS_FAILURE, access_failure_excerpt, has_discovery_identity
from core.research.quote_evidence import visible_text

from core.research.research_utils import (
    get_canonical_source,
    get_product_identity_conflict,
    is_price_focused_query,
    url_belongs_to_source,
    normalize_price_condition,
    normalize_identity,
)

from core.research.verification import (
    is_domain_url,
    validate_money_values,
    urls_match,
)


def create_research_tools(
    get_state: Callable[
        [],
        ComparisonState | None,
    ],
    observation_store: ObservationStore,
) -> list:

    def source_evidence(source: str, observation_id: str):
        observation = observation_store.require_evidence(observation_id)
        if not url_belongs_to_source(source, observation.page_url):
            raise ValueError("Evidence must come from the direct source's own website.")
        return observation

    def failure_evidence(observation_id: str, excerpt: str):
        observation = observation_store.require_evidence(observation_id)
        if not excerpt.strip() or excerpt.casefold() not in observation.page_text.casefold():
            raise ValueError("Copy the actual observed failure from the stored browser evidence.")
        if observation.kind != "error" and not ACCESS_FAILURE.search(excerpt) and not re.search(
            r"captcha|access denied|forbidden|erişim engell|robot|verify you are|unusual traffic|not found|bulunamadı|stokta yok|out of stock|tükendi",
            excerpt, re.I,
        ):
            raise ValueError("This is not evidence of an access/availability failure. Quote-format errors need corrected refs, not a site blocker.")
        return observation

    def describe_result(
        result: ComparisonResult | None,
    ) -> str:
        if result is None:
            return "None"

        return (
            f"{result.result_id} | "
            f"{result.title} | "
            f"source={result.source} | "
            f"public={get_public_total(result)} | "
            f"conditional="
            f"{get_conditional_total(result)} | "
            f"condition={result.price_condition} | "
            f"verified={result.verified}"
        )

    def terminal_verification_message(result: ComparisonResult) -> str | None:
        if not result.verification_is_terminal():
            return None
        return (
            f"VERIFICATION SKIPPED: {result.result_id} is already "
            f"{result.verification_status.value}. Move to another offer "
            "or continue the source research."
        )

    def record_validation_failure(
        state: ComparisonState,
        result: ComparisonResult,
        error: ValueError | str,
        *,
        correction_hint: str = "",
    ) -> str:
        reason = str(error).strip()
        terminal = result.record_verification_failure(reason)
        state.reset_finalization()
        refresh_source_rankings(state, result.source)

        suffix = f" {correction_hint.strip()}" if correction_hint.strip() else ""

        if terminal:
            return (
                f"VERIFICATION BLOCKED: {reason}{suffix}\n"
                f"RETRY BUDGET EXHAUSTED: {result.result_id} is now terminal "
                f"after {result.verification_attempts} failed verification attempt(s). "
                "Do not verify this candidate again; move to another offer or source."
            )

        return (
            f"VERIFICATION BLOCKED: {reason}{suffix}\n"
            f"Verification failures: {result.verification_attempts}/"
            f"{MAX_VERIFICATION_ATTEMPTS}. Correct the evidence and retry only "
            "if there is a meaningful change."
        )


    def record_final_page_validation_failure(
        state: ComparisonState,
        result: ComparisonResult,
        error: ValueError | str,
        *,
        correction_hint: str = "",
    ) -> str:
        """Record final-page evidence failure without invalidating the winner."""
        reason = str(error).strip()
        terminal = state.record_final_page_failure(reason)
        suffix = f" {correction_hint.strip()}" if correction_hint.strip() else ""

        if terminal:
            return (
                f"FINAL PAGE BLOCKED: {reason}{suffix}\n"
                "RETRY BUDGET EXHAUSTED: final-page confirmation is now terminal "
                f"after {state.final_page_attempts} failed attempt(s). "
                f"{result.result_id} remains VERIFIED and finalized; report the "
                "winner but state that the final page could not be freshly confirmed."
            )

        return (
            f"FINAL PAGE BLOCKED: {reason}{suffix}\n"
            f"Final-page failures: {state.final_page_attempts}/"
            f"{MAX_FINAL_PAGE_ATTEMPTS}. The existing VERIFIED winner is preserved. "
            "Retry only with meaningfully corrected fresh evidence."
        )


    @tool
    def research_status() -> str:
        """Return the progress of active comparison research."""

        state = get_state()

        if state is None:
            return "No active comparison research."

        source_lines = []

        for source in state.planned_sources:
            source_state = state.get_source_state(source)

            if source_state is None:
                continue

            source_lines.append(
                f"- {source}: "
                f"{source_state.status.value}, "
                f"results={len(source_state.result_ids)}, "
                f"best_public="
                f"{source_state.best_public_result_id}, "
                f"best_conditional="
                f"{source_state.best_conditional_result_id}"
            )

        remaining = [
            source
            for source in state.planned_sources
            if (
                state.get_source_state(source)
                is not None
                and not state
                .get_source_state(source)
                .is_terminal()
            )
        ]

        # Keep unresolved offers visible even when their source is closed.
        pending_lines = []

        for result in get_pending_verifications(state):
            pending_lines.append(
                f"- {describe_result(result)} | "
                f"currency={result.currency or 'unknown'} | "
                f"seller={result.seller or 'unknown'} | "
                f"offer_url={result.offer_url or 'unknown'} | "
                f"discovery_url={result.url or 'unknown'}"
            )

        pending_summary = (
            "\n".join(pending_lines)
            if pending_lines
            else "None"
        )

        return (
            f"Category: {state.category}\n"
            f"Target product: {state.target_product}\n"
            f"Coverage complete: "
            f"{state.coverage_complete()}\n"
            f"Remaining sources: {remaining}\n"
            f"Results: {len(state.results)}\n"
            f"Verified results: "
            f"{len(state.get_verified_results())}\n"
            f"Finalized: {state.is_finalized()}\n"
            f"Final page verified: "
            f"{state.final_page_verified}\n"
            f"Staging required: "
            f"{state.requires_staging}\n"
            f"Staging status: "
            f"{state.staging_status.value}\n"
            f"Ready to return: "
            f"{state.is_ready_to_return()}\n\n"
            + "\n".join(source_lines)
            + "\n\nPENDING OFFER VERIFICATIONS:\n"
            + pending_summary
        )

    @tool
    def research_read_observation(
        observation_id: str,
        offer_ref: str | None = None,
    ) -> str:
        """
        Read a previously stored browser observation.

        This is archived evidence only. It does not make the observation
        current again and does not replace fresh browser verification.
        """

        cleaned_id = observation_id.strip()

        if not cleaned_id:
            return "ARCHIVE READ BLOCKED: observation_id is required."

        observation = observation_store.get(cleaned_id)

        if observation is None:
            return "ARCHIVE READ BLOCKED: Observation not found."

        content = observation.page_text

        if offer_ref:
            try:
                content = get_snapshot_subtree(
                    observation.page_text,
                    offer_ref,
                )
            except ValueError as error:
                return (
                    "ARCHIVE READ BLOCKED: "
                    f"{error}"
                )

        return (
            "ARCHIVED BROWSER OBSERVATION\n"
            f"Observation ID: {observation.observation_id}\n"
            f"Page URL: {observation.page_url}\n"
            f"Captured at: {observation.captured_at.isoformat()}\n"
            "Freshness/currentness is NOT established by this tool.\n"
            "Use a fresh browser_snapshot for verification.\n\n"
            f"{content}"
        )

    @tool
    def research_start_source(
        source: str,
    ) -> str:
        """Start researching one planned source."""

        state = get_state()

        if state is None:
            return (
                "SOURCE START BLOCKED: "
                "No active comparison research."
            )

        canonical_source = get_canonical_source(
            state.planned_sources,
            source,
        )

        if canonical_source is None:
            return (
                f"SOURCE START BLOCKED: "
                f"{source} is not in the research plan."
            )

        source_state = state.get_source_state(
            canonical_source
        )

        if source_state is None:
            return "SOURCE START BLOCKED."

        if source_state.is_terminal():
            return (
                f"SOURCE ALREADY FINISHED: "
                f"{canonical_source}"
            )

        if (
            source_state.status
            == SourceStatus.RESEARCHING
        ):
            return (
                f"SOURCE ALREADY RESEARCHING: "
                f"{canonical_source}"
            )

        if not state.start_source(canonical_source):
            return (
                f"SOURCE START BLOCKED: "
                f"{canonical_source}"
            )

        return (
            f"SOURCE RESEARCH STARTED: "
            f"{canonical_source}"
        )

    @tool
    def research_record_discovery_attempt(
        source: str,
        query: str,
        note: str | None = None,
        observation_id: str = "",
    ) -> str:
        """
        Record one distinct search/discovery attempt made on a research source.
        """

        state = get_state()

        if state is None:
            return "NO ACTIVE COMPARISON."

        canonical_source = get_canonical_source(
            state.planned_sources,
            source,
        )

        if canonical_source is None:
            return (
                "DISCOVERY ATTEMPT REJECTED: "
                f"{source} is not a planned source."
            )

        source_state = state.get_source_state(
            canonical_source
        )

        if source_state is None:
            return (
                "DISCOVERY ATTEMPT REJECTED: "
                "Source state could not be found."
            )

        if source_state.status != SourceStatus.RESEARCHING:
            return (
                "DISCOVERY ATTEMPT REJECTED: "
                f"{canonical_source} must be in RESEARCHING state."
            )

        try:
            observation = source_evidence(canonical_source, observation_id)
        except ValueError as error:
            return f"DISCOVERY ATTEMPT REJECTED: {error}"
        failure = access_failure_excerpt(observation)
        if failure:
            return (
                "DISCOVERY ATTEMPT NOT COUNTED: The page is unavailable, not an empty search. "
                "Use the site's actual search form if the URL is wrong; for an access block call "
                "research_complete_source(outcome='blocked') with this observation_id and "
                f"copied observed_evidence: {failure}"
            )
        fingerprint = hashlib.sha256((observation.page_url + "\n" + visible_text(observation.page_text)).encode()).hexdigest()
        if any(item["fingerprint"] == fingerprint for item in source_state.discovery_evidence):
            return "DISCOVERY ATTEMPT NOT COUNTED: This same page content was already recorded. Perform and inspect a different search."
        added = source_state.record_discovery_attempt(
            query=query,
            note=note,
        )

        if not added:
            return (
                "DISCOVERY ATTEMPT NOT COUNTED: "
                "The query was empty or has already been recorded."
            )

        source_state.discovery_evidence.append({
            "query": query.strip(), "observation_id": observation.observation_id,
            "url": observation.page_url, "fingerprint": fingerprint,
            "matching_product_visible": bool(state.target_product and has_discovery_identity(
                observation.page_text, state.target_product, state.target_product)),
        })

        return (
            "DISCOVERY ATTEMPT RECORDED.\n"
            f"Source: {canonical_source}\n"
            f"Query: {query.strip()}\n"
            f"Distinct attempts: "
            f"{source_state.discovery_attempt_count()}"
        )

    @tool
    def research_add_result(
        title: str,
        source: str,
        model: str | None = None,
        variant: str | None = None,
        sku: str | None = None,
        seller: str | None = None,
        regular_price: float | None = None,
        price: float | None = None,
        price_condition: str | None = None,
        shipping_cost: float | None = None,
        currency: str | None = None,
        url: str | None = None,
        offer_url: str | None = None,
        effective_total: float | None = None,
        public_total: float | None = None,
        conditional_total: float | None = None,
        details: dict | None = None,
        observation_id: str = "",
    ) -> str:
        """Store one offer found on the active source."""

        state = get_state()

        if state is None:
            return (
                "RESULT BLOCKED: "
                "No active comparison research."
            )

        canonical_source = get_canonical_source(
            state.planned_sources,
            source,
        )

        if canonical_source is None:
            return (
                f"RESULT BLOCKED: "
                f"{source} is not in the research plan."
            )

        source_state = state.get_source_state(
            canonical_source
        )

        if (
            source_state is None
            or source_state.status
            != SourceStatus.RESEARCHING
        ):
            return (
                "RESULT BLOCKED: "
                "Call research_start_source first."
            )

        # Direct sources may only contribute offers
        # discovered on their own website.
        if (
            url
            and not url_belongs_to_source(
                canonical_source,
                url,
            )
        ):
            return (
                "RESULT BLOCKED: "
                f"The result URL does not belong to "
                f"{canonical_source}. "
                "Research this source directly instead of using "
                "another marketplace, search engine, or snippet."
            )

        # Product identity validation applies only
        # to product comparison tasks.
        if state.target_product:
            identity_conflict = get_product_identity_conflict(
                state.target_product,
                title,
            )

            if identity_conflict:
                return (
                    "RESULT BLOCKED: "
                    "Product identity does not match the user's request. "
                    f"Reason: {identity_conflict}"
                )


        money_error = validate_money_values(
            regular_price=regular_price,
            price=price,
            shipping_cost=shipping_cost,
            effective_total=effective_total,
            public_total=public_total,
            conditional_total=conditional_total,
        )

        if money_error:
            return (
                f"RESULT BLOCKED: {money_error}"
            )

        price_condition = normalize_price_condition(price_condition)

        if (
            conditional_total is not None
            and not price_condition
        ):
            return (
                "RESULT BLOCKED: "
                "conditional_total requires "
                "price_condition."
            )

        try:
            discovery = source_evidence(canonical_source, observation_id)
            if access_failure_excerpt(discovery):
                raise ValueError("An error page cannot establish a discovered offer.")
            if state.target_product and not has_discovery_identity(discovery.page_text, state.target_product, title):
                raise ValueError("No single visible product title matches this candidate. Copy the candidate's actual title; unrelated recommendation text is not its identity.")
        except ValueError as error:
            return f"RESULT BLOCKED: {error}"

        result = ComparisonResult(
            title=title.strip(),
            source=canonical_source,
            model=model.strip() if model else None,
            variant=(
                variant.strip()
                if variant
                else None
            ),
            sku=sku.strip() if sku else None,
            seller=(
                seller.strip()
                if seller
                else None
            ),
            regular_price=regular_price,
            price=price,
            price_condition=(
                price_condition.strip()
                if price_condition
                else None
            ),
            shipping_cost=shipping_cost,
            currency=(
                currency.strip()
                if currency
                else None
            ),
            url=url.strip() if url else None,
            offer_url=(
                offer_url.strip()
                if offer_url
                else None
            ),
            effective_total=effective_total,
            public_total=public_total,
            conditional_total=conditional_total,
            details={**(details or {}), "discovery_observation_id": discovery.observation_id},
        )

        for existing in state.get_results_for_source(canonical_source):
            # Fresh browser observations are evidence metadata, not offer identity.
            existing_details = {
                key: value for key, value in existing.details.items()
                if key != "discovery_observation_id"
            }
            result_details = {
                key: value for key, value in result.details.items()
                if key != "discovery_observation_id"
            }

            same_exact_offer_url = (
                bool(existing.offer_url)
                and bool(result.offer_url)
                and urls_match(existing.offer_url, result.offer_url)
            )

            # URL alone is not enough for travel: the same booking page may expose
            # several rooms, flights or vehicle options. Require the stable visible
            # identity to agree as well, while allowing one observation to omit an
            # optional SKU/model/variant that another observation already captured.
            stable_identity_matches = (
                normalize_identity(existing.title) == normalize_identity(result.title)
                and (
                    not existing.seller
                    or not result.seller
                    or normalize_identity(existing.seller)
                    == normalize_identity(result.seller)
                )
                and normalize_currency(existing.currency)
                == normalize_currency(result.currency)
                and all(
                    not getattr(existing, field)
                    or not getattr(result, field)
                    or normalize_identity(str(getattr(existing, field)))
                    == normalize_identity(str(getattr(result, field)))
                    for field in ("model", "variant", "sku")
                )
            )

            shared_detail_keys = set(existing_details) & set(result_details)
            details_do_not_conflict = all(
                existing_details[key] == result_details[key]
                for key in shared_detail_keys
            )

            if (
                same_exact_offer_url
                and stable_identity_matches
                and details_do_not_conflict
            ):
                return (
                    f"STORED RESULT ALREADY EXISTS: {existing.result_id}. "
                    "Continue its verification instead of creating a duplicate."
                )

            fields = (
                "title", "model", "variant", "sku", "seller", "price",
                "regular_price", "currency", "price_condition",
                "shipping_cost", "url", "offer_url",
            )
            if (
                all(getattr(existing, field) == getattr(result, field) for field in fields)
                and existing_details == result_details
            ):
                return (
                    f"STORED RESULT ALREADY EXISTS: {existing.result_id}. "
                    "Continue its verification."
                )

        state.add_result(result)

        refresh_source_rankings(
            state,
            canonical_source,
        )

        source_state = state.get_source_state(
            canonical_source
        )

        return (
            f"STORED RESULT: {result.title} "
            f"(result_id={result.result_id})\n"
            f"Source public best: "
            f"{source_state.best_public_result_id}\n"
            f"Source conditional best: "
            f"{source_state.best_conditional_result_id}"
        )

    @tool
    def research_complete_source(
        source: str,
        outcome: str,
        coverage_summary: str,
        observation_id: str = "",
        observed_evidence: str = "",
    ) -> str:
        """
        Finish one source.

        outcome:
        completed, no_results, or blocked.
        """

        state = get_state()

        if state is None:
            return (
                "SOURCE COMPLETION BLOCKED: "
                "No active comparison research."
            )

        canonical_source = get_canonical_source(
            state.planned_sources,
            source,
        )

        if canonical_source is None:
            return (
                "SOURCE COMPLETION BLOCKED: "
                "Source is not in the research plan."
            )

        source_state = state.get_source_state(
            canonical_source
        )

        if (
            source_state is None
            or source_state.status
            != SourceStatus.RESEARCHING
        ):
            return (
                "SOURCE COMPLETION BLOCKED: "
                "Source is not being researched."
            )

        status_map = {
            "completed": SourceStatus.COMPLETED,
            "no_results": SourceStatus.NO_RESULTS,
            "blocked": SourceStatus.BLOCKED,
        }

        status = status_map.get(
            outcome.strip().lower()
        )

        if status is None:
            return (
                "SOURCE COMPLETION BLOCKED: "
                "Invalid outcome."
            )

        summary = coverage_summary.strip()

        if not summary:
            return (
                "SOURCE COMPLETION BLOCKED: "
                "coverage_summary is required."
            )

        if status == SourceStatus.BLOCKED:
            try:
                observation = failure_evidence(observation_id, observed_evidence)
                source_evidence(canonical_source, observation_id)
            except ValueError as error:
                return f"SOURCE COMPLETION BLOCKED: {error}"
            source_state.discovery_evidence.append({
                "query": "access failure", "observation_id": observation.observation_id,
                "url": observation.page_url, "fingerprint": "error:" + observation.observation_id,
            })

        if (
            status == SourceStatus.COMPLETED
            and not source_state.result_ids
        ):
            return (
                "SOURCE COMPLETION BLOCKED: "
                "A completed source needs "
                "at least one stored result."
            )

        # A completed source must have its current best offers verified
        if status == SourceStatus.COMPLETED:
            evidence_ids = [r.details.get("discovery_observation_id")
                            for r in state.get_results_for_source(canonical_source)]
            if not source_state.discovery_evidence and not any(evidence_ids):
                return "SOURCE COMPLETION BLOCKED: Record an actual discovery observation before completing this source."
            unverified_winners = get_unverified_source_winners(
                state,
                canonical_source,
            )

            if unverified_winners:
                result_ids = ", ".join(
                    result.result_id
                    for result in unverified_winners
                    if result.result_id
                )

                return (
                    "SOURCE COMPLETION BLOCKED: "
                    f"{canonical_source} still has unverified "
                    f"source winner candidates: {result_ids}. "
                    "Open each candidate's exact seller/provider "
                    "offer page, verify its current price and "
                    "details with research_verify_result, then "
                    "run research_complete_source again."
                )

        # Do not allow NO_RESULTS after only a shallow search
        if status == SourceStatus.NO_RESULTS:
            minimum_discovery_attempts = 3
            if any(item.get("matching_product_visible") for item in source_state.discovery_evidence):
                return "SOURCE COMPLETION BLOCKED: A recorded discovery contains a matching product. Store and investigate it; a rejected tool payload is not NO_RESULTS."
            # Recheck archived evidence as well: error/challenge pages are never
            # proof that the source has no matching inventory.
            discovery_count = sum(
                1 for item in source_state.discovery_evidence
                if (observation := observation_store.get(item["observation_id"]))
                and not access_failure_excerpt(observation)
            )

            if discovery_count < minimum_discovery_attempts:
                remaining_attempts = (
                    minimum_discovery_attempts
                    - discovery_count
                )

                return (
                    "SOURCE COMPLETION BLOCKED: "
                    f"{canonical_source} cannot be marked NO_RESULTS yet. "
                    f"Only {discovery_count} distinct discovery search(es) "
                    f"have been recorded. "
                    f"At least {minimum_discovery_attempts} distinct searches "
                    f"are required before concluding that no matching result exists. "
                    f"Try {remaining_attempts} more broader or alternative search "
                    "queries, inspect the resulting listings, record each attempt "
                    "with research_record_discovery_attempt, and then try again."
                )

        if (
            status == SourceStatus.NO_RESULTS
            and source_state.result_ids
        ):
            return (
                "SOURCE COMPLETION BLOCKED: "
                "Stored results already exist."
            )

        if not state.complete_source(
            canonical_source,
            status,
            summary,
        ):
            return "SOURCE COMPLETION BLOCKED."

        return (
            f"SOURCE RESEARCH FINISHED: "
            f"{canonical_source}\n"
            f"Status: {status.value}\n"
            f"Results: "
            f"{len(source_state.result_ids)}"
        )

    @tool
    def research_mark_source_checked(
        source: str,
    ) -> str:
        """Deprecated source completion tool."""

        return (
            "DEPRECATED TOOL: "
            "Use research_start_source before browsing "
            "and research_complete_source when finished."
        )

    @tool
    def research_set_offer_url(
        result_id: str,
        offer_url: str,
    ) -> str:
        """Store the direct seller or provider URL."""

        state = get_state()

        if state is None:
            return "No active comparison research."

        result = state.get_result(result_id.strip())

        if result is None:
            return (
                f"Research result not found: "
                f"{result_id}"
            )

        terminal_message = terminal_verification_message(result)
        if terminal_message:
            return terminal_message.replace("VERIFICATION SKIPPED", "OFFER URL BLOCKED", 1)

        cleaned_offer_url = offer_url.strip()

        if not cleaned_offer_url:
            return (
                "OFFER URL BLOCKED: "
                "Offer URL cannot be empty."
            )

        # Akakce is discovery-only.
        # Its own pages cannot be exact seller offer pages.
        if (
            result.source.casefold() == "akakce"
            and is_domain_url(
                cleaned_offer_url,
                "akakce.com",
            )
        ):
            return (
                "OFFER URL BLOCKED: "
                "Akakce is a comparison source, not the merchant. "
                "Click 'Satıcıya Git' or the equivalent seller link, "
                "follow the redirect to the real merchant product page, "
                "then store that final merchant URL."
            )

        if result.offer_url != cleaned_offer_url:
            result.invalidate_verification()
            result.reset_verification_retry()
            state.reset_finalization()

        result.offer_url = cleaned_offer_url

        return (
            f"Stored direct offer URL for "
            f"{result.result_id}."
        )


    def verify_result(
        result_id: str,
        observation_id: str,
        quote: OfferQuote,
    ) -> str:
        """Verify ONE seller/provider offer against a fresh browser_snapshot.

        Store its exact offer URL first. Quote evidence must come from the
        selected offer subtree, with price node references and seller evidence.
        Covers products, flights, hotels, rentals and other purchasable offers.
        """
        state = get_state()
        if state is None:
            return "VERIFICATION BLOCKED: No active comparison research."
        result = state.get_result(result_id.strip())
        if result is None:
            return "VERIFICATION BLOCKED: Result not found."

        terminal_message = terminal_verification_message(result)
        if terminal_message:
            return terminal_message

        previous = quote_prices(result)
        result.invalidate_verification()
        state.reset_finalization()
        try:
            observation = observation_store.require_current(observation_id)
            validate_quote(state, result, observation, quote)
        except ValueError as error:
            return record_validation_failure(state, result, error)

        apply_quote(result, observation, quote)
        refresh_source_rankings(state, result.source)
        return (
            f"VERIFIED RESULT: {result.result_id}\n"
            f"Previous observation: {json.dumps(previous, ensure_ascii=False)}\n"
            f"Current observation: {json.dumps(quote_prices(result), ensure_ascii=False)}\n"
            f"Comparable public total: {get_public_total(result, strict=True)}\n"
            f"Comparable conditional total: {get_conditional_total(result, strict=True)}\n"
            "Use current amounts in rankings. Missing comparable totals remain provisional."
        )

    research_verify_result = tool("research_verify_result")(verify_result)

    @tool
    def research_verify_product(
        result_id: str,
        observation_id: str,
        selection: ProductQuoteSelection,
        final_check: bool = False,
    ) -> str:
        """Verify a product using snapshot REFS; Python copies evidence and parses prices.

        Use this instead of writing a long quote for product research. For the
        final winner, call research_finalize, take a NEW snapshot, then set
        final_check=True. A changed final price reopens ranking as usual.
        All refs must belong to the same offer. Never use this for travel.
        """
        state = get_state()
        if state is None:
            return "VERIFICATION BLOCKED: No active comparison research."
        result = state.get_result(result_id.strip())
        if result is None:
            return "VERIFICATION BLOCKED: Result not found."

        if final_check:
            if not state.is_finalized():
                return "FINAL PAGE BLOCKED: Research is not finalized."
            if state.finalized_result_id != result.result_id:
                return "FINAL PAGE BLOCKED: Wrong result."
            if state.final_page_blocked:
                return (
                    "FINAL PAGE SKIPPED: final-page confirmation already exhausted "
                    "its retry budget. The verified winner is preserved."
                )
        else:
            terminal_message = terminal_verification_message(result)
            if terminal_message:
                return terminal_message

        try:
            observation = observation_store.require_current(observation_id)
            quote = build_product_quote(state, observation, selection)
        except ValueError as error:
            if final_check:
                return record_final_page_validation_failure(
                    state,
                    result,
                    error,
                    correction_hint=(
                        "Correct the selected refs; do not translate or paraphrase evidence."
                    ),
                )

            result.invalidate_verification()
            return record_validation_failure(
                state,
                result,
                error,
                correction_hint=(
                    "Correct the selected refs; do not translate or paraphrase evidence."
                ),
            )

        if final_check:
            return confirm_final_page(result_id, observation_id, quote)

        return verify_result(result_id, observation_id, quote)

    @tool
    def research_block_verification(
        result_id: str,
        attempted_url: str,
        reason: str,
        observed_evidence: str,
        observation_id: str = "",
    ) -> str:
        """
        Record an unsuccessful offer verification attempt.

        Use only after actually attempting verification.
        Not starting or not finishing verification is not a blocker.
        Include the attempted URL and the observed failure.
        """

        state = get_state()

        if state is None:
            return "No active comparison research."

        result = state.get_result(result_id.strip())

        if result is None:
            return "VERIFICATION UPDATE REJECTED: Result not found."

        if result.verification_status != VerificationStatus.PENDING:
            return (
                "VERIFICATION UPDATE REJECTED: "
                "Only pending offers can be marked blocked."
            )

        attempted_url = attempted_url.strip()
        reason = reason.strip()
        observed_evidence = observed_evidence.strip()

        if not attempted_url or not reason or not observed_evidence:
            return (
                "VERIFICATION UPDATE REJECTED: "
                "Provide the attempted URL, reason, and observed failure."
            )

        try:
            observation = failure_evidence(observation_id, observed_evidence)
            if not urls_match(attempted_url, observation.page_url):
                raise ValueError("Attempted URL does not match the browser evidence.")
            if not any(urls_match(url, attempted_url) for url in (result.offer_url, result.url) if url):
                raise ValueError("The failure must belong to this offer's recorded URL.")
        except ValueError as error:
            return f"VERIFICATION UPDATE REJECTED: {error}"

        # Preserve the observed offer and record the actual site/access failure.
        # Unlike quote/ref validation failures above, this is explicit terminal
        # browser evidence and may block immediately.
        result.verified = False
        result.verification_attempts += 1
        result.last_verification_failure = reason
        result.verification_status = VerificationStatus.BLOCKED
        result.verification_reason = reason

        result.details.setdefault(
            "verification_failures", []
        ).append(
            {
                "attempted_url": attempted_url,
                "reason": reason,
                "observed_evidence": observed_evidence,
                "observation_id": observation.observation_id,
            }
        )

        state.reset_finalization()
        refresh_source_rankings(state, result.source)

        return (
            f"VERIFICATION BLOCKED: {result.result_id}\n"
            f"Reason: {reason}\n"
            "The observed price is preserved but remains unverified."
        )




    @tool
    def research_rankings(
        verified_only: bool = False,
    ) -> str:
        """Return rankings grouped by currency; verified rankings require full totals."""
        state = get_state()
        if state is None:
            return "No active comparison research."

        lines = [
            f"Verified only: {verified_only}",
            "Conditional prices are alternatives; eligibility is not assumed.",
        ]
        for currency in sorted({normalize_currency(item.currency) or "UNKNOWN" for item in state.results}):
            lines.append(f"Currency: {currency}")
            if currency == "UNKNOWN":
                lines.append("Unknown currency: offers cannot be price-ranked.")
                continue
            lines.extend([
                f"Best public: {describe_result(find_best_public(state, verified_only, currency=currency))}",
                f"Best conditional: {describe_result(find_best_conditional(state, verified_only, currency=currency))}",
            ])
        winner = find_best_overall(state, verified_only)
        lines.append(f"Overall public winner: {describe_result(winner)}")
        if verified_only and winner is None:
            lines.append(f"No overall winner: {no_winner_reason(state)}")
        return "\n".join(lines)

    @tool
    def research_finish_without_winner() -> str:
        """Finish resolved research when no comparable public winner can be established.

        All planned sources and pending offer investigations must be resolved first.
        Retains every offer for a partial report or a report of no matching results.
        """
        state = get_state()
        if state is None:
            return "No active comparison research."
        if not state.coverage_complete() or get_pending_verifications(state):
            return "FINISH BLOCKED: Resolve remaining sources and pending offers first."
        reason = no_winner_reason(state)
        if reason is None:
            return "FINISH BLOCKED: A comparable public winner is available. Finalize it."
        state.reset_finalization()
        state.finished_without_winner_reason = reason
        return f"RESEARCH FINISHED WITHOUT WINNER: {reason}"

    @tool
    def research_finalize(
        result_id: str,
    ) -> str:
        """Finalize the verified winner."""

        state = get_state()

        if state is None:
            return (
                "FINALIZATION BLOCKED: "
                "No active research."
            )

        # Resolve pending offers before finalizing the comparison.
        pending = get_pending_verifications(state)

        if pending:
            pending_ids = ", ".join(
                result.result_id
                for result in pending
                if result.result_id
            )

            return (
                "FINALIZATION BLOCKED: "
                f"Offers still need verification: {pending_ids}. "
                "Inspect their exact seller/provider pages. "
                "Use research_verify_result for successful verification. "
                "If an actual attempt fails, record the observed failure "
                "with research_block_verification. "
                "An unfinished task alone is not a verification blocker."
            )


        if not state.coverage_complete():
            return (
                "FINALIZATION BLOCKED: "
                "Research coverage is incomplete."
            )

        winner = state.get_verified_result(
            result_id.strip()
        )

        if winner is None:
            return (
                "FINALIZATION BLOCKED: "
                "Winner is not verified."
            )

        reason = no_winner_reason(state)
        if reason or get_public_total(winner, strict=True) is None:
            return f"FINALIZATION BLOCKED: {reason or 'Winner has no comparable public total.'}"

        if is_price_focused_query(state.query):
            cheapest = find_best_overall(
                state,
                verified_only=True,
                strict=True,
            )

            if cheapest is None:
                return (
                    "FINALIZATION BLOCKED: "
                    "Verified final totals are "
                    "not sufficient for a reliable "
                    "price winner."
                )

            if (
                winner.result_id
                != cheapest.result_id
            ):
                return (
                    "FINALIZATION BLOCKED: "
                    f"Python ranking selected "
                    f"{cheapest.result_id}, "
                    f"not {winner.result_id}."
                )

        state.finalized_result_id = (
            winner.result_id
        )

        state.final_page_verified = False
        state.final_page_url = None
        state.final_page_notes = None
        state.final_page_observation_id = None
        state.reset_final_page_retry()
        state.finished_without_winner_reason = None

        return (
            f"FINALIZATION APPROVED: "
            f"{winner.result_id}"
        )


    def confirm_final_page(
        result_id: str,
        observation_id: str,
        quote: OfferQuote,
    ) -> str:
        """Recheck the finalized offer using a NEW browser_snapshot and fresh quote.

        Final-page evidence selection is isolated from durable candidate
        verification. Only a successfully validated fresh quote may update the
        offer and reopen ranking.
        """
        state = get_state()

        if state is None or not state.is_finalized():
            return "FINAL PAGE BLOCKED: Research is not finalized."

        if state.finalized_result_id != result_id.strip():
            return "FINAL PAGE BLOCKED: Wrong result."

        winner = state.get_verified_result(result_id.strip())
        if winner is None:
            return "FINAL PAGE BLOCKED: Finalized winner is no longer verified."

        if state.final_page_blocked:
            return (
                "FINAL PAGE SKIPPED: final-page confirmation already exhausted "
                "its retry budget. The verified winner is preserved."
            )

        state.final_page_verified = False
        state.final_page_url = None
        state.final_page_observation_id = None
        state.final_page_notes = None

        try:
            observation = observation_store.require_current(observation_id)

            if observation.observation_id == winner.verification_observation_id:
                return record_final_page_validation_failure(
                    state,
                    winner,
                    "Take a new browser_snapshot after finalization.",
                )

            # Validate first without mutating durable result state.
            validate_quote(state, winner, observation, quote)

        except ValueError as error:
            return record_final_page_validation_failure(
                state,
                winner,
                error,
            )

        previous = quote_prices(winner)

        # Compare transactionally on a copy.
        refreshed = deepcopy(winner)
        apply_quote(refreshed, observation, quote)
        current = quote_prices(refreshed)

        if previous != current:
            # A real validated change may update the offer and reopen ranking.
            apply_quote(winner, observation, quote)
            refresh_source_rankings(state, winner.source)
            state.reset_finalization()

            return (
                "FINAL PAGE CHANGED: Fresh prices/details were validated and stored. "
                "Call research_rankings and research_finalize again. "
                f"Previous: {json.dumps(previous, ensure_ascii=False)}; "
                f"Current: {json.dumps(current, ensure_ascii=False)}"
            )

        if is_price_focused_query(state.query):
            best = find_best_overall(
                state,
                verified_only=True,
                strict=True,
            )
            if best is None or best.result_id != winner.result_id:
                return record_final_page_validation_failure(
                    state,
                    winner,
                    "The finalized offer is no longer the current verified public winner.",
                )

        # Same valid offer: refresh evidence only after all checks pass.
        apply_quote(winner, observation, quote)
        refresh_source_rankings(state, winner.source)

        state.finalized_result_id = winner.result_id
        state.reset_final_page_retry()
        state.final_page_verified = True
        state.final_page_url = observation.page_url
        state.final_page_observation_id = observation.observation_id
        state.final_page_notes = quote.notes

        return f"FINAL PAGE CONFIRMED: {winner.result_id}"

    research_confirm_final_page = tool("research_confirm_final_page")(confirm_final_page)

    @tool
    def research_confirm_staging_page(
        result_id: str,
        staging_url: str,
        staging_type: str,
        staging_notes: str | None = None,
    ) -> str:
        """
        Confirm that the browser reached a safe transaction stage
        before payment or irreversible confirmation.
        """

        state = get_state()

        if state is None:
            return (
                "STAGING BLOCKED: "
                "No active comparison research."
            )

        if not state.requires_staging:
            return (
                "STAGING NOT REQUIRED: "
                "This comparison does not require "
                "transaction staging."
            )

        if not state.is_finalized():
            return (
                "STAGING BLOCKED: "
                "Research must be finalized first."
            )

        if not state.final_page_verified:
            return (
                "STAGING BLOCKED: "
                "The finalized offer page must be "
                "confirmed before staging."
            )

        if (
            state.finalized_result_id
            != result_id.strip()
        ):
            return (
                "STAGING BLOCKED: "
                "This result is not the finalized winner."
            )

        allowed_types = {
            "cart",
            "checkout",
            "booking_details",
            "reservation_details",
            "passenger_details",
            "review",
        }

        normalized_type = staging_type.strip().lower()

        if normalized_type not in allowed_types:
            return (
                "STAGING BLOCKED: "
                "Unsupported staging type."
            )

        cleaned_url = staging_url.strip()

        if not cleaned_url:
            return (
                "STAGING BLOCKED: "
                "Staging URL is empty."
            )

        state.confirm_staging(
            url=cleaned_url,
            staging_type=normalized_type,
            notes=(
                staging_notes.strip()
                if staging_notes
                else None
            ),
        )

        return (
            f"STAGING CONFIRMED: "
            f"{normalized_type} at {cleaned_url}"
        )


    @tool
    def research_mark_staging_blocked(
        result_id: str,
        reason: str,
    ) -> str:
        """
        Mark staging as safely blocked when Jarvis cannot
        continue without sensitive information or unsafe actions.
        """

        state = get_state()

        if state is None:
            return (
                "STAGING BLOCKED: "
                "No active comparison research."
            )

        if not state.requires_staging:
            return "STAGING NOT REQUIRED."

        if not state.is_finalized():
            return (
                "STAGING BLOCKED: "
                "Research must be finalized first."
            )

        if (
            state.finalized_result_id
            != result_id.strip()
        ):
            return (
                "STAGING BLOCKED: "
                "This result is not the finalized winner."
            )

        cleaned_reason = reason.strip()

        if not cleaned_reason:
            return (
                "STAGING BLOCKED: "
                "A reason is required."
            )

        state.block_staging(cleaned_reason)

        return (
            f"STAGING SAFELY STOPPED: "
            f"{cleaned_reason}"
        )

    return [
    research_status,
    research_read_observation,
    research_start_source,
    research_record_discovery_attempt,
    research_add_result,
    research_complete_source,
    research_set_offer_url,
    research_verify_result,
    research_verify_product,
    research_rankings,
    research_finish_without_winner,
    research_finalize,
    research_confirm_final_page,
    research_confirm_staging_page,
    research_mark_staging_blocked,
    research_block_verification
    ]
