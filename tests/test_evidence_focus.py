from core.research.evidence import get_focused_snapshot


PAGE_TEXT = """
- list "Ürünler" [ref=e1]
  - link "Apple AirPods Pro 2. Nesil" [ref=e2]
  - text "12.999 TL" [ref=e3]
  - text "Satıcı: Teknoloji Mağazası" [ref=e4]
- link "Başka bir ürün" [ref=e5]
""".strip()


def test_focused_snapshot_ignores_inflected_task_words():
    result = get_focused_snapshot(
        PAGE_TEXT,
        "AirPods Pro ürünleri, fiyatları ve satıcıları",
        page_url="https://www.hepsiburada.com/ara?q=airpods",
    )

    assert result
    assert "FOCUSED BROWSER SNAPSHOT" in result
    assert "Apple AirPods Pro 2. Nesil" in result
    assert "12.999 TL" in result


def test_focused_snapshot_matches_short_specific_focus():
    result = get_focused_snapshot(
        PAGE_TEXT,
        "AirPods Pro",
        page_url="https://www.hepsiburada.com/ara?q=airpods",
    )

    assert result
    assert "Apple AirPods Pro 2. Nesil" in result


def test_focused_snapshot_returns_empty_for_unrelated_focus():
    result = get_focused_snapshot(
        PAGE_TEXT,
        "RTX 5090",
        page_url="https://www.hepsiburada.com/ara?q=airpods",
    )

    assert result == ""