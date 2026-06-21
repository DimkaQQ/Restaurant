import logging

import httpx
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.main import lang_keyboard, main_menu_keyboard, cities_keyboard, venues_keyboard
from bot.locales import t

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "lang_select")
async def show_lang_keyboard(callback: CallbackQuery, lang: str):
    await callback.message.edit_text(t('choose_lang', lang), reply_markup=lang_keyboard())


@router.callback_query(F.data.startswith("lang:"))
async def change_language(
    callback: CallbackQuery,
    guest: dict | None,
    api_url: str,
    lang: str,
):
    new_lang = callback.data.split(":", 1)[1]
    if new_lang not in ('ru', 'kz', 'en'):
        new_lang = 'ru'

    if guest:
        try:
            async with httpx.AsyncClient() as client:
                await client.patch(
                    f"{api_url}/api/bot/guest/{guest['telegram_id']}",
                    json={"language": new_lang},
                    timeout=5.0,
                )
        except Exception as e:
            logger.error("Language update error: %s", e)

    await callback.message.edit_text(
        t('lang_changed', new_lang),
        reply_markup=main_menu_keyboard(new_lang),
    )


@router.callback_query(F.data == "venue_select")
async def show_city_selection(
    callback: CallbackQuery,
    api_url: str,
    network_id: str,
    lang: str,
):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{api_url}/api/bot/venues",
                params={"network_id": network_id},
                timeout=5.0,
            )
            venues = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error("Venues fetch error: %s", e)
        venues = []

    if not venues:
        await callback.message.edit_text(t('no_venues', lang), reply_markup=venues_keyboard([], lang))
        return

    cities = list(dict.fromkeys(v.get('city') or '' for v in venues if v.get('city')))
    if not cities:
        await callback.message.edit_text(
            t('choose_venue', lang),
            reply_markup=venues_keyboard(venues, lang, prefix="venue_set"),
        )
        return

    await callback.message.edit_text(t('choose_city', lang), reply_markup=cities_keyboard(cities, lang))


@router.callback_query(F.data.startswith("city:"))
async def show_venues_in_city(
    callback: CallbackQuery,
    api_url: str,
    network_id: str,
    lang: str,
):
    city = callback.data.split(":", 1)[1]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{api_url}/api/bot/venues",
                params={"network_id": network_id},
                timeout=5.0,
            )
            venues = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error("Venues fetch error: %s", e)
        venues = []

    city_venues = [v for v in venues if v.get('city') == city]
    if not city_venues:
        await callback.message.edit_text(t('no_venues', lang), reply_markup=venues_keyboard([], lang))
        return

    await callback.message.edit_text(
        t('choose_venue', lang),
        reply_markup=venues_keyboard(city_venues, lang, prefix="venue_set"),
    )


@router.callback_query(F.data.startswith("venue_set:"))
async def set_preferred_venue(
    callback: CallbackQuery,
    guest: dict | None,
    api_url: str,
    network_id: str,
    lang: str,
):
    venue_id = callback.data.split(":", 1)[1]

    if not guest:
        await callback.answer(t('register_first', lang), show_alert=True)
        return

    venue_name = venue_id
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{api_url}/api/bot/venues",
                params={"network_id": network_id},
                timeout=5.0,
            )
            if resp.status_code == 200:
                venues = resp.json()
                found = next((v for v in venues if v['id'] == venue_id), None)
                if found:
                    venue_name = found['name']

            await client.patch(
                f"{api_url}/api/bot/guest/{guest['telegram_id']}",
                json={"preferred_venue_id": venue_id},
                timeout=5.0,
            )
    except Exception as e:
        logger.error("Set venue error: %s", e)

    await callback.message.edit_text(
        t('venue_changed', lang, name=venue_name),
        reply_markup=main_menu_keyboard(lang),
    )
