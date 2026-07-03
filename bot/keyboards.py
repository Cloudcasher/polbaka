"""Клавиатуры бота. Формат callback_data: "действие:аргументы"."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .texts import FUEL_LABELS, STATUS_LABELS

FUELS = ["AI92", "AI95", "AI98", "DT", "GAS"]


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Заправки рядом", request_location=True)],
            [KeyboardButton(text="🔔 Мои подписки")],
        ],
        resize_keyboard=True,
    )


def stations_list(stations) -> InlineKeyboardMarkup:
    from .texts import station_title

    rows = []
    for st in stations:
        km = st["dist_m"] / 1000
        rows.append([
            InlineKeyboardButton(
                text=f"{station_title(st)} · {km:.1f} км",
                callback_data=f"st:{st['id']}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def station_card(station_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Отметить", callback_data=f"rep:{station_id}"),
            InlineKeyboardButton(text="🔔 Следить", callback_data=f"sub:{station_id}"),
        ],
    ])


def fuel_choice(prefix: str, station_id: int) -> InlineKeyboardMarkup:
    """Выбор марки топлива; prefix — repf (отметка) или subf (подписка)."""
    row = [
        InlineKeyboardButton(
            text=FUEL_LABELS[f], callback_data=f"{prefix}:{station_id}:{f}"
        )
        for f in FUELS
    ]
    # По 3 кнопки в ряд
    return InlineKeyboardMarkup(inline_keyboard=[row[:3], row[3:]])


def status_choice(station_id: int, fuel: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label, callback_data=f"reps:{station_id}:{fuel}:{status}"
            )
        ]
        for status, label in STATUS_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscriptions_list(subs) -> InlineKeyboardMarkup:
    from .texts import FUEL_LABELS, station_title

    rows = []
    for s in subs:
        rows.append([
            InlineKeyboardButton(
                text=f"❌ {station_title(s)} · {FUEL_LABELS[s['fuel_type']]}",
                callback_data=f"unsub:{s['id']}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
