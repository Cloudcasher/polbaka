"""Тексты и форматирование сообщений бота."""

from app.schemas import FuelStatusOut

FUEL_LABELS = {
    "AI92": "АИ-92",
    "AI95": "АИ-95",
    "AI98": "АИ-98",
    "AI100": "АИ-100",
    "DT": "ДТ",
    "GAS": "Газ",
}

STATUS_LABELS = {
    "available": "✅ Есть",
    "low": "🟡 Мало",
    "queue": "🕐 Очередь",
    "empty": "❌ Пусто",
}

LEVEL_NOTES = {
    "confirmed": "подтверждено",
    "single": "1 отметка",
    "stale": "данные устарели",
}


def station_title(st) -> str:
    name = st["name"] or st["brand"] or "АЗС"
    if st["address"]:
        return f"{name} — {st['address']}"
    return name


def format_age(age_min: int) -> str:
    if age_min < 1:
        return "только что"
    if age_min < 60:
        return f"{age_min} мин назад"
    return f"{age_min // 60} ч назад"


def format_card(st, statuses: dict[str, FuelStatusOut]) -> str:
    lines = [f"⛽ <b>{station_title(st)}</b>"]
    if not statuses:
        lines.append("\nПо этой заправке пока нет отметок — будь первым!")
        return "\n".join(lines)

    lines.append("")
    for fuel, s in sorted(statuses.items()):
        parts = [f"{FUEL_LABELS.get(fuel, fuel)}: {STATUS_LABELS[s.status]}"]
        if s.queue_min:
            parts.append(f"очередь ~{s.queue_min} мин")
        if s.limit_liters:
            parts.append(f"лимит {s.limit_liters} л")
        parts.append(f"({LEVEL_NOTES[s.level]}, {format_age(s.age_min)})")
        lines.append(" · ".join(parts))
    return "\n".join(lines)
