from enum import Enum
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



def plan_sources(
    prompt: str,
    category: ResearchCategory | None = None,
    product_type: ProductType | None = None,
) -> list[str]:
    
    # Detect the category only when it was not already provided
    if category is None:
        category = detect_research_category(prompt)

    # Use specialized sources for product comparisons
    if category == ResearchCategory.PRODUCT:
        # Detect the product type only when it was not already provided
        if product_type is None:
            product_type = detect_product_type(prompt)

        return PRODUCT_SOURCES[product_type].copy()

    # Return trusted default sources for known categories
    if category in CATEGORY_SOURCES:
        return CATEGORY_SOURCES[category].copy()

    # Keep semantic/general comparisons actionable instead of creating an empty
    # plan that can never reach terminal coverage.
    return ["Web Search"]


def detect_product_type(prompt: str) -> ProductType:
    # Check if the product is computer hardware
    for keyword in COMPUTER_HARDWARE_KEYWORDS:
        if contains_keyword(prompt, keyword):
            return ProductType.COMPUTER_HARDWARE

    # Use general product type by default
    return ProductType.GENERAL
