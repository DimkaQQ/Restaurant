import logging

import httpx
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.keyboards.main import lang_keyboard, main_menu_keyboard, phone_request_keyboard
from bot.locales import t

router = Router()
logger = logging.getLogger(__name__)


class RegistrationStates(StatesGroup):
    waiting_lang = State()
    waiting_name = State()
    waiting_phone = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, guest: dict | None, lang: str):
    if guest:
        await message.answer(
            t('welcome_back', lang, name=guest['name'] or 'гость', points=guest['total_points']),
            reply_markup=main_menu_keyboard(lang),
        )
    else:
        await message.answer(t('choose_lang', lang), reply_markup=lang_keyboard())
        await state.set_state(RegistrationStates.waiting_lang)


@router.callback_query(F.data.startswith("lang:"), RegistrationStates.waiting_lang)
async def process_lang_registration(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split(":", 1)[1]
    if lang not in ('ru', 'kz', 'en'):
        lang = 'ru'
    await state.update_data(lang=lang)
    await callback.message.edit_text(t('ask_name', lang))
    await state.set_state(RegistrationStates.waiting_name)


@router.message(RegistrationStates.waiting_name)
async def process_name(message: Message, state: FSMContext):
    if not message.text:
        data = await state.get_data()
        lang = data.get('lang', 'ru')
        await message.answer(t('ask_name', lang))
        return
    name = message.text.strip()
    await state.update_data(name=name)
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    await message.answer(t('ask_phone', lang), reply_markup=phone_request_keyboard(lang))
    await state.set_state(RegistrationStates.waiting_phone)


@router.message(RegistrationStates.waiting_phone, F.contact)
async def process_phone(
    message: Message,
    state: FSMContext,
    api_url: str,
    network_id: str,
):
    data = await state.get_data()
    name = data.get("name", message.from_user.full_name)
    phone = message.contact.phone_number
    lang = data.get('lang', 'ru')

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{api_url}/api/guests/",
                json={
                    "network_id": network_id,
                    "telegram_id": message.from_user.id,
                    "name": name,
                    "phone": phone,
                    "language": lang,
                },
                timeout=5.0,
            )
            guest = resp.json() if resp.status_code in (200, 201) else None
    except Exception as e:
        logger.error("Guest creation error: %s", e)
        guest = None

    await state.clear()
    await message.answer(
        t('reg_done', lang, name=name),
        reply_markup=main_menu_keyboard(lang),
    )


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery, guest: dict | None, lang: str):
    name = guest["name"] if guest else "гость"
    points = guest["total_points"] if guest else 0
    await callback.message.edit_text(
        t('welcome_back', lang, name=name, points=points),
        reply_markup=main_menu_keyboard(lang),
    )
