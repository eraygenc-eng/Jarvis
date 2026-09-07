from core.llm.base import BaseLLM
from core.research.comparison_state import ComparisonState

from core.research.source_planner import (
    ProductType,
    ResearchCategory,
    detect_product_type,
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


async def detect_product_type_semantically(
    prompt: str,
    llm: BaseLLM,
) -> ProductType:
    # Ask the LLM to classify only the product type
    classification_prompt = f"""
Classify the product in the following request into exactly one category:

computer_hardware
general

Use computer_hardware for computer components and peripherals such as
mice, keyboards, monitors, GPUs, CPUs, SSDs, RAM, headsets, webcams,
and similar computer-related hardware.

Request:
{prompt}

Return only the category name.
"""

    # Use the existing primary Jarvis model
    response = await llm.get_model().ainvoke(classification_prompt)

    # Extract and normalize the model response
    product_type_name = extract_response_text(
        response.content
    ).strip().lower()

    # Convert the model response into a known product type
    try:
        return ProductType(product_type_name)
    except ValueError:
        return ProductType.GENERAL



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

    # Product comparisons may need a second level of classification
    product_type = None

    if category == ResearchCategory.PRODUCT:
        # Try the fast keyword-based product type detection first
        product_type = detect_product_type(prompt)

        # Use semantic product classification when keywords are not enough
        if product_type == ProductType.GENERAL:
            product_type = await detect_product_type_semantically(
                prompt,
                llm,
            )

    # Plan sources using the resolved category and product type
    sources = plan_sources(
        prompt,
        category=category,
        product_type=product_type,
    )

    # Create the initial comparison research state
    return ComparisonState(
        query=prompt,
        planned_sources=sources,
    )