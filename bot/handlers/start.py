import logging

import httpx
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.keyboards.main import main_menu_keyboard, phone_request_keyboard

router = Router()
logger = logging.getLogger(__name__)


class RegistrationStates(StatesGroup):
    waiting_name = State()
    waiting_phone = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, guest: dict | None, api_url: str, venue_id: str):
    if guest:
        rec_text = ""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{api_url}/api/guests/{guest['id']}/recommendation",
                    params={"venue_id": venue_id},
                    timeout=8.0,
                )
                if resp.status_code == 200:
                    rec_text = "\n\n" + resp.json().get("recommendation", "")
        except Exception as e:
            logger.warning("Could not get recommendation: %s", e)

        await message.answer(
            f"С возвращением, {guest['name'] or 'дорогой гость'}! 👋\n"
            f"У вас {guest['total_points']} баллов.{rec_text}",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            "Добро пожаловать! 🎉\nКак вас зовут?",
        )
        await state.set_state(RegistrationStates.waiting_name)


@router.message(RegistrationStates.waiting_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer(
        f"Отлично, {message.text.strip()}! Поделитесь вашим номером телефона:",
        reply_markup=phone_request_keyboard(),
    )
    await state.set_state(RegistrationStates.waiting_phone)


@router.message(RegistrationStates.waiting_phone, F.contact)
async def process_phone(message: Message, state: FSMContext, guest: dict | None, api_url: str, network_id: str, venue_id: str):
    data = await state.get_data()
    name = data.get("name", message.from_user.full_name)
    phone = message.contact.phone_number

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{api_url}/api/guests/",
                json={
                    "network_id": network_id,
                    "telegram_id": message.from_user.id,
                    "name": name,
                    "phone": phone,
                },
                timeout=5.0,
            )
            guest = resp.json() if resp.status_code in (200, 201) else None
    except Exception as e:
        logger.error("Guest creation error: %s", e)

    await state.clear()
    await message.answer(
        f"Добро пожаловать, {name}! 🎉\nВы зарегистрированы и получаете баллы за каждый заказ.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery, guest: dict | None):
    name = guest["name"] if guest else "гость"
    points = guest["total_points"] if guest else 0
    await callback.message.edit_text(
        f"Главное меню\nПривет, {name}! Ваши баллы: {points}",
        reply_markup=main_menu_keyboard(),
    )
