from dataclasses import dataclass, field
from typing import Optional



@dataclass
class ScreenElement:
    element_type: str
    label: Optional[str] = None

    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    clickable: bool = False
    visible: bool = True


    @property
    def center(self) -> tuple[int, int]:
        return (
            self.x + self.width // 2,
            self.y + self.height // 2,
        )



@dataclass
class ScreenState:
    active_app: Optional[str] = None
    window_title: Optional[str] = None

    screen_width: int = 0
    screen_height: int = 0

    # Store all detected screen elements in a new list
    elements: list[ScreenElement] = field(default_factory=list)

    # Store the raw vision model description
    raw_description: Optional[str] = None



    def find_element(self, label: str, element_type: Optional[str] = None) -> Optional[ScreenElement]:
        target = label.strip().lower()

        fallback = None

        for element in self.elements:
            if not element.label:
                continue

            if element.label.strip().lower() != target:
                continue

            if fallback is None:
                fallback = element

            if element_type is None:
                return element

            current_type = (element.element_type or "").strip().lower()
            preferred_type = element_type.strip().lower()

            if current_type == preferred_type:
                return element

        return fallback