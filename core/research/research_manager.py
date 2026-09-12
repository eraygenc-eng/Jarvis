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


async def extract_target_product_semantically(
    prompt: str,
    llm: BaseLLM,
    config: dict | None = None,
) -> str:
    # Extract only the product identity from the user's request.
    extraction_prompt = f"""
Extract only the specific product identity from the request below.

Rules:
- Return only the product name or model.
- Keep brand, model number, generation, and edition when explicitly mentioned.
- Remove shopping intent such as cheapest, compare, find, search, buy, or look for.
- Do not add product information that the user did not provide.
- Do not guess a more complete official product name.
- Do not include explanations.

Examples:

Request:
bana Logitech Superlight 2 mouse bak ve en ucuzunu bul
Answer:
Logitech Superlight 2

Request:
RTX 5070 en ucuz nerede
Answer:
RTX 5070

Request:
iPhone 17 Pro 256 GB siyah fiyatlarını karşılaştır
Answer:
iPhone 17 Pro 256 GB siyah

Request:
{prompt}

Answer:
"""

    response = await llm.get_model().ainvoke(
        extraction_prompt,
        config=config,
    )

    target_product = extract_response_text(
        response.content
    ).strip()

    # Fall back safely when extraction fails.
    if not target_product:
        return prompt.strip()

    return target_product



async def detect_category_semantically(
    prompt: str, 
    llm: BaseLLM,
    config: dict | None = None,
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
    response = await llm.get_model().ainvoke(
        classification_prompt,
        config=config,
    )

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
    config: dict | None = None,
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
    response = await llm.get_model().ainvoke(
        classification_prompt,
        config=config,
    )

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
    config: dict | None = None,
) -> ComparisonState:
    # Try the fast keyword-based category detection first
    category = detect_research_category(prompt)

    # Use semantic classification only when keywords are not enough
    if category == ResearchCategory.GENERAL:
        category = await detect_category_semantically(
            prompt,
            llm,
            config=config,
        )

    # Product comparisons may need a second level of classification
    product_type = None
    target_product = None

    if category == ResearchCategory.PRODUCT:
        # Extract a clean product identity once for the whole research.
        target_product = await extract_target_product_semantically(
            prompt,
            llm,
            config=config,
        )

        # Try the fast keyword-based product type detection first
        product_type = detect_product_type(prompt)

        # Use semantic product classification when keywords are not enough
        if product_type == ProductType.GENERAL:
            product_type = await detect_product_type_semantically(
                prompt,
                llm,
                config=config,
            )

    # Plan sources using the resolved category and product type
    sources = plan_sources(
        prompt,
        category=category,
        product_type=product_type,
    )

    # Purchasable or bookable comparisons should end
    # at a safe pre-commit transaction stage
    requires_staging = False

    # Create the initial comparison research state
    return ComparisonState(
        query=prompt,
        category=category.value,
        target_product=target_product,
        planned_sources=sources,
        requires_staging=requires_staging,
    )
