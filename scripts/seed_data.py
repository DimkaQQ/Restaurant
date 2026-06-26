"""
Seed: Chayla Group — 6 концепций, 14 активных + 3 в запуске.
  Чайла | Suli da Guli | Lukum Vostok | &milk | Usta | Joy (launch)

Usage:
  python scripts/seed_data.py           # пропустит если данные есть
  python scripts/seed_data.py --force   # перезаписать
"""
import asyncio
import os
import sys
import uuid
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import sqlalchemy as sa
from datetime import date, time
from sqlalchemy import select, delete, insert

from app.database import AsyncSessionLocal
from app.models.network import Network
from app.models.venue import Venue
from app.models.menu import MenuItem
from app.models.guest import Guest
from app.models.order import Order, OrderItem, Visit
from app.models.points import PointsTransaction
from app.models.staff import Staff
from app.models.review import Review
from app.models.inventory import Ingredient, WriteOff
from app.models.finance import Expense, EXPENSE_CATEGORIES
from app.models.shift import Shift


# ══════════════════════════════════════════════════════════════════════════════
# VENUES  (brand, name, address, city, is_active, daily_min, daily_max, avg_check)
# ══════════════════════════════════════════════════════════════════════════════
VENUES = [
    # ── Чайла — еда на каждый день в лаунж-пространстве ──────────────────────
    {"brand": "Чайла",         "name": "Чайла — Достык",         "address": "пр. Достык, 240",              "city": "Алматы",  "active": True,  "dmin": 65, "dmax": 120, "avg_check": 5200},
    {"brand": "Чайла",         "name": "Чайла — Жибек Жолы",     "address": "ул. Жибек Жолы, 115",          "city": "Алматы",  "active": True,  "dmin": 55, "dmax": 100, "avg_check": 4800},
    {"brand": "Чайла",         "name": "Чайла — Байзақов",       "address": "ул. Байзақов, 280",            "city": "Алматы",  "active": True,  "dmin": 45, "dmax": 85,  "avg_check": 4500},
    {"brand": "Чайла",         "name": "Чайла — Мега",           "address": "ТРЦ Мега, пр. Розы Багланова, 7", "city": "Алматы", "active": True, "dmin": 80, "dmax": 155, "avg_check": 4600},
    {"brand": "Чайла",         "name": "Чайла — Астана",         "address": "ул. Кабанбай батыра, 61",      "city": "Астана",  "active": True,  "dmin": 50, "dmax": 95,  "avg_check": 4900},

    # ── Suli da Guli — грузинская история ────────────────────────────────────
    {"brand": "Suli da Guli",  "name": "Suli da Guli — Гоголя",  "address": "ул. Гоголя, 20",               "city": "Алматы",  "active": True,  "dmin": 45, "dmax": 85,  "avg_check": 10500},
    {"brand": "Suli da Guli",  "name": "Suli da Guli — Тимирязева","address": "ул. Тимирязева, 42",          "city": "Алматы",  "active": True,  "dmin": 40, "dmax": 75,  "avg_check": 9800},
    {"brand": "Suli da Guli",  "name": "Suli da Guli — Астана",  "address": "ул. Туркестан, 2",             "city": "Астана",  "active": True,  "dmin": 40, "dmax": 78,  "avg_check": 10200},

    # ── Lukum Vostok — восточная кухня ───────────────────────────────────────
    {"brand": "Lukum Vostok",  "name": "Lukum Vostok — Казыбек Би","address": "ул. Казыбек Би, 48",         "city": "Алматы",  "active": True,  "dmin": 40, "dmax": 75,  "avg_check": 8200},
    {"brand": "Lukum Vostok",  "name": "Lukum Vostok — Достык",  "address": "пр. Достык, 162",              "city": "Алматы",  "active": True,  "dmin": 35, "dmax": 65,  "avg_check": 7800},

    # ── &milk — кофейня ──────────────────────────────────────────────────────
    {"brand": "&milk",         "name": "&milk — Esentai",         "address": "пр. Аль-Фараби, 77/8",         "city": "Алматы",  "active": True,  "dmin": 75, "dmax": 140, "avg_check": 3200},
    {"brand": "&milk",         "name": "&milk — Алмалы",          "address": "ул. Панфилова, 98",            "city": "Алматы",  "active": True,  "dmin": 60, "dmax": 110, "avg_check": 3000},

    # ── Usta — турецкая кухня ────────────────────────────────────────────────
    {"brand": "Usta",          "name": "Usta — Омаров",           "address": "ул. Омаров, 11",               "city": "Алматы",  "active": True,  "dmin": 40, "dmax": 80,  "avg_check": 9500},
    {"brand": "Usta",          "name": "Usta — Кунаева",          "address": "ул. Кунаева, 35",              "city": "Алматы",  "active": True,  "dmin": 35, "dmax": 70,  "avg_check": 9000},

    # ── Joy — well-being bistro (в запуске) ──────────────────────────────────
    {"brand": "Joy",           "name": "Joy — Достык",            "address": "пр. Достык, 295",              "city": "Алматы",  "active": False, "dmin": 0, "dmax": 0, "avg_check": 0},
    {"brand": "Joy",           "name": "Joy — Esentai",           "address": "пр. Аль-Фараби, 77/8",         "city": "Алматы",  "active": False, "dmin": 0, "dmax": 0, "avg_check": 0},
    {"brand": "Joy",           "name": "Joy — Астана",            "address": "пр. Туран, 22",                "city": "Астана",  "active": False, "dmin": 0, "dmax": 0, "avg_check": 0},
]

# ══════════════════════════════════════════════════════════════════════════════
# MENUS
# ══════════════════════════════════════════════════════════════════════════════
MENU_CHAYLA = [
    # Напитки
    {"name": "Чёрный чай (чайник)",      "cat": "Напитки",        "price": 800,  "w": 12},
    {"name": "Зелёный чай (чайник)",      "cat": "Напитки",        "price": 800,  "w": 10},
    {"name": "Чай с молоком",             "cat": "Напитки",        "price": 900,  "w": 11},
    {"name": "Шальчай",                   "cat": "Напитки",        "price": 1000, "w": 8},
    {"name": "Чай с чабрецом и мёдом",    "cat": "Напитки",        "price": 1100, "w": 6},
    {"name": "Матча латте",               "cat": "Напитки",        "price": 1500, "w": 5},
    {"name": "Капучино",                  "cat": "Напитки",        "price": 1400, "w": 9},
    {"name": "Латте",                     "cat": "Напитки",        "price": 1500, "w": 8},
    {"name": "Американо",                 "cat": "Напитки",        "price": 1000, "w": 7},
    {"name": "Какао",                     "cat": "Напитки",        "price": 1200, "w": 5},
    {"name": "Лимонад домашний",          "cat": "Напитки",        "price": 1300, "w": 6},
    # Завтраки
    {"name": "Каша молочная",             "cat": "Завтраки",       "price": 1200, "w": 5},
    {"name": "Яичница с овощами",         "cat": "Завтраки",       "price": 1500, "w": 6},
    {"name": "Омлет с сыром",             "cat": "Завтраки",       "price": 1600, "w": 5},
    {"name": "Авокадо тост",              "cat": "Завтраки",       "price": 2200, "w": 7},
    {"name": "Сырники со сметаной",       "cat": "Завтраки",       "price": 1800, "w": 6},
    {"name": "Блинчики с мёдом",          "cat": "Завтраки",       "price": 1700, "w": 5},
    # Выпечка
    {"name": "Самса с мясом",             "cat": "Выпечка",        "price": 600,  "w": 10},
    {"name": "Самса с тыквой",            "cat": "Выпечка",        "price": 550,  "w": 6},
    {"name": "Круассан масляный",         "cat": "Выпечка",        "price": 900,  "w": 8},
    {"name": "Круассан с шоколадом",      "cat": "Выпечка",        "price": 1000, "w": 6},
    {"name": "Булочка с корицей",         "cat": "Выпечка",        "price": 850,  "w": 7},
    {"name": "Лепёшка тандырная",         "cat": "Выпечка",        "price": 500,  "w": 9},
    {"name": "Баурсаки",                  "cat": "Выпечка",        "price": 700,  "w": 7},
    # Горячие блюда
    {"name": "Лагман",                    "cat": "Горячие блюда",  "price": 2800, "w": 9},
    {"name": "Манты (6 шт.)",            "cat": "Горячие блюда",  "price": 2500, "w": 10},
    {"name": "Плов по-узбекски",          "cat": "Горячие блюда",  "price": 2600, "w": 8},
    {"name": "Шурпа",                     "cat": "Горячие блюда",  "price": 2400, "w": 7},
    {"name": "Бешбармак",                 "cat": "Горячие блюда",  "price": 3500, "w": 6},
    # Десерты
    {"name": "Чизкейк классический",      "cat": "Десерты",        "price": 1600, "w": 8},
    {"name": "Медовик (кусок)",           "cat": "Десерты",        "price": 1400, "w": 7},
    {"name": "Тирамису",                  "cat": "Десерты",        "price": 1800, "w": 5},
    {"name": "Пахлава",                   "cat": "Десерты",        "price": 800,  "w": 6},
    {"name": "Шоколадный фондан",         "cat": "Десерты",        "price": 1900, "w": 5},
]

MENU_SULI = [
    {"name": "Хинкали с говядиной (5 шт.)",  "cat": "Хинкали",       "price": 2200, "w": 15},
    {"name": "Хинкали с грибами (5 шт.)",     "cat": "Хинкали",       "price": 2000, "w": 8},
    {"name": "Хинкали с сыром (5 шт.)",       "cat": "Хинкали",       "price": 2100, "w": 7},
    {"name": "Хачапури по-аджарски",          "cat": "Хачапури",      "price": 3500, "w": 12},
    {"name": "Хачапури по-мегрельски",        "cat": "Хачапури",      "price": 3200, "w": 9},
    {"name": "Хачапури по-имеретински",       "cat": "Хачапури",      "price": 2800, "w": 7},
    {"name": "Лобиани",                        "cat": "Хачапури",      "price": 2500, "w": 6},
    {"name": "Чкмерули (цыплёнок)",            "cat": "Горячее",       "price": 5200, "w": 8},
    {"name": "Чахохбили",                      "cat": "Горячее",       "price": 4500, "w": 7},
    {"name": "Сациви",                         "cat": "Горячее",       "price": 4200, "w": 6},
    {"name": "Шашлык из говядины",             "cat": "Шашлык",        "price": 4800, "w": 8},
    {"name": "Шашлык из баранины",             "cat": "Шашлык",        "price": 5500, "w": 6},
    {"name": "Мцвади (свинина)",               "cat": "Шашлык",        "price": 4500, "w": 7},
    {"name": "Харчо",                          "cat": "Супы",          "price": 2800, "w": 6},
    {"name": "Аджапсандал",                    "cat": "Закуски",       "price": 2200, "w": 6},
    {"name": "Пхали с орехами",                "cat": "Закуски",       "price": 1800, "w": 5},
    {"name": "Баклажаны с орехами",            "cat": "Закуски",       "price": 2000, "w": 6},
    {"name": "Грузинский зелёный салат",       "cat": "Салаты",        "price": 1900, "w": 5},
    {"name": "Вино Саперави (бокал)",          "cat": "Напитки",       "price": 2500, "w": 7},
    {"name": "Вино Ркацители (бокал)",         "cat": "Напитки",       "price": 2500, "w": 6},
    {"name": "Лимонад Тархун",                 "cat": "Напитки",       "price": 1200, "w": 8},
    {"name": "Чай по-грузински (чайник)",      "cat": "Напитки",       "price": 900,  "w": 7},
    {"name": "Чурчхела",                       "cat": "Десерты",       "price": 800,  "w": 5},
    {"name": "Пахлава грузинская",             "cat": "Десерты",       "price": 1000, "w": 4},
]

MENU_LUKUM = [
    {"name": "Манты с говядиной (6 шт.)", "cat": "Горячие блюда",  "price": 2800, "w": 10},
    {"name": "Манты с тыквой (6 шт.)",    "cat": "Горячие блюда",  "price": 2500, "w": 7},
    {"name": "Лагман",                     "cat": "Горячие блюда",  "price": 3200, "w": 9},
    {"name": "Плов по-фергански",          "cat": "Горячие блюда",  "price": 3000, "w": 8},
    {"name": "Шурпа",                      "cat": "Горячие блюда",  "price": 2800, "w": 7},
    {"name": "Дымляма",                    "cat": "Горячие блюда",  "price": 3500, "w": 6},
    {"name": "Кавурма",                    "cat": "Горячие блюда",  "price": 4200, "w": 5},
    {"name": "Шашлык из ягнёнка",         "cat": "Шашлык",         "price": 5200, "w": 7},
    {"name": "Самса с говядиной",          "cat": "Выпечка",        "price": 700,  "w": 9},
    {"name": "Самса с бараниной",          "cat": "Выпечка",        "price": 750,  "w": 6},
    {"name": "Лукум классический (200г)",  "cat": "Сладости",       "price": 1500, "w": 8},
    {"name": "Лукум с розой (200г)",       "cat": "Сладости",       "price": 1600, "w": 7},
    {"name": "Лукум с фисташкой (200г)",   "cat": "Сладости",       "price": 1800, "w": 6},
    {"name": "Пахлава (100г)",             "cat": "Сладости",       "price": 1200, "w": 7},
    {"name": "Чак-чак (100г)",             "cat": "Сладости",       "price": 1000, "w": 6},
    {"name": "Восточный чай с кардамоном", "cat": "Напитки",        "price": 900,  "w": 9},
    {"name": "Чай с шафраном",             "cat": "Напитки",        "price": 1100, "w": 7},
    {"name": "Кофе по-восточному",         "cat": "Напитки",        "price": 1200, "w": 6},
    {"name": "Айран",                      "cat": "Напитки",        "price": 700,  "w": 8},
    {"name": "Клубничный щербет",          "cat": "Напитки",        "price": 1300, "w": 5},
]

MENU_MILK = [
    {"name": "Эспрессо",                   "cat": "Кофе",           "price": 900,  "w": 8},
    {"name": "Американо",                  "cat": "Кофе",           "price": 1000, "w": 9},
    {"name": "Капучино",                   "cat": "Кофе",           "price": 1400, "w": 13},
    {"name": "Флэт Уайт",                  "cat": "Кофе",           "price": 1500, "w": 11},
    {"name": "Кортадо",                    "cat": "Кофе",           "price": 1500, "w": 8},
    {"name": "Латте",                      "cat": "Кофе",           "price": 1500, "w": 12},
    {"name": "Раф кофе",                   "cat": "Кофе",           "price": 1700, "w": 7},
    {"name": "Овсяный латте",              "cat": "Кофе",           "price": 1800, "w": 8},
    {"name": "Матча латте",                "cat": "Напитки",        "price": 1700, "w": 10},
    {"name": "Золотое молоко",             "cat": "Напитки",        "price": 1500, "w": 6},
    {"name": "Смузи Клубника",             "cat": "Напитки",        "price": 1800, "w": 7},
    {"name": "Смузи Манго-Авокадо",        "cat": "Напитки",        "price": 1900, "w": 6},
    {"name": "Лимонад Базилик",            "cat": "Напитки",        "price": 1300, "w": 5},
    {"name": "Авокадо тост с яйцом пашот", "cat": "Еда",            "price": 2500, "w": 9},
    {"name": "Клаб-сэндвич",               "cat": "Еда",            "price": 2800, "w": 7},
    {"name": "Боул с гранолой",            "cat": "Еда",            "price": 2000, "w": 7},
    {"name": "Чиа-пудинг",                 "cat": "Еда",            "price": 1400, "w": 5},
    {"name": "Салат Цезарь",               "cat": "Еда",            "price": 2400, "w": 6},
    {"name": "Яйца Бенедикт",             "cat": "Еда",            "price": 2600, "w": 6},
    {"name": "Круассан масляный",          "cat": "Выпечка",        "price": 900,  "w": 10},
    {"name": "Круассан Ветчина & Сыр",     "cat": "Выпечка",        "price": 1200, "w": 8},
    {"name": "Брауни",                     "cat": "Выпечка",        "price": 1000, "w": 7},
    {"name": "Чизкейк",                    "cat": "Выпечка",        "price": 1600, "w": 6},
    {"name": "Печенье (2 шт.)",            "cat": "Выпечка",        "price": 700,  "w": 6},
]

MENU_USTA = [
    {"name": "Дёнер кебаб",               "cat": "Кебаб",          "price": 2800, "w": 12},
    {"name": "Шиш-кебаб из говядины",     "cat": "Кебаб",          "price": 4800, "w": 9},
    {"name": "Адана-кебаб",               "cat": "Кебаб",          "price": 4500, "w": 8},
    {"name": "Кюфте",                     "cat": "Кебаб",          "price": 4200, "w": 7},
    {"name": "Лахмаджун",                 "cat": "Пиде & Лахмаджун","price": 2200, "w": 8},
    {"name": "Пиде с фаршем",             "cat": "Пиде & Лахмаджун","price": 3200, "w": 7},
    {"name": "Пиде с мясом и овощами",    "cat": "Пиде & Лахмаджун","price": 3500, "w": 6},
    {"name": "Чечевичный суп",            "cat": "Супы",           "price": 1800, "w": 7},
    {"name": "Суп Яйла",                  "cat": "Супы",           "price": 2000, "w": 5},
    {"name": "Мезе ассорти",              "cat": "Закуски",        "price": 3200, "w": 6},
    {"name": "Баклажаны по-стамбульски",  "cat": "Закуски",        "price": 2800, "w": 5},
    {"name": "Турецкий салат Чобан",      "cat": "Салаты",         "price": 2000, "w": 6},
    {"name": "Баклава по-турецки",        "cat": "Десерты",        "price": 1200, "w": 8},
    {"name": "Кюнефе",                    "cat": "Десерты",        "price": 2200, "w": 6},
    {"name": "Тулумба",                   "cat": "Десерты",        "price": 1200, "w": 5},
    {"name": "Кофе по-турецки",           "cat": "Напитки",        "price": 1000, "w": 9},
    {"name": "Чай по-турецки (чайдан)",   "cat": "Напитки",        "price": 800,  "w": 10},
    {"name": "Айран",                     "cat": "Напитки",        "price": 700,  "w": 8},
    {"name": "Şalgam суджук",             "cat": "Напитки",        "price": 900,  "w": 4},
]

MENU_JOY = [
    {"name": "Смузи-боул Асаи",           "cat": "Боулы",          "price": 2800, "w": 8},
    {"name": "Боул Buddha",               "cat": "Боулы",          "price": 3200, "w": 7},
    {"name": "Зелёный смузи",             "cat": "Напитки",        "price": 1800, "w": 8},
    {"name": "Матча-латте",               "cat": "Напитки",        "price": 1700, "w": 9},
    {"name": "Куркума-латте",             "cat": "Напитки",        "price": 1500, "w": 7},
    {"name": "Авокадо тост с микрозеленью","cat": "Еда",           "price": 2500, "w": 8},
    {"name": "Яйца Бенедикт на спельте",  "cat": "Еда",           "price": 2800, "w": 6},
    {"name": "Гранола с суперфудами",     "cat": "Еда",            "price": 1900, "w": 6},
    {"name": "Чиа-пудинг",               "cat": "Еда",            "price": 1600, "w": 5},
    {"name": "Детокс-напиток",            "cat": "Напитки",        "price": 1600, "w": 5},
]

MENU_BY_BRAND = {
    "Чайла": MENU_CHAYLA,
    "Suli da Guli": MENU_SULI,
    "Lukum Vostok": MENU_LUKUM,
    "&milk": MENU_MILK,
    "Usta": MENU_USTA,
    "Joy": MENU_JOY,
}

# ══════════════════════════════════════════════════════════════════════════════
# GUESTS — 1000 человек
# ══════════════════════════════════════════════════════════════════════════════
GUEST_FEMALE_FIRST = [
    "Алия","Айгерим","Динара","Гульназ","Зарина","Камила","Бота","Сауле","Нагима","Аида",
    "Асель","Жания","Малика","Ксения","Ирина","Анна","Мария","Наталья","Екатерина","Дарья",
    "Алина","Юлия","Кристина","Меруерт","Айнур","Назгуль","Жанар","Гульмира","Арайлым",
]
GUEST_MALE_FIRST = [
    "Марат","Нурлан","Руслан","Ержан","Асхат","Тимур","Данияр","Бауыржан","Ринат","Алибек",
    "Сейткали","Болат","Санжар","Максат","Берик","Талгат","Олжас","Аманжол","Дулат","Аскар",
    "Рустем","Виктор","Александр","Сергей","Дмитрий","Андрей","Иван","Артём","Никита",
    "Азамат","Еркин","Нурсултан","Арман","Куаныш","Жасулан","Серик","Бек","Мирас",
]
GUEST_FEMALE_LAST = [
    "Ахметова","Касымова","Тулегенова","Абдрахманова","Сейтханова","Досмагамбетова",
    "Байжанова","Жаксыбекова","Нурмаганбетова","Сулейменова","Абенова","Байдаулетова",
    "Ибрагимова","Хасанова","Назарова","Каримова","Рахимова","Юсупова","Матвеева","Соколова",
    "Новикова","Попова","Лебедева","Козлова","Николаева","Семёнова","Голубева","Виноградова",
    "Кузнецова","Смирнова","Иванова","Васильева","Тоқаева","Нурбекова","Жұмабекова","Есенова",
    "Маратова","Ахметова","Қасымова","Бекенова","Орынбасарова","Дюсебаева","Петрова","Ким",
]
GUEST_MALE_LAST = [
    "Джаксыбеков","Бейсенов","Омаров","Сагинтаев","Байжанов","Мусаев","Ким",
    "Жаксыбеков","Нурмаганбетов","Сулейменов","Абенов","Байдаулетов",
    "Ибрагимов","Хасанов","Назаров","Каримов","Рахимов","Юсупов","Матвеев","Соколов",
    "Новиков","Попов","Лебедев","Козлов","Николаев","Семёнов","Голубев","Виноградов",
    "Кузнецов","Смирнов","Иванов","Васильев","Тоқаев","Нурбеков","Жұмабеков","Есенов",
    "Маратов","Ахметов","Қасымов","Бекенов","Орынбасаров","Дюсебаев","Петров","Сейткали",
]
PHONE_PFXS = ["+7 701","+7 702","+7 705","+7 707","+7 747","+7 771","+7 777","+7 778"]


def rand_phone():
    return f"{random.choice(PHONE_PFXS)} {random.randint(100,999)} {random.randint(1000,9999)}"


async def main():
    force = "--force" in sys.argv

    async with AsyncSessionLocal() as db:
        network = (await db.execute(select(Network))).scalars().first()
        if not network:
            print("❌ Нет сети. Сначала: make setup")
            return
        print(f"✅ Сеть: {network.name} — Chayla Group")

        existing = (await db.execute(
            select(Venue).where(Venue.network_id == network.id)
        )).scalars().first()

        if existing and not force:
            print("⚠️  Данные уже есть. Для перезаписи: make reseed")
            return

        if existing and force:
            print("   Очищаем старые данные...")
            await db.execute(sa.text("UPDATE users SET venue_id = NULL"))
            await db.execute(sa.text(
                "TRUNCATE shifts, writeoffs, ingredients, expenses, "
                "reviews, visits, points_transactions, order_items, orders, "
                "menu_items, staff, guests RESTART IDENTITY CASCADE"
            ))
            await db.execute(sa.text("DELETE FROM venues"))
            await db.commit()
            print("   ✓ Очищено")

        # Rename network to demo name so real client data is not exposed
        await db.execute(
            sa.update(Network)
            .where(Network.id == network.id)
            .values(name="Chayla Group", slug="chayla")
        )
        await db.commit()
        print("   ✓ Сеть переименована в «Chayla Group»")

        # ── 1. Venues ────────────────────────────────────────────────────────
        venue_rows = []
        venue_meta = []
        for v in VENUES:
            vid = uuid.uuid4()
            venue_rows.append({
                "id": vid,
                "network_id": network.id,
                "name": v["name"],
                "address": f"г. {v['city']}, {v['address']}",
                "is_active": v["active"],
                "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(200, 600)),
            })
            venue_meta.append({**v, "id": vid})
        await db.execute(insert(Venue), venue_rows)
        await db.flush()
        active_count = sum(1 for v in VENUES if v["active"])
        launch_count = sum(1 for v in VENUES if not v["active"])
        print(f"   + {active_count} активных заведений, {launch_count} в запуске")

        # ── 2. Menu items ─────────────────────────────────────────────────────
        menu_rows = []
        venue_menu: dict[uuid.UUID, list] = {}
        for vm in venue_meta:
            items_def = MENU_BY_BRAND[vm["brand"]]
            items = []
            for m in items_def:
                mid = uuid.uuid4()
                menu_rows.append({
                    "id": mid,
                    "venue_id": vm["id"],
                    "name": m["name"],
                    "category": m["cat"],
                    "price": Decimal(str(m["price"])),
                    "description": None,
                    "is_available": True,
                })
                items.append({"id": mid, "name": m["name"], "price": m["price"], "w": m["w"]})
            venue_menu[vm["id"]] = items
        await db.execute(insert(MenuItem), menu_rows)
        await db.flush()
        print(f"   + {len(menu_rows)} позиций меню")

        # ── 3. Guests ─────────────────────────────────────────────────────────
        GUEST_COUNT = 1000
        guest_rows = []
        guest_ids = []
        for _ in range(GUEST_COUNT):
            gid = uuid.uuid4()
            guest_rows.append({
                "id": gid,
                "network_id": network.id,
                "name": (lambda g: f"{random.choice(GUEST_FEMALE_FIRST)} {random.choice(GUEST_FEMALE_LAST)}" if g == "f" else f"{random.choice(GUEST_MALE_FIRST)} {random.choice(GUEST_MALE_LAST)}")(random.choice(["f","f","m","m","m"])),
                "phone": rand_phone(),
                "telegram_id": None,
                "total_points": 0,
                "total_visits": 0,
                "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 500)),
            })
            guest_ids.append(gid)
        await db.execute(insert(Guest), guest_rows)
        await db.flush()
        print(f"   + {GUEST_COUNT} гостей")

        # ── 4. Orders (90 дней истории + сегодня) ─────────────────────────────
        HIST_STATUSES = ["done"] * 9 + ["cancelled"]
        LIVE_STATUSES = ["new", "new", "new", "confirmed", "preparing", "preparing", "ready"]

        order_rows = []
        item_rows = []
        visit_rows = []
        guest_visits = {g: 0 for g in guest_ids}
        guest_points = {g: 0 for g in guest_ids}

        for vm in venue_meta:
            if not vm["active"]:
                continue
            items = venue_menu[vm["id"]]
            weights = [i["w"] for i in items]
            now = datetime.now(timezone.utc)

            # History: 90 days
            for day in range(1, 91):
                day_ts = now - timedelta(days=day)
                n = random.randint(vm["dmin"], vm["dmax"])
                # weekends ~30% busier
                if day_ts.weekday() >= 5:
                    n = int(n * 1.3)

                for _ in range(n):
                    oid = uuid.uuid4()
                    gid = random.choice(guest_ids)
                    status = random.choice(HIST_STATUSES)
                    n_items = random.choices([1, 2, 3, 4, 5], weights=[15, 35, 30, 15, 5])[0]
                    chosen = random.choices(items, weights=weights, k=n_items)

                    total = 0.0
                    seen = {}
                    for mi in chosen:
                        seen[mi["id"]] = seen.get(mi["id"], 0) + 1
                    for mi_id, qty in seen.items():
                        mi = next(x for x in items if x["id"] == mi_id)
                        total += mi["price"] * qty
                        item_rows.append({
                            "id": uuid.uuid4(),
                            "order_id": oid,
                            "menu_item_id": mi_id,
                            "name": mi["name"],
                            "price": Decimal(str(mi["price"])),
                            "quantity": qty,
                        })

                    order_dt = day_ts.replace(
                        hour=random.randint(9, 22),
                        minute=random.randint(0, 59),
                        second=random.randint(0, 59),
                        microsecond=0,
                    )
                    pts = int(total // 1000) * 10 if status == "done" else 0
                    order_rows.append({
                        "id": oid,
                        "venue_id": vm["id"],
                        "guest_id": gid,
                        "status": status,
                        "total_amount": Decimal(str(round(total, 2))),
                        "points_earned": pts,
                        "notes": None,
                        "created_at": order_dt,
                        "updated_at": order_dt,
                    })

                    if status == "done":
                        visit_rows.append({
                            "id": uuid.uuid4(),
                            "guest_id": gid,
                            "venue_id": vm["id"],
                            "order_id": oid,
                            "visited_at": order_dt,
                        })
                        guest_visits[gid] += 1
                        guest_points[gid] += pts

            # Live orders (today)
            n_live = random.randint(vm["dmin"] // 6, vm["dmax"] // 5)
            for _ in range(max(n_live, 4)):
                oid = uuid.uuid4()
                gid = random.choice(guest_ids)
                n_items = random.choices([1, 2, 3], weights=[25, 50, 25])[0]
                chosen = random.choices(items, weights=weights, k=n_items)

                total = 0.0
                seen = {}
                for mi in chosen:
                    seen[mi["id"]] = seen.get(mi["id"], 0) + 1
                for mi_id, qty in seen.items():
                    mi = next(x for x in items if x["id"] == mi_id)
                    total += mi["price"] * qty
                    item_rows.append({
                        "id": uuid.uuid4(),
                        "order_id": oid,
                        "menu_item_id": mi_id,
                        "name": mi["name"],
                        "price": Decimal(str(mi["price"])),
                        "quantity": qty,
                    })

                order_rows.append({
                    "id": oid,
                    "venue_id": vm["id"],
                    "guest_id": gid,
                    "status": random.choice(LIVE_STATUSES),
                    "total_amount": Decimal(str(round(total, 2))),
                    "points_earned": 0,
                    "notes": None,
                    "created_at": now - timedelta(minutes=random.randint(3, 120)),
                    "updated_at": now - timedelta(minutes=random.randint(0, 10)),
                })

        # Bulk insert in batches
        BATCH = 2000
        print(f"   Вставляем {len(order_rows):,} заказов...")
        for i in range(0, len(order_rows), BATCH):
            await db.execute(insert(Order), order_rows[i:i+BATCH])
        await db.flush()

        print(f"   Вставляем {len(item_rows):,} позиций заказов...")
        for i in range(0, len(item_rows), BATCH):
            await db.execute(insert(OrderItem), item_rows[i:i+BATCH])
        await db.flush()

        for i in range(0, len(visit_rows), BATCH):
            await db.execute(insert(Visit), visit_rows[i:i+BATCH])
        await db.flush()

        # Update guest totals
        update_rows = [
            {"id": g, "total_visits": guest_visits[g], "total_points": guest_points[g]}
            for g in guest_ids if guest_visits[g] > 0
        ]
        for row in update_rows:
            await db.execute(
                sa.update(Guest)
                .where(Guest.id == row["id"])
                .values(total_visits=row["total_visits"], total_points=row["total_points"])
            )

        await db.commit()

        live = sum(1 for o in order_rows if o["status"] in ("new","confirmed","preparing","ready"))
        total_rev = sum(float(o["total_amount"]) for o in order_rows if o["status"] == "done")
        print(f"   + {len(order_rows):,} заказов ({live} активных сегодня)")
        print(f"   + {len(visit_rows):,} визитов")

        # ── 5. Staff ─────────────────────────────────────────────────────────
        STAFF_BY_BRAND = {
            "Чайла":       [("waiter",4),("waiter",4),("senior_waiter",2),("manager",1),("barista",1)],
            "Suli da Guli":[("waiter",4),("waiter",3),("senior_waiter",2),("manager",1),("hostess",1)],
            "Lukum Vostok":[("waiter",4),("waiter",3),("senior_waiter",2),("manager",1),("bartender",1)],
            "&milk":       [("barista",3),("barista",2),("senior_waiter",1),("manager",1)],
            "Usta":        [("waiter",4),("waiter",3),("senior_waiter",1),("manager",1),("bartender",1)],
            "Joy":         [("waiter",2),("barista",2),("manager",1)],
        }
        STAFF_FEMALE_FIRST = [
            "Алия","Айгерим","Динара","Камила","Асель","Жания","Малика","Анна","Мария","Дарья",
            "Алина","Меруерт","Назгуль","Гульмира","Арайлым","Айнур","Зарина","Гульназ","Сауле",
        ]
        STAFF_MALE_FIRST = [
            "Руслан","Тимур","Алибек","Берик","Олжас","Аскар","Виктор","Александр","Артём",
            "Азамат","Нурсултан","Арман","Мирас","Данияр","Бауыржан","Ержан","Максат","Санжар",
        ]
        STAFF_FEMALE_LAST = [
            "Ахметова","Касымова","Тулегенова","Петрова","Новикова","Козлова","Сулейменова",
            "Матвеева","Соколова","Бекенова","Маратова","Есенова","Иванова","Кузнецова",
            "Жаксыбекова","Омарова","Мусаева","Бейсенова","Ким","Сейткали",
        ]
        STAFF_MALE_LAST = [
            "Ахметов","Бейсенов","Омаров","Мусаев","Сулейменов","Матвеев","Соколов","Новиков",
            "Козлов","Кузнецов","Смирнов","Иванов","Бекенов","Маратов","Есенов","Джаксыбеков",
            "Жаксыбеков","Ким","Сейткали","Попов","Николаев","Семёнов",
        ]

        staff_rows = []
        venue_staff: dict[uuid.UUID, list[uuid.UUID]] = {}
        for vm in venue_meta:
            if not vm["active"]:
                continue
            roles_def = STAFF_BY_BRAND.get(vm["brand"], [("waiter",3),("manager",1)])
            sids = []
            for role, count in roles_def:
                for _ in range(count):
                    sid = uuid.uuid4()
                    staff_rows.append({
                        "id": sid,
                        "network_id": network.id,
                        "venue_id": vm["id"],
                        "name": (lambda g: f"{random.choice(STAFF_FEMALE_FIRST)} {random.choice(STAFF_FEMALE_LAST)}" if g == "f" else f"{random.choice(STAFF_MALE_FIRST)} {random.choice(STAFF_MALE_LAST)}")(random.choice(["f","f","m","m","m"])),
                        "role": role,
                        "is_active": True,
                        "avg_rating": None,
                        "total_reviews": 0,
                        "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(30, 400)),
                    })
                    sids.append(sid)
            venue_staff[vm["id"]] = sids
        await db.execute(insert(Staff), staff_rows)
        await db.flush()
        print(f"   + {len(staff_rows)} сотрудников")

        # ── 6. Reviews (for ~35% of done orders) ─────────────────────────────
        COMMENTS_POSITIVE = [
            "Всё понравилось, очень вкусно!",
            "Отличный сервис, приятная атмосфера.",
            "Вернёмся ещё, спасибо!",
            "Быстро и вкусно, рекомендую.",
            "Официант был очень внимательным.",
            "Прекрасный вечер в хорошей компании.",
            "Всё на высшем уровне!",
            "Порции большие, цены приятные.",
            "Чудесная еда и обслуживание.",
            "Очень доброжелательный персонал.",
        ]
        COMMENTS_NEUTRAL = [
            "В целом нормально, но можно лучше.",
            "Еда хорошая, ждали немного долго.",
            "Приятное место, но шумновато.",
            "Средне, без особых впечатлений.",
            "Еда вкусная, сервис мог бы быть быстрее.",
        ]
        COMMENTS_NEGATIVE = [
            "Долго ждали заказ.",
            "Официант был невнимательным.",
            "Блюдо не соответствовало описанию.",
            "Ожидал большего за такие деньги.",
        ]

        # collect done order ids per venue
        done_orders_by_venue: dict[uuid.UUID, list] = {}
        for o in order_rows:
            if o["status"] == "done":
                vid = o["venue_id"]
                if vid not in done_orders_by_venue:
                    done_orders_by_venue[vid] = []
                done_orders_by_venue[vid].append(o)

        review_rows = []
        staff_rating_sum: dict[uuid.UUID, float] = {}
        staff_review_count: dict[uuid.UUID, int] = {}

        for vm in venue_meta:
            if not vm["active"]:
                continue
            done_ords = done_orders_by_venue.get(vm["id"], [])
            sids = venue_staff.get(vm["id"], [])
            if not sids:
                continue
            waiter_ids = [
                s["id"] for s in staff_rows
                if s["venue_id"] == vm["id"] and s["role"] in ("waiter","senior_waiter","barista","hostess")
            ]
            if not waiter_ids:
                waiter_ids = sids

            for o in done_ords:
                if random.random() > 0.35:
                    continue
                overall = random.choices([5,4,4,3,2], weights=[40,30,15,10,5])[0]
                food_r = max(1, overall + random.randint(-1, 1))
                service_r = max(1, overall + random.randint(-1, 1))
                food_r = min(5, food_r)
                service_r = min(5, service_r)
                staff_id = random.choice(waiter_ids)

                if overall >= 4:
                    comment = random.choice(COMMENTS_POSITIVE) if random.random() < 0.6 else None
                elif overall == 3:
                    comment = random.choice(COMMENTS_NEUTRAL) if random.random() < 0.4 else None
                else:
                    comment = random.choice(COMMENTS_NEGATIVE) if random.random() < 0.5 else None

                review_rows.append({
                    "id": uuid.uuid4(),
                    "venue_id": vm["id"],
                    "order_id": o["id"],
                    "guest_id": o["guest_id"],
                    "staff_id": staff_id,
                    "food_rating": food_r,
                    "service_rating": service_r,
                    "overall_rating": overall,
                    "comment": comment,
                    "source": "bot",
                    "created_at": o["created_at"],
                })

                staff_rating_sum[staff_id] = staff_rating_sum.get(staff_id, 0.0) + overall
                staff_review_count[staff_id] = staff_review_count.get(staff_id, 0) + 1

        print(f"   Вставляем {len(review_rows):,} отзывов...")
        for i in range(0, len(review_rows), BATCH):
            await db.execute(insert(Review), review_rows[i:i+BATCH])
        await db.flush()

        # Update staff avg_rating and total_reviews
        for s in staff_rows:
            sid = s["id"]
            cnt = staff_review_count.get(sid, 0)
            if cnt > 0:
                avg = staff_rating_sum[sid] / cnt
                await db.execute(
                    sa.update(Staff)
                    .where(Staff.id == sid)
                    .values(avg_rating=round(avg, 2), total_reviews=cnt)
                )

        await db.commit()

        # ── 7. Ingredients (склад) ────────────────────────────────────────────
        INGREDIENTS_BASE = [
            # name, unit, qty, min_qty, cost
            ("Мука пшеничная",    "кг",   50.0,  10.0,  250),
            ("Сахар",             "кг",   30.0,   5.0,  200),
            ("Соль",              "кг",   15.0,   3.0,   80),
            ("Масло подсолнечное","л",    20.0,   5.0,  600),
            ("Масло сливочное",   "кг",   10.0,   2.0, 2200),
            ("Яйца",              "шт",  200.0,  50.0,   55),
            ("Молоко",            "л",    40.0,  10.0,  350),
            ("Сливки 33%",        "л",    15.0,   3.0,  900),
            ("Сыр твёрдый",       "кг",    8.0,   2.0, 3500),
            ("Лук репчатый",      "кг",   20.0,   5.0,  150),
            ("Морковь",           "кг",   15.0,   3.0,  120),
            ("Помидоры",          "кг",   10.0,   3.0,  450),
            ("Огурцы",            "кг",    8.0,   2.0,  350),
            ("Картофель",         "кг",   30.0,   8.0,  120),
            ("Чеснок",            "кг",    3.0,   1.0,  800),
            ("Зелень (пучок)",    "шт",   20.0,   5.0,  150),
            ("Перец чёрный",      "кг",    1.0,  0.2, 2500),
            ("Чай (листовой)",    "кг",    5.0,   1.0, 1800),
            ("Кофе в зёрнах",     "кг",    8.0,   2.0, 6500),
            ("Сахар тростниковый","кг",    5.0,   1.0,  450),
        ]
        INGREDIENTS_BRAND = {
            "Чайла": [
                ("Говядина (фарш)",   "кг",   15.0,  3.0, 3200),
                ("Баранина",          "кг",    8.0,  2.0, 4500),
                ("Рис",               "кг",   25.0,  5.0,  350),
                ("Тыква",             "кг",   10.0,  2.0,  200),
                ("Кефир",             "л",     8.0,  2.0,  320),
                ("Творог",            "кг",    5.0,  1.0, 1200),
            ],
            "Suli da Guli": [
                ("Говядина (вырезка)", "кг",  12.0,  3.0, 5500),
                ("Свинина",           "кг",    8.0,  2.0, 3200),
                ("Сулугуни",          "кг",   10.0,  2.0, 4200),
                ("Вино красное (бутыль)","л",  20.0,  5.0, 1800),
                ("Вино белое (бутыль)","л",   15.0,  3.0, 1600),
                ("Кинза",             "кг",    2.0, 0.5,  800),
                ("Грецкий орех",      "кг",    3.0,  1.0, 2800),
                ("Аджика",            "кг",    2.0, 0.5, 1500),
            ],
            "Lukum Vostok": [
                ("Баранина (на кости)","кг",  10.0,  3.0, 4200),
                ("Нут",               "кг",    5.0,  1.0,  600),
                ("Кунжут",            "кг",    2.0, 0.5, 1800),
                ("Лукум (полуфабрикат)","кг", 10.0,  2.0, 3500),
                ("Фисташки",          "кг",    2.0, 0.5, 8500),
                ("Рисовый крахмал",   "кг",    3.0,  1.0,  700),
                ("Розовая вода",      "л",     2.0, 0.5, 1200),
            ],
            "&milk": [
                ("Кофе спешелти",     "кг",   10.0,  2.0, 9500),
                ("Молоко овсяное",    "л",    20.0,  5.0,  650),
                ("Молоко миндальное", "л",    10.0,  2.0,  850),
                ("Авокадо",           "шт",   30.0, 10.0,  600),
                ("Хлеб (буханка)",    "шт",   15.0,  5.0,  400),
                ("Сироп ванильный",   "л",     3.0,  1.0, 1500),
                ("Матча (порошок)",   "кг",    1.0, 0.2,12000),
            ],
            "Usta": [
                ("Говядина (фарш)",   "кг",   12.0,  3.0, 3200),
                ("Баранина",          "кг",   10.0,  3.0, 4500),
                ("Лаваш (листы)",     "шт",   50.0, 10.0,  120),
                ("Томатная паста",    "кг",    5.0,  1.0,  600),
                ("Петрушка",          "кг",    2.0, 0.5,  700),
                ("Перец красный",     "кг",    1.5, 0.3, 1200),
                ("Чечевица красная",  "кг",    8.0,  2.0,  450),
            ],
            "Joy": [
                ("Авокадо",           "шт",   20.0,  5.0,  600),
                ("Чиа семена",        "кг",    2.0, 0.5, 3500),
                ("Ягоды асаи (заморож.)","кг", 5.0, 1.0, 4500),
                ("Кокосовое молоко",  "л",     8.0,  2.0, 1200),
                ("Мёд натуральный",   "кг",    3.0,  1.0, 2500),
                ("Гранола",           "кг",    5.0,  1.0, 1800),
                ("Шпинат",            "кг",    3.0,  1.0,  600),
            ],
        }

        # Bar-specific ingredients (category="bar") for venues with bartenders
        BAR_INGREDIENTS_BASE = [
            ("Водка",              "л",    10.0,  2.0, 4500),
            ("Виски",              "л",     8.0,  1.5, 8500),
            ("Ром тёмный",         "л",     5.0,  1.0, 6500),
            ("Джин",               "л",     5.0,  1.0, 7000),
            ("Тоник (бутылка)",    "шт",   48.0, 12.0,  350),
            ("Сок апельсиновый",   "л",    15.0,  4.0,  600),
            ("Сок томатный",       "л",    10.0,  3.0,  550),
            ("Лайм",               "кг",    5.0,  1.5,  900),
            ("Мята свежая",        "шт",   20.0,  5.0,  250),
            ("Сироп сахарный",     "л",     5.0,  1.0,  800),
            ("Биттер Ангостура",   "мл",  200.0, 50.0, 3200),
            ("Кола (бутылка)",     "шт",   48.0, 12.0,  280),
        ]
        BAR_INGREDIENTS_BRAND = {
            "Suli da Guli": [
                ("Чача",           "л",     4.0,  1.0, 5500),
                ("Вермут красный", "л",     3.0,  0.5, 3800),
                ("Вермут белый",   "л",     3.0,  0.5, 3500),
            ],
            "Lukum Vostok": [
                ("Арак",           "л",     3.0,  0.5, 4200),
                ("Айран (бутылка)","шт",   24.0,  6.0,  300),
                ("Гранатовый сок", "л",     8.0,  2.0,  750),
            ],
            "Usta": [
                ("Пиво разливное", "л",    50.0, 10.0,  850),
                ("Квас",           "л",    20.0,  5.0,  400),
            ],
        }
        # brands that have a bar
        BAR_BRANDS = {"Suli da Guli", "Lukum Vostok", "Usta"}

        ingredient_rows = []
        writeoff_rows = []
        venue_ingredient_ids: dict[uuid.UUID, list[uuid.UUID]] = {}

        for vm in venue_meta:
            if not vm["active"]:
                continue
            brand_specific = INGREDIENTS_BRAND.get(vm["brand"], [])
            # kitchen ingredients
            all_ing = [(name, unit, qty, min_qty, cost, "kitchen")
                       for name, unit, qty, min_qty, cost in INGREDIENTS_BASE + brand_specific]
            # bar ingredients for applicable brands
            if vm["brand"] in BAR_BRANDS:
                bar_base = BAR_INGREDIENTS_BASE
                bar_brand = BAR_INGREDIENTS_BRAND.get(vm["brand"], [])
                all_ing += [(name, unit, qty, min_qty, cost, "bar")
                            for name, unit, qty, min_qty, cost in bar_base + bar_brand]
            iids = []
            for name, unit, qty, min_qty, cost, category in all_ing:
                # randomize quantities a bit
                actual_qty = round(qty * random.uniform(0.3, 1.8), 1)
                iid = uuid.uuid4()
                ingredient_rows.append({
                    "id": iid,
                    "network_id": network.id,
                    "venue_id": vm["id"],
                    "name": name,
                    "unit": unit,
                    "quantity": Decimal(str(actual_qty)),
                    "min_quantity": Decimal(str(min_qty)),
                    "cost_per_unit": Decimal(str(cost)),
                    "category": category,
                    "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(30, 180)),
                })
                iids.append(iid)

                # seed a few writeoffs per ingredient
                n_writeoffs = random.randint(1, 4)
                for _ in range(n_writeoffs):
                    wo_qty = round(random.uniform(0.5, min(qty * 0.3, actual_qty * 0.4 + 0.1)), 2)
                    wo_date = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))
                    writeoff_rows.append({
                        "id": uuid.uuid4(),
                        "ingredient_id": iid,
                        "quantity": Decimal(str(wo_qty)),
                        "reason": random.choice(["spoilage", "usage", "damage", "inventory"]),
                        "note": None,
                        "created_by_id": None,
                        "created_at": wo_date,
                    })
            venue_ingredient_ids[vm["id"]] = iids

        await db.execute(insert(Ingredient), ingredient_rows)
        await db.flush()
        await db.execute(insert(WriteOff), writeoff_rows)
        await db.flush()
        print(f"   + {len(ingredient_rows)} позиций склада, {len(writeoff_rows)} списаний")

        # ── 8. Expenses (финансы, 6 месяцев) ─────────────────────────────────
        MONTHLY_EXPENSE_TEMPLATES = {
            "Чайла": [
                ("rent",       180_000, 220_000),
                ("salaries",   420_000, 520_000),
                ("ingredients",   180_000, 240_000),
                ("utilities",   35_000,  55_000),
                ("marketing",   20_000,  40_000),
            ],
            "Suli da Guli": [
                ("rent",       220_000, 280_000),
                ("salaries",   500_000, 620_000),
                ("ingredients",   250_000, 330_000),
                ("utilities",   40_000,  65_000),
                ("marketing",   25_000,  50_000),
            ],
            "Lukum Vostok": [
                ("rent",       200_000, 260_000),
                ("salaries",   460_000, 580_000),
                ("ingredients",   220_000, 290_000),
                ("utilities",   35_000,  60_000),
                ("marketing",   20_000,  45_000),
            ],
            "&milk": [
                ("rent",       150_000, 190_000),
                ("salaries",   350_000, 450_000),
                ("ingredients",   120_000, 170_000),
                ("utilities",   25_000,  45_000),
                ("marketing",   30_000,  55_000),
            ],
            "Usta": [
                ("rent",       210_000, 270_000),
                ("salaries",   480_000, 600_000),
                ("ingredients",   240_000, 310_000),
                ("utilities",   38_000,  62_000),
                ("marketing",   22_000,  45_000),
            ],
            "Joy": [
                ("rent",       160_000, 200_000),
                ("salaries",   380_000, 480_000),
                ("ingredients",   140_000, 190_000),
                ("utilities",   28_000,  48_000),
                ("marketing",   35_000,  60_000),
            ],
        }
        ONE_OFF_EXPENSES = [
            ("equipment",  50_000,  250_000),
            ("other",      30_000,  150_000),
            ("other",      10_000,   80_000),
        ]

        today = date.today()
        expense_rows = []
        for vm in venue_meta:
            if not vm["active"]:
                continue
            templates = MONTHLY_EXPENSE_TEMPLATES.get(vm["brand"], MONTHLY_EXPENSE_TEMPLATES["Чайла"])

            for months_back in range(6):
                # month start: first day of that month
                m_date = today.replace(day=1)
                for _ in range(months_back):
                    m_date = (m_date - timedelta(days=1)).replace(day=1)

                for cat, lo, hi in templates:
                    exp_date = m_date.replace(
                        day=random.randint(1, 5) if cat in ("rent", "salaries") else random.randint(1, 28)
                    )
                    if exp_date > today:
                        exp_date = today
                    expense_rows.append({
                        "id": uuid.uuid4(),
                        "network_id": network.id,
                        "venue_id": vm["id"],
                        "category": cat,
                        "amount": Decimal(str(random.randint(lo // 1000, hi // 1000) * 1000)),
                        "description": None,
                        "expense_date": exp_date,
                        "created_by_id": None,
                        "created_at": datetime.now(timezone.utc) - timedelta(days=months_back * 30 + random.randint(0, 5)),
                    })

            # 1-2 one-off expenses per venue
            for _ in range(random.randint(1, 2)):
                cat, lo, hi = random.choice(ONE_OFF_EXPENSES)
                exp_date = today - timedelta(days=random.randint(0, 90))
                expense_rows.append({
                    "id": uuid.uuid4(),
                    "network_id": network.id,
                    "venue_id": vm["id"],
                    "category": cat,
                    "amount": Decimal(str(random.randint(lo // 1000, hi // 1000) * 1000)),
                    "description": None,
                    "expense_date": exp_date,
                    "created_by_id": None,
                    "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(0, 90)),
                })

        await db.execute(insert(Expense), expense_rows)
        await db.flush()
        print(f"   + {len(expense_rows)} записей расходов")

        # ── 9. Shifts (смены, 3 недели) ───────────────────────────────────────
        SHIFT_TEMPLATES_BY_BRAND = {
            "Чайла":        [(time(8, 0), time(16, 0)), (time(14, 0), time(22, 0))],
            "Suli da Guli": [(time(10, 0), time(18, 0)), (time(16, 0), time(23, 0))],
            "Lukum Vostok": [(time(10, 0), time(18, 0)), (time(16, 0), time(23, 0))],
            "&milk":        [(time(7, 0),  time(15, 0)), (time(13, 0), time(21, 0))],
            "Usta":         [(time(10, 0), time(18, 0)), (time(16, 0), time(23, 0))],
            "Joy":          [(time(8, 0),  time(16, 0)), (time(14, 0), time(22, 0))],
        }

        shift_rows = []
        week_start = today - timedelta(days=today.weekday())  # Monday this week

        for vm in venue_meta:
            if not vm["active"]:
                continue
            sids = venue_staff.get(vm["id"], [])
            if not sids:
                continue
            shift_templates = SHIFT_TEMPLATES_BY_BRAND.get(vm["brand"], SHIFT_TEMPLATES_BY_BRAND["Чайла"])

            for week_offset in range(-2, 2):  # last 2 weeks + current + next week
                week_monday = week_start + timedelta(weeks=week_offset)
                for day_offset in range(7):
                    shift_date = week_monday + timedelta(days=day_offset)
                    is_weekend = day_offset >= 5

                    # fewer staff on weekdays, more on weekends
                    n_morning = random.randint(2, 4) if is_weekend else random.randint(1, 3)
                    n_evening = random.randint(2, 4) if is_weekend else random.randint(1, 3)

                    assigned = random.sample(sids, min(n_morning + n_evening, len(sids)))
                    morning_staff = assigned[:n_morning]
                    evening_staff = assigned[n_morning:n_morning + n_evening]

                    for sid in morning_staff:
                        st, et = shift_templates[0]
                        if shift_date < today:
                            status = "done"
                        elif shift_date == today:
                            status = "active"
                        else:
                            status = "planned"
                        shift_rows.append({
                            "id": uuid.uuid4(),
                            "staff_id": sid,
                            "venue_id": vm["id"],
                            "shift_date": shift_date,
                            "start_time": st,
                            "end_time": et,
                            "status": status,
                            "notes": None,
                            "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(0, 14)),
                        })

                    for sid in evening_staff:
                        if not shift_templates[1:]:
                            continue
                        st, et = shift_templates[1]
                        if shift_date < today:
                            status = "done"
                        elif shift_date == today:
                            status = "active"
                        else:
                            status = "planned"
                        shift_rows.append({
                            "id": uuid.uuid4(),
                            "staff_id": sid,
                            "venue_id": vm["id"],
                            "shift_date": shift_date,
                            "start_time": st,
                            "end_time": et,
                            "status": status,
                            "notes": None,
                            "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(0, 14)),
                        })

        await db.execute(insert(Shift), shift_rows)
        await db.flush()
        await db.commit()
        print(f"   + {len(shift_rows)} смен (3 недели + следующая)")

        print(f"\n✅ Готово!")
        print(f"   Общая выручка за 90 дней: {total_rev:,.0f} ₸")
        print(f"   Среднедневная на сеть: {total_rev/90:,.0f} ₸")
        print(f"   Сотрудников: {len(staff_rows)}, отзывов: {len(review_rows):,}")
        total_exp = sum(float(r["amount"]) for r in expense_rows)
        print(f"   Расходов за 6 мес: {total_exp:,.0f} ₸ ({len(expense_rows)} записей)")
        print(f"   Склад: {len(ingredient_rows)} позиций, {len(writeoff_rows)} списаний")
        print(f"   Смен: {len(shift_rows)}")


if __name__ == "__main__":
    asyncio.run(main())
