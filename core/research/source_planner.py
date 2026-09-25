import re

from enum import Enum
from dataclasses import dataclass


from core.research.task_classifier import normalize_text, contains_keyword



class ResearchCategory(str, Enum):
    # Flight ticket comparisons
    FLIGHT = "flight"

    # Hotel and accommodation comparisons
    HOTEL = "hotel"

    # Car rental comparisons
    CAR_RENTAL = "car_rental"

    # Product comparisons
    PRODUCT = "product"

    # Job and internship comparisons
    JOB = "job"

    # Comparison tasks that do not match a known category
    GENERAL = "general"


class ProductType(str, Enum):
    # Computer parts and technology hardware
    COMPUTER_HARDWARE = "computer_hardware"

    # General consumer products
    GENERAL = "general"


@dataclass
class SourceSelection:
    sources: list[str]

    # True when Jarvis must ask the user which sources to use
    needs_clarification: bool = False

    # Number of sources requested by the user
    requested_count: int | None = None


CATEGORY_KEYWORDS = {
    ResearchCategory.FLIGHT: [
        # Turkish flight terms
        "ucak",
        "ucus",
        "ucak bileti",
        "havayolu",

        # English flight terms
        "flight",
        "airline",
        "plane ticket",
    ],

    ResearchCategory.HOTEL: [
        # Turkish hotel terms
        "otel",
        "konaklama",

        # English hotel terms
        "hotel",
        "accommodation",
    ],

    ResearchCategory.CAR_RENTAL: [
        # Turkish car rental terms
        "araba kiralama",
        "arac kiralama",
        "kiralik araba",
        "kiralik arac",

        # English car rental terms
        "car rental",
        "rent a car",
        "rental car",
    ],

    ResearchCategory.JOB: [
    # Turkish job terms
    "staj",
    "staj ilan",
    "is ilan",
    "is pozisyon",
    "pozisyon",
    "kariyer",
    "muhendis",
    "gelistirici",

    # English job terms
    "internship",
    "intern",
    "job",
    "job opening",
    "job position",
    "vacancy",
    "career",
    "engineer",
    "developer",
    "junior",
    "junior engineer",
    "junior developer",
    "software engineer",
    "ai engineer",
    "machine learning engineer",
],

    ResearchCategory.PRODUCT: [
        # Turkish product terms
        "urun",
        "telefon",
        "laptop",
        "bilgisayar",

        # English product terms
        "product",
        "phone",
        "laptop",
        "computer",
    ],
}


CATEGORY_SOURCES = {
    ResearchCategory.FLIGHT: [
        "Google Flights",
        "Skyscanner",
        "Kayak",
        "Ucuzabilet",
        "Enuygun",
        "Turkish Airlines",
        "AJet",
        "Pegasus",
        "Airline Official Websites",
    ],

    ResearchCategory.HOTEL: [
        "Google Hotels",
        "Booking",
        "Agoda",
        "Airbnb",
        "Limehome",
    ],

    ResearchCategory.CAR_RENTAL: [
        "Rentalcars",
        "Kayak",
        "DiscoverCars",
    ],

    ResearchCategory.PRODUCT: [
        "Google Shopping",
    ],

    ResearchCategory.JOB: [
        "LinkedIn",
        "Indeed",
        "Company Career Pages",
    ],
}


PRODUCT_SOURCES = {
    ProductType.COMPUTER_HARDWARE: [
        "Google Shopping",
        "Akakce",
        "Vatan Computer",
        "Itopya",
        "Hepsiburada",
        "Trendyol",
        "Ciceksepeti",
    ],

    ProductType.GENERAL: [
        "Google Shopping",
        "Trendyol",
        "Hepsiburada",
        "Akakce",
        "Ciceksepeti",
    ],
}


SOURCE_DOMAINS = {
    # Product sources
    "Trendyol": {"trendyol.com"},
    "Hepsiburada": {"hepsiburada.com"},
    "Akakce": {"akakce.com"},
    "Ciceksepeti": {"ciceksepeti.com"},
    "Vatan Computer": {"vatanbilgisayar.com"},
    "Itopya": {"itopya.com"},

    # Flight and travel sources
    "Skyscanner": {"skyscanner.com", "skyscanner.com.tr"},
    "Kayak": {"kayak.com", "kayak.com.tr"},
    "Ucuzabilet": {"ucuzabilet.com"},
    "Enuygun": {"enuygun.com"},
    "Turkish Airlines": {"turkishairlines.com"},
    "AJet": {"ajet.com"},
    "Pegasus": {"flypgs.com", "pegasusairlines.com"},
    "Booking": {"booking.com"},
    "Agoda": {"agoda.com"},
    "Airbnb": {"airbnb.com"},
    "Limehome": {"limehome.com"},
    "Rentalcars": {"rentalcars.com"},
    "DiscoverCars": {"discovercars.com"},

    # Google research sources
    "Google Shopping": {"google.com", "google.com.tr"},
    "Google Flights": {"google.com", "google.com.tr"},
    "Google Hotels": {"google.com", "google.com.tr"},

    # Job sources
    "LinkedIn": {"linkedin.com"},
    "Indeed": {"indeed.com"},
}


DYNAMIC_SOURCES = {
    "Airline Official Websites",
    "Company Career Pages",
}


def get_source_domain(source: str) -> set[str]:
    # Return known domains for this source
    return SOURCE_DOMAINS.get(source, set()).copy()


def is_dynamic_source(source: str) -> bool:
    # Check if this source can use different domains
    return source in DYNAMIC_SOURCES


COMPUTER_HARDWARE_KEYWORDS = [
    # General hardware terms
    "bilgisayar parcasi",
    "pc parcasi",
    "donanim",

    # Components
    "ekran karti",
    "gpu",
    "graphics card",
    "islemci",
    "cpu",
    "processor",
    "anakart",
    "motherboard",
    "ram",
    "ssd",
    "nvme",
    "hard disk",
    "hdd",
    "power supply",
    "psu",
    "guc kaynagi",
    "kasa",
    "computer case",
    "cpu cooler",
    "sogutucu",

    # Computer peripherals
    "mouse",
    "fare",
    "keyboard",
    "klavye",
    "monitor",
    "webcam",
    "headset",
    "gaming mouse",
    "gaming keyboard",
    "gaming monitor",

    # Common peripheral terms
    "computer mouse",
    "wireless mouse",
    "kablosuz fare",
    "mekanik klavye",
]


GENERAL_PRODUCT_KEYWORDS = [
    # Electronics
    "telefon",
    "tablet",
    "televizyon",
    "monitor",
    "kulaklik",
    "kamera",
    "klavye",
    "mouse",

    # Home appliances
    "kahve makinesi",
    "supurge",
    "airfryer",
    "blender",
    "mikser",
    "tost makinesi",

    # General consumer products
    "ayakkabi",
    "canta",
    "saat",
    "parfum",
    "oyuncak",
]


def extract_explicit_sources(prompt: str, available_sources: list[str]) -> list[str]:
    # Keep the sources explicitly mentioned by the user
    selected_sources = []

    for source in available_sources:
        if contains_keyword(prompt, source):
            selected_sources.append(source)

    return selected_sources


def extract_requested_source_count(prompt: str) -> int | None:
    # Normalize the prompt before checking source count
    normalized_prompt = normalize_text(prompt)

    match = re.search(
        r"\b(\d+)\s+"
        r"(?:(?:farkli|different)\s+)?"
        r"(?:"
        r"site|siteye|siteden|sitesinden|"
        r"sites|"
        r"website|websites|"
        r"source|sources|"
        r"kaynak|kaynaktan|kaynaklardan"
        r")\b",
        normalized_prompt
    )

    # No source count was explicitly requested
    if match is None:
        return None

    return int(match.group(1))


def allows_automatic_source_choice(prompt: str) -> bool:
    normalized_prompt =  normalize_text(prompt)

    automatic_choice_phrases = [
        # Turkish
        "fark etmez",
        "farketmez",
        "sen sec",
        "sen belirle",
        "herhangi",
        "sana birakiyorum",

        # English
        "doesnt matter",
        "doesn't matter",
        "you choose",
        "choose for me",
        "up to you",
        "any site",
        "any website",
        "any source",
        "whatever",
    ]

    return any(
        phrase in normalized_prompt
        for phrase in automatic_choice_phrases
    )


def select_sources(prompt: str, default_sources: list[str]) -> SourceSelection:
    # Find sources explicitly mentioned by the user
    explicit_sources = extract_explicit_sources(
        prompt,
        default_sources
    )

    # Check how many sources the user requested
    requested_count = extract_requested_source_count(prompt)

    # Check whether Jarvis can choose sources automatically
    allow_choice_auto = allows_automatic_source_choice(prompt)

    # No specific source preference was given
    if not explicit_sources and requested_count is None:
        return SourceSelection(sources=default_sources.copy())

    # The user explicitly named sources
    # but did not request a specific count
    if explicit_sources and requested_count is None:
        return SourceSelection(sources=explicit_sources)

    # The user requested a number of sources
    # but did not name any of them
    if not explicit_sources and requested_count is not None:
        if allow_choice_auto:
            selected_sources = default_sources[:requested_count]

            # Not enough default sources are available
            if len(selected_sources) < requested_count:
                return SourceSelection(
                    sources=selected_sources,
                    needs_clarification=True,
                    requested_count=requested_count
                )

            return SourceSelection(
                sources=selected_sources,
                requested_count=requested_count
            )

        return SourceSelection(
            sources=[],
            needs_clarification=True,
            requested_count=requested_count
        )

    # The user named exactly the requested number of sources
    if len(explicit_sources) == requested_count:
        return SourceSelection(
            sources=explicit_sources,
            requested_count=requested_count
        )

    # The user named fewer sources and allowed Jarvis
    # to choose the remaining ones
    if(
        len(explicit_sources) < requested_count
        and allow_choice_auto
    ):
        selected_sources = explicit_sources.copy()

        for source in default_sources:
            # Do not add the same source twice
            if source in selected_sources:
                continue

            selected_sources.append(source)


            # Stop when the request count is reached
            if len(selected_sources) == requested_count:
                break


        # The available source list was not large enough
        if len(selected_sources) < requested_count:
            return SourceSelection(
                sources=selected_sources,
                needs_clarification=True,
                requested_count=requested_count
            )

        return SourceSelection(
            sources=selected_sources,
            requested_count=requested_count
        )

    # The request is conflicting or incomplete
    return SourceSelection(
        sources=explicit_sources,
        needs_clarification=True,
        requested_count=requested_count
    )



def detect_research_category(prompt: str) -> ResearchCategory:
    # Check known research categories first
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if contains_keyword(prompt, keyword):
                return category

    # Treat computer hardware terms as product research
    for keyword in COMPUTER_HARDWARE_KEYWORDS:
        if contains_keyword(prompt, keyword):
            return ResearchCategory.PRODUCT

    # Check common consumer product terms
    for keyword in GENERAL_PRODUCT_KEYWORDS:
        if contains_keyword(prompt, keyword):
            return ResearchCategory.PRODUCT

    # Use general research when no known category matches
    return ResearchCategory.GENERAL



def plan_source_selection(
    prompt: str,
    category: ResearchCategory | None = None,
    product_type: ProductType | None = None,
) -> SourceSelection:

    # Detect the category only when it was not already provided
    if category is None:
        category = detect_research_category(prompt)

    # Use specialized sources for product comparisons
    if category == ResearchCategory.PRODUCT:
        # Detect the product type only when it was not already provided
        if product_type is None:
            product_type = detect_product_type(prompt)

        default_sources = PRODUCT_SOURCES[
            product_type
        ].copy()

    # Use trusted default sources for known categories
    elif category in CATEGORY_SOURCES:
        default_sources = CATEGORY_SOURCES[
            category
        ].copy()

    # Keep general research actionable
    else:
        default_sources = ["Web Search"]

    # Apply the user's source preferences
    return select_sources(
        prompt,
        default_sources,
    )


def plan_sources(
    prompt: str,
    category: ResearchCategory | None = None,
    product_type: ProductType | None = None,
) -> list[str]:
    # Keep the old API for existing code
    selection = plan_source_selection(
        prompt,
        category=category,
        product_type=product_type,
    )

    return selection.sources


def detect_product_type(prompt: str) -> ProductType:
    # Check if the product is computer hardware
    for keyword in COMPUTER_HARDWARE_KEYWORDS:
        if contains_keyword(prompt, keyword):
            return ProductType.COMPUTER_HARDWARE

    # Use general product type by default
    return ProductType.GENERAL