import json

from typing import Callable

from langchain_core.tools import tool

from core.research.comparison_state import (
    ComparisonResult,
    ComparisonState,
    SourceStatus,
    VerificationStatus,
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

from core.research.evidence import ObservationStore
from core.research.offer_verification import OfferQuote, validate_quote, apply_quote, quote_prices

from core.research.research_utils import (
    get_canonical_source,
    get_product_identity_conflict,
    is_price_focused_query,
    url_belongs_to_source,
    normalize_price_condition,
)

from core.research.verification import (
    is_domain_url,
    validate_money_values,
)


def create_research_tools(
    get_state: Callable[
        [],
        ComparisonState | None,
    ],
    observation_store: ObservationStore,
) -> list:

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

        added = source_state.record_discovery_attempt(
            query=query,
            note=note,
        )

        if not added:
            return (
                "DISCOVERY ATTEMPT NOT COUNTED: "
                "The query was empty or has already been recorded."
            )

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
            details=details or {},
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

            discovery_count = (
                source_state.discovery_attempt_count()
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

        result.offer_url = cleaned_offer_url

        state.reset_finalization()

        return (
            f"Stored direct offer URL for "
            f"{result.result_id}."
        )


    @tool
    def research_verify_result(
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

        previous = quote_prices(result)
        result.invalidate_verification()
        state.reset_finalization()
        try:
            observation = observation_store.require_current(observation_id)
            validate_quote(state, result, observation, quote)
        except ValueError as error:
            refresh_source_rankings(state, result.source)
            return f"VERIFICATION BLOCKED: {error}"

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

    @tool
    def research_block_verification(
        result_id: str,
        attempted_url: str,
        reason: str,
        observed_evidence: str,
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

        # Preserve the observed offer and record the failed attempt.
        result.verified = False
        result.verification_status = VerificationStatus.BLOCKED
        result.verification_reason = reason

        result.details.setdefault(
            "verification_failures", []
        ).append(
            {
                "attempted_url": attempted_url,
                "reason": reason,
                "observed_evidence": observed_evidence,
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
        state.finished_without_winner_reason = None

        return (
            f"FINALIZATION APPROVED: "
            f"{winner.result_id}"
        )


    @tool
    def research_confirm_final_page(
        result_id: str,
        observation_id: str,
        quote: OfferQuote,
    ) -> str:
        """Recheck the finalized offer using a NEW browser_snapshot and fresh quote.

        Provide the same evidence structure as research_verify_result. A changed
        price invalidates finalization and requires ranking again.
        """
        state = get_state()
        if state is None or not state.is_finalized():
            return "FINAL PAGE BLOCKED: Research is not finalized."
        if state.finalized_result_id != result_id.strip():
            return "FINAL PAGE BLOCKED: Wrong result."
        winner = state.get_verified_result(result_id.strip())
        state.final_page_verified = False
        state.final_page_url = None
        state.final_page_observation_id = None
        try:
            observation = observation_store.require_current(observation_id)
            if observation.observation_id == winner.verification_observation_id:
                return "FINAL PAGE BLOCKED: Take a new browser_snapshot after finalization."
            validate_quote(state, winner, observation, quote)
        except ValueError as error:
            winner.invalidate_verification()
            state.reset_finalization()
            return f"FINAL PAGE BLOCKED: {error}"

        previous = quote_prices(winner)
        winner.invalidate_verification()
        state.reset_finalization()
        apply_quote(winner, observation, quote)
        refresh_source_rankings(state, winner.source)
        if previous != quote_prices(winner):
            return (
                "FINAL PAGE CHANGED: Fresh prices were stored. "
                "Call research_rankings and research_finalize again. "
                f"Previous: {json.dumps(previous, ensure_ascii=False)}; "
                f"Current: {json.dumps(quote_prices(winner), ensure_ascii=False)}"
            )
        if is_price_focused_query(state.query):
            best = find_best_overall(state, verified_only=True)
            if best is None or best.result_id != winner.result_id:
                return "FINAL PAGE CHANGED: Recalculate the public winner before finalization."

        state.finalized_result_id = winner.result_id
        state.final_page_verified = True
        state.final_page_url = observation.page_url
        state.final_page_observation_id = observation.observation_id
        state.final_page_notes = quote.notes
        return f"FINAL PAGE CONFIRMED: {winner.result_id}"

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
    research_start_source,
    research_record_discovery_attempt,
    research_add_result,
    research_complete_source,
    research_set_offer_url,
    research_verify_result,
    research_rankings,
    research_finish_without_winner,
    research_finalize,
    research_confirm_final_page,
    research_confirm_staging_page,
    research_mark_staging_blocked,
    research_block_verification
    ]
