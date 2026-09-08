from typing import Callable
from urllib.parse import urlparse

from langchain_core.tools import tool

from core.research.comparison_state import ComparisonState, ComparisonResult, normalize_identity



def create_research_tools(
        get_state: Callable[[], ComparisonState | None],
) -> list:


    @tool
    def research_status() -> str:
        """Return the progress of the active comparison research."""

        # Get the current comparison state
        state = get_state()

        # Stop if there is no active comparison task
        if state is None:
            return "No active comparison research."


        # Count verified and unverified research results
        verified_results = sum(
            1
            for result in state.results
            if result.verified
        )

        unverified_results = (
            len(state.results) - verified_results
        )

        # Track final research readiness
        finalized = state.is_finalized()
        final_page_verified = state.final_page_verified
        ready_to_return = state.is_ready_to_return()

        # Find sources that still need to be checked
        remaining_sources = [
            source
            for source in state.planned_sources
            if source not in state.checked_sources
        ]

        # Return the current research progress
        return (
            f"Planned sources: {state.planned_sources}\n"
            f"Checked sources: {state.checked_sources}\n"
            f"Remaining sources: {remaining_sources}\n"
            f"Collected results: {len(state.results)}\n"
            f"Coverage complete: {state.coverage_complete()}\n"
            f"Verified results: {verified_results}\n"
            f"Unverified results: {unverified_results}\n"
            f"Finalized: {finalized}\n"
            f"Final page verified: {final_page_verified}\n"
            f"Ready to return: {ready_to_return}\n"
        )

    @tool
    def research_mark_source_checked(source: str) -> str:
        """Mark a planned research source as checked."""

        # Get the current comparison state
        state = get_state()

        # Stop if there is no active comparison task
        if state is None:
            return "No active comparison research."

        # Clean the source name
        requested_source = source.strip()

        # Find the canonical source name from the research plan
        matched_source = next(
            (
                planned_source
                for planned_source in state.planned_sources
                if planned_source.casefold() == requested_source.casefold()
            ),
            None,
        )

        # Reject sources that are not part of the research plan
        if matched_source is None:
            return f"Source is not in the research plan: {source}"

        # Mark the source as checked
        state.mark_source_checked(matched_source)

        return f"Marked as checked: {matched_source}"
    

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
        details: dict | None = None,
    ) -> str:
        """Store one option found during comparison research."""

        # Get the current comparison state
        state = get_state()

        # Stop if there is no active comparison task
        if state is None:
            return "No active comparison research."

        # Reject results from sources outside the active research plan
        planned_source = next(
            (
                planned
                for planned in state.planned_sources
                if planned.casefold() == source.strip().casefold()
            ),
            None,
        )

        if planned_source is None:
            return (
                f"RESULT BLOCKED: {source} is not part of the active research plan. "
                f"Use only the planned sources: {state.planned_sources}"
            )

        result = ComparisonResult(
            title=title.strip(),
            source=source.strip(),
            model=model.strip() if model else None,
            variant=variant.strip() if variant else None,
            sku=sku.strip() if sku else None,
            seller=seller.strip() if seller else None,
            regular_price=regular_price,
            price=price,
            price_condition=(
                price_condition.strip()
                if price_condition
                else None
            ),
            shipping_cost=shipping_cost,
            effective_total=effective_total,
            currency=currency,
            url=url,
            offer_url=offer_url,
            details=details or {},
        )

        # Collect identity warnings for similar results
        identity_warnings = []

        for existing_result in state.results:
            # Compare identity only when both results refer to the same model
            if result.model and existing_result.model:
                same_model = (
                    normalize_identity(result.model)
                    == normalize_identity(existing_result.model)
                )

                if not same_model:
                    continue

                identity_match = result.matches_identity(existing_result)

                # Warn when the same model has a different known SKU or variant
                if identity_match is False:
                    identity_warnings.append(
                        f"Possible variant mismatch with "
                        f"'{existing_result.title}' from "
                        f"{existing_result.source}."
                    )

                # Warn when exact identity cannot be verified
                elif identity_match is None:
                    identity_warnings.append(
                        f"Exact variant could not be verified against "
                        f"'{existing_result.title}' from "
                        f"{existing_result.source}."
                    )

        # Store the result in the active research state
        state.add_result(result)

        # Return warnings so the agent does not assume variants are identical
        if identity_warnings:
            warnings_text = " ".join(identity_warnings)

            return (
                f"Stored research result: {result.title}. "
                f"IDENTITY WARNING: {warnings_text}"
                f"(result_id={result.result_id}). "
            )

        return (
            f"Stored research result: {result.title} "
            f"(result_id={result.result_id})"
        )


    @tool
    def research_set_offer_url(
        result_id: str,
        offer_url: str,
    ) -> str:
        """Store the direct seller or provider offer URL for a research result."""

        # Get the active comparison research state
        state = get_state()

        if state is None:
            return "No active comparison research state."

        # Find the target research result
        target_result = next(
            (
                result
                for result in state.results
                if result.result_id == result_id.strip()
            ),
            None,
        )

        if target_result is None:
            return f"Research result not found: {result_id}"

        # Store the direct offer URL
        target_result.offer_url = offer_url.strip()

        return (
            f"Stored direct offer URL for "
            f"{target_result.title} "
            f"(result_id={target_result.result_id})"
        )

    

    @tool
    def research_verify_result(
        result_id: str,
        verification_url: str,
        verification_type: str,
        verification_notes: str | None = None,
        price: float | None = None,
        regular_price: float | None = None,
        price_condition: str | None = None,
        seller: str | None = None,
        shipping_cost: float | None = None,
        currency: str | None = None,
        variant: str | None = None,
        sku: str | None = None,
        effective_total: float | None = None,
        verified_details: dict | None = None,
    ) -> str:
        """Verify a research result on its exact offer page and update confirmed details.""" 

        # Get the active comparison research state
        state = get_state()

        if state is None:
            return "No active comparison research state."

        # Find the result that should be verified
        target_result = next(
            (
                result
                for result in state.results
                if result.result_id == result_id.strip()
            ),
            None,
        )

        if target_result is None:
            return f"Research result not found: {result_id}"

        # Only an exact offer page can verify a final candidate
        normalized_verification_type = verification_type.strip().lower()

        if normalized_verification_type != "exact_offer":
            return (
                "VERIFICATION BLOCKED: The result was not checked on an exact "
                "seller, provider, or booking offer page. Search results, listing "
                "pages, and comparison pages cannot verify a final candidate."
            )

        # When a direct offer URL is known, verify against that exact offer
        if target_result.offer_url:
            expected_url = urlparse(target_result.offer_url)
            current_url = urlparse(verification_url.strip())

            same_domain = (
                expected_url.netloc.casefold()
                == current_url.netloc.casefold()
            )

            same_path = (
                expected_url.path.rstrip("/")
                == current_url.path.rstrip("/")
            )

            if not (same_domain and same_path):
                return (
                    "VERIFICATION BLOCKED: The current page does not match "
                    "the known direct offer URL for this candidate."
                )

        # Update details confirmed on the exact page
        if price is not None:
            target_result.price = price

        if regular_price is not None:
            target_result.regular_price = regular_price

        if price_condition is not None:
            target_result.price_condition = price_condition.strip()

        if seller is not None:
            target_result.seller = seller.strip()

        if shipping_cost is not None:
            target_result.shipping_cost = shipping_cost

        if currency is not None:
            target_result.currency = currency.strip()

        if variant is not None:
            target_result.variant = variant.strip()

        if sku is not None:
            target_result.sku = sku.strip()

        # Store details confirmed on the exact offer page
        if verified_details is not None:
            target_result.verified_details = verified_details.copy()

        if effective_total is not None:
            target_result.effective_total = effective_total

        # Mark the result as verified
        target_result.verified = True
        target_result.verification_url = verification_url.strip()
        target_result.verification_notes = (
            verification_notes.strip()
            if verification_notes
            else None
        )

        return (
            f"Verified research result: "
            f"{target_result.title} "
            f"(result_id={target_result.result_id})"
        )

    @tool
    def research_finalize(
        result_id: str,
    ) -> str:
        """Validate whether a verified research result can be selected as the final winner."""

        # Get the active comparison research state
        state = get_state()

        if state is None:
            return "FINALIZATION BLOCKED: No active comparison research state."

        # Research cannot finish before all planned sources are covered
        if not state.coverage_complete():
            return (
                "FINALIZATION BLOCKED: Research coverage is incomplete. "
                "Continue researching the remaining planned sources."
            )

        # At least one verified result must exist
        if not state.has_verified_results():
            return (
                "FINALIZATION BLOCKED: No verified research results exist. "
                "Verify the strongest candidates on their exact pages first."
            )

        # The selected winner itself must be verified
        winner = state.get_verified_result(
            result_id.strip()
        )

        if winner is None:
            return (
                f"FINALIZATION BLOCKED: {result_id} is not a verified result. "
                "Verify this candidate or select another verified result."
            )

        # Store the verified result as the final winner
        state.finalized_result_id = winner.result_id

        return (
            f"FINALIZATION APPROVED: "
            f"{winner.title} "
            f"(result_id={winner.result_id})"
        )


    @tool
    def research_confirm_final_page(
        result_id: str,
        final_page_url: str,
        final_page_notes: str | None = None,
    ) -> str:
        """Confirm that the browser is positioned on the finalized winner page."""

        # Get the active comparison research state
        state = get_state()

        if state is None:
            return "FINAL PAGE BLOCKED: No active comparison research state."

        # A winner must already be finalized
        if not state.is_finalized():
            return (
                "FINAL PAGE BLOCKED: Research has not been finalized yet. "
                "Select and finalize a verified winner first."
            )

        # The confirmed page must belong to the finalized winner
        if state.finalized_result_id != result_id.strip():
            return (
                f"FINAL PAGE BLOCKED: {result_id} is not the finalized winner."
            )

        # Get the finalized verified result
        winner = state.get_verified_result(
            state.finalized_result_id
        )

        if winner is None or not winner.verification_url:
            return (
                "FINAL PAGE BLOCKED: The finalized winner does not have "
                "an exact verified offer URL."
            )

        # Compare the verified offer location with the current final browser page
        verified_url = urlparse(winner.verification_url)
        current_url = urlparse(final_page_url.strip())

        same_domain = (
            verified_url.netloc.casefold()
            == current_url.netloc.casefold()
        )

        same_path = (
            verified_url.path.rstrip("/")
            == current_url.path.rstrip("/")
        )

        if not (same_domain and same_path):
            return (
                "FINAL PAGE BLOCKED: The browser is not on the exact "
                "verified winner page. Navigate back to the verified offer "
                "before confirming the final page."
            )

        # Store the confirmed final browser location
        state.final_page_verified = True
        state.final_page_url = final_page_url.strip()
        state.final_page_notes = (
            final_page_notes.strip()
            if final_page_notes
            else None
        )

        return (
            f"FINAL PAGE CONFIRMED: "
            f"{result_id} "
            f"at {state.final_page_url}"
        )

    # Return all research tools
    return [
        research_status,
        research_mark_source_checked,
        research_add_result,
        research_set_offer_url,
        research_verify_result,
        research_finalize,
        research_confirm_final_page,
    ]

    