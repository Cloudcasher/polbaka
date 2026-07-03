"""Хендлеры бота: /start, геолокация, карточка АЗС, отметки, подписки."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.service import fuel_statuses_for

from . import keyboards as kb
from . import queries as q
from .texts import FUEL_LABELS, STATUS_LABELS, format_card, station_title

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await q.upsert_tg_user(message.from_user.id)
    await message.answer(
        "⛽ <b>ПолБака</b> — где в Питере и области есть бензин.\n\n"
        "📍 Пришли геолокацию — покажу ближайшие заправки и что на них с топливом.\n"
        "🔔 Подпишись на свою АЗС — напишу, как только там появится нужное топливо.\n\n"
        "Данные добавляют сами водители. Увидел ситуацию на заправке — отметь, "
        "помоги остальным!",
        reply_markup=kb.main_menu(),
    )


@router.message(F.location)
async def on_location(message: Message) -> None:
    stations = await q.nearest_stations(
        message.location.latitude, message.location.longitude
    )
    await message.answer(
        "Ближайшие заправки (жми, чтобы посмотреть статус):",
        reply_markup=kb.stations_list(stations),
    )


@router.message(F.text == "🔔 Мои подписки")
async def on_my_subs(message: Message) -> None:
    user_id = await q.upsert_tg_user(message.from_user.id)
    subs = await q.list_subscriptions(user_id)
    if not subs:
        await message.answer(
            "Подписок пока нет. Найди заправку через «📍 Заправки рядом» и нажми «🔔 Следить»."
        )
        return
    await message.answer(
        "Твои подписки (жми, чтобы удалить):",
        reply_markup=kb.subscriptions_list(subs),
    )


@router.callback_query(F.data.startswith("st:"))
async def on_station(callback: CallbackQuery) -> None:
    station_id = int(callback.data.split(":")[1])
    st = await q.station_by_id(station_id)
    statuses = (await fuel_statuses_for([station_id])).get(station_id, {})
    await callback.message.answer(
        format_card(st, statuses), reply_markup=kb.station_card(station_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rep:"))
async def on_report_start(callback: CallbackQuery) -> None:
    station_id = int(callback.data.split(":")[1])
    await callback.message.answer(
        "Какое топливо?", reply_markup=kb.fuel_choice("repf", station_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("repf:"))
async def on_report_fuel(callback: CallbackQuery) -> None:
    _, station_id, fuel = callback.data.split(":")
    await callback.message.answer(
        f"Что с {FUEL_LABELS[fuel]}?",
        reply_markup=kb.status_choice(int(station_id), fuel),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reps:"))
async def on_report_status(callback: CallbackQuery) -> None:
    _, station_id, fuel, status = callback.data.split(":")
    user_id = await q.upsert_tg_user(callback.from_user.id)
    await q.insert_report(int(station_id), user_id, fuel, status)
    await callback.message.answer(
        f"Записал: {FUEL_LABELS[fuel]} — {STATUS_LABELS[status]}. Спасибо, что помогаешь! 🙌"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:"))
async def on_subscribe_start(callback: CallbackQuery) -> None:
    station_id = int(callback.data.split(":")[1])
    await callback.message.answer(
        "Какое топливо ждём?", reply_markup=kb.fuel_choice("subf", station_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("subf:"))
async def on_subscribe_fuel(callback: CallbackQuery) -> None:
    _, station_id, fuel = callback.data.split(":")
    user_id = await q.upsert_tg_user(callback.from_user.id)
    st = await q.station_by_id(int(station_id))
    created = await q.add_subscription(user_id, int(station_id), fuel)
    if created:
        await callback.message.answer(
            f"🔔 Слежу за {FUEL_LABELS[fuel]} на «{station_title(st)}». "
            "Как появится — сразу напишу!"
        )
    else:
        await callback.message.answer("Ты уже следишь за этим топливом здесь 😉")
    await callback.answer()


@router.callback_query(F.data.startswith("unsub:"))
async def on_unsubscribe(callback: CallbackQuery) -> None:
    sub_id = int(callback.data.split(":")[1])
    user_id = await q.upsert_tg_user(callback.from_user.id)
    await q.delete_subscription(sub_id, user_id)
    await callback.message.answer("Подписка удалена.")
    await callback.answer()
