import logging

import httpx
from bot.http_client import bot_client
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.keyboards.main import lang_keyboard, main_menu_keyboard, phone_request_keyboard, staff_menu_keyboard
from bot.locales import t

router = Router()
logger = logging.getLogger(__name__)


class RegistrationStates(StatesGroup):
    waiting_lang = State()
    waiting_name = State()
    waiting_phone = State()


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    guest: dict | None,
    staff_user: dict | None,
    lang: str,
    api_url: str,
    network_id: str,
):
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""

    # Staff deeplink: /start link_TOKEN
    if args.startswith("link_"):
        token = args[5:]
        try:
            async with bot_client(timeout=5.0) as client:
                resp = await client.post(
                    f"{api_url}/api/bot/staff/link",
                    json={
                        "token": token,
                        "telegram_id": message.from_user.id,
                        "telegram_name": message.from_user.full_name,
                    },
                )
            if resp.status_code == 200:
                result = resp.json()
                await message.answer(
                    f"✅ Аккаунт сотрудника привязан!\n"
                    f"Роль: <b>{result['role']}</b>\n"
                    f"Email: {result['email']}\n\n"
                    f"Используйте /staff для меню сотрудника.",
                )
            else:
                err = resp.json().get("detail", "Ошибка")
                await message.answer(f"❌ {err}")
        except Exception as e:
            logger.error("Staff link error: %s", e)
            await message.answer("❌ Ошибка соединения")
        return

    # If staff user is already linked
    if staff_user:
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n"
            f"Вы вошли как сотрудник ({staff_user['role']}).",
            reply_markup=staff_menu_keyboard(lang),
        )
        return

    # Registered guest
    if guest:
        await state.clear()
        await message.answer(
            t('welcome_back', lang, name=guest['name'] or 'Гость', points=guest['total_points']),
            reply_markup=main_menu_keyboard(lang),
        )
        return

    # New user — start registration
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

    registered = False
    try:
        async with bot_client(timeout=5.0) as client:
            resp = await client.post(
                f"{api_url}/api/bot/guest",
                json={
                    "network_id": network_id,
                    "telegram_id": message.from_user.id,
                    "name": name,
                    "phone": phone,
                    "language": lang,
                },
            )
        registered = resp.status_code in (200, 201)
        if not registered:
            logger.error("Guest creation failed: %s", resp.text)
    except Exception as e:
        logger.error("Guest creation error: %s", e)

    if not registered:
        await message.answer(
            "❌ Произошла ошибка при регистрации. Попробуйте ещё раз — нажмите /start",
        )
        return

    await state.clear()
    await message.answer(
        t('reg_done', lang, name=name),
        reply_markup=main_menu_keyboard(lang),
    )


@router.callback_query(F.data == "back_main")
async def back_to_main(
    callback: CallbackQuery,
    state: FSMContext,
    guest: dict | None,
    staff_user: dict | None,
    lang: str,
):
    if staff_user:
        await callback.message.edit_text(
            f"👨‍💼 Меню сотрудника",
            reply_markup=staff_menu_keyboard(lang),
        )
        return

    name = (guest["name"] or "Гость") if guest else "Гость"
    points = guest["total_points"] if guest else 0
    await callback.message.edit_text(
        t('welcome_back', lang, name=name, points=points),
        reply_markup=main_menu_keyboard(lang),
    )
