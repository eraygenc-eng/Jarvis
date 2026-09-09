import re
from enum import Enum


class TaskType(str, Enum):
    # Direct action requested by the user
    ACTION = "action"

    # User wants a specific piece of information
    LOOKUP = "lookup"

    # User wants multiple options researched and compared
    COMPARISON = "comparison"



TURKISH_CHAR_MAP = str.maketrans({
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
})


def normalize_text(text: str) -> str:
    # Normalize Turkish characters and letter casing
    return text.casefold().translate(TURKISH_CHAR_MAP).strip()


TURKISH_SUFFIXES = [
    # Plural suffixes
    "lar",
    "ler",

    # Common case and possessive suffixes
    "i",
    "u",
    "a",
    "e",
    "in",
    "un",
    "ni",
    "nu",
    "nin",
    "nun",
    "da",
    "de",
    "dan",
    "den",

    # Common plural combinations
    "lari",
    "leri",
    "larin",
    "lerin",
    "larini",
    "lerini",
    "lara",
    "lere",
    "larda",
    "lerde",
    "lardan",
    "lerden",

    # Common combined possessive / case suffixes
    "ini",
    "unu",
    "sini",
    "sunu",


    # Buffer consonant suffixes
    "yi",
    "yu",
    "ya",
    "ye",
    "yin",
    "yun",
]


ENGLISH_SUFFIXES = [
    # Common English plural suffixes
    "s",
    "es",

    # Common English possessive suffix
    "'s",
]


def contains_keyword(text: str, keyword: str) -> bool:
    # Normalize both values before matching
    normalized_text = normalize_text(text)
    normalized_keyword = normalize_text(keyword)

    # Match the exact keyword first
    exact_pattern = rf"(?<!\w){re.escape(normalized_keyword)}(?!\w)"

    if re.search(exact_pattern, normalized_text):
        return True


    # Support common Turkish and English suffixes
    allowed_suffixes = TURKISH_SUFFIXES + ENGLISH_SUFFIXES

    suffix_pattern = "|".join(
        re.escape(suffix)
        for suffix in allowed_suffixes
    )

    inflected_pattern = (
        rf"(?<!\w)"
        rf"{re.escape(normalized_keyword)}"
        rf"(?:{suffix_pattern})"
        rf"(?!\w)"
    )

    return re.search(inflected_pattern, normalized_text) is not None


COMPARISON_KEYWORDS = [
    # Turkish comparison phrases
    "en ucuz",
    "en uygun",
    "en iyi",
    "en mantıklı",
    "en avantajlı",
    "karşılaştır",
    "kıyasla",
    "alternatifleri",
    "hangisi daha iyi",
    "hangisi daha ucuz",

    # English comparison phrases
    "cheapest",
    "best option",
    "best choice",
    "most affordable",
    "compare",
    "comparison",
    "alternatives",
    "which is better",
    "which is cheaper",
]

ACTION_KEYWORDS = [
    # Turkish action phrases
    "satın al",
    "bilet al",
    "rezervasyon yap",
    "rezerve et",
    "gönder",
    "aç",
    "kapat",
    "tıkla",

    # English action phrases
    "buy",
    "book",
    "reserve",
    "send",
    "open",
    "close",
    "click",
]


def classify_task(prompt: str) -> TaskType:
    # Check comparison intent first
    for keyword in COMPARISON_KEYWORDS:
        if contains_keyword(prompt, keyword):
            return TaskType.COMPARISON

    # Check direct action intent
    for keyword in ACTION_KEYWORDS:
        if contains_keyword(prompt, keyword):
            return TaskType.ACTION

    # Use lookup as the default task type
    return TaskType.LOOKUP