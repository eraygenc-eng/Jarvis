from core.llm.base import BaseLLM
from core.research.comparison_state import ComparisonState
from core.research.source_planner import (
    ResearchCategory,
    detect_research_category,
    plan_sources,
)


def extract_response_text(content) -> str:
    # Return plain text responses directly
    if isinstance(content, str):
        return content

    # Extract text from block-based model responses
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict)
        )

    # Use string conversion as a final fallback
    return str(content)



async def detect_category_semantically(
    prompt: str, 
    llm: BaseLLM,
) -> ResearchCategory:
    # Ask the LLM to classify only the research category
    classification_prompt = f"""
Classify the following comparison request into exactly one category:

flight
hotel
car_rental
product
job
general

Request:
{prompt}

Return only the category name.
"""

    # Use the existing primary Jarvis model
    response = await llm.get_model().ainvoke(classification_prompt)

    # Extract and normalize the category returned by the model
    category_name = extract_response_text(
        response.content
    ).strip().lower()


    # Convert the model response into a known category
    try:
        return ResearchCategory(category_name)
    except ValueError:
        return ResearchCategory.GENERAL


async def create_comparison_state(
    prompt: str,
    llm: BaseLLM,
) -> ComparisonState:
    # Try the fast keyword-based category detection first
    category = detect_research_category(prompt)

    # Use semantic classification only when keywords are not enough
    if category == ResearchCategory.GENERAL:
        category = await detect_category_semantically(
            prompt,
            llm,
        )

    # Plan sources using the resolved research category
    sources = plan_sources(
        prompt,
        category=category,
    )

    # Create the initial comparison research state
    return ComparisonState(
        query=prompt,
        planned_sources=sources,
    )