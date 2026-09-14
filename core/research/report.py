"""Render required sources, offers and links without relying on model recall."""

import html
from urllib.parse import urlparse, quote

from core.research.ranking import get_public_total, get_conditional_total
from core.research.task_classifier import normalize_text


def cell(value) -> str:
    return html.escape(str(value if value is not None else "—")).replace("|", "&#124;").replace("\n", " ").replace("\r", " ").replace("[", "&#91;").replace("]", "&#93;").replace("*", "&#42;").replace("`", "&#96;")


def offer_link(url: str | None, label: str) -> str:
    if not url:
        return "—"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return "—"
    return f"[{label}](<{quote(url, safe=':/?&=%#@+;,~!$-_.')}>)"


def render_report_table(state, prompt: str) -> str:
    turkish = any(word in normalize_text(prompt) for word in ("bul", "ucuz", "karsilastir", "arastir", "fiyat", "devam"))
    tr = lambda a, b: a if turkish else b
    lines = [tr("**Kaynak ve teklif kaydı**", "**Sources and recorded offers**")]
    ready = state.is_ready_to_return()
    lines.append(tr("Durum: ", "Status: ") + tr("tamamlandı" if ready else "kısmi", "complete" if ready else "partial"))
    lines.append(tr("Doğrulanmış teklif: ", "Verified offers: ") + str(len(state.get_verified_results())))
    lines.extend(["", tr("| Kaynak | Durum | Kanıtlı arama / erişim | Açıklama |", "| Source | Status | Evidenced discovery / access | Notes |"), "| --- | --- | --- | --- |"])
    for source in state.planned_sources:
        item = state.get_source_state(source)
        evidence = ", ".join(offer_link(e["url"], str(i + 1)) for i, e in enumerate(item.discovery_evidence))
        lines.append(f"| {cell(source)} | {cell(item.status.value)} | {evidence or '—'} | {cell(item.completion_reason)} |")
    lines.extend(["", tr("| ID / Kaynak | Ürün / Satıcı | Fiyat | Toplam / Koşullu toplam | Kapsam / Ek ücret | Doğrulama | Bağlantı |", "| ID / Source | Item / Seller | Price | Public / Conditional total | Scope / Additional cost | Verification | Link |"), "| --- | --- | --- | --- | --- | --- | --- |"])
    notes = []
    for result in state.results:
        money = lambda n: "—" if n is None else f"{n:,.2f} {cell(result.currency)}"
        public = get_public_total(result, strict=True)
        conditional = get_conditional_total(result, strict=True)
        costs = tr("dahil", "included") if result.fees_included else tr("bilinmiyor", "unknown") if result.shipping_cost is None and result.mandatory_fees is None else f"{money(result.shipping_cost)} / {money(result.mandatory_fees)}"
        link = offer_link(result.offer_url or result.verification_url or result.url, tr("Teklif", "Offer"))
        if result.url and result.url != result.offer_url:
            link += " · " + offer_link(result.url, tr("Keşif", "Discovery"))
        lines.append(f"| {cell(result.result_id)} / {cell(result.source)} | {cell(result.title)} / {cell(result.seller)} | {money(result.price)} | {money(public)} / {money(conditional)} | {cell(result.price_scope)} / {costs} | {cell(result.verification_status.value)} | {link} |")
        if result.price_condition:
            notes.append(cell(result.result_id) + ": " + cell(result.price_condition))
        if result.details.get("discovery_seller_label"):
            notes.append(cell(result.result_id) + ": " + tr("Keşif mağaza etiketi → doğrulanmış satıcı: ", "Discovery store label → verified seller: ")
                         + cell(result.details["discovery_seller_label"]) + " → " + cell(result.seller))
        if len(result.price_history) > 1:
            amounts = [entry.get("price") for entry in result.price_history]
            if len(set(amounts)) > 1:
                notes.append(cell(result.result_id) + ": " + tr("Fiyat geçmişi: ", "Price history: ") + " → ".join(money(a) for a in amounts))
    if notes:
        lines.extend(["", "\n\n".join(notes)])
    winner = state.get_result(state.finalized_result_id) if state.finalized_result_id else None
    lines.extend(["", tr("Seçilmiş teklif: ", "Selected offer: ") + (cell(winner.result_id) if winner else tr("yok", "none"))])
    if state.final_page_verified and winner:
        lines.append(tr("Son sayfa doğrulandı: ", "Final page confirmed: ") + offer_link(state.final_page_url, tr("Teklif", "Offer")))
    return "\n".join(lines)
