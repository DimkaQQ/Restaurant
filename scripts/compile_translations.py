"""Extract {{ _("...") }} message ids from the i18n-enabled templates and
compile locales/en/LC_MESSAGES/messages.mo. Run from the repo root after
adding a new translatable string or editing an existing translation:

    python scripts/compile_translations.py

Requires `pip install babel` (dev-only dependency, see requirements-dev.txt).
"""
import re
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo

files = ["app/templates/landing.html","app/templates/login.html","app/templates/register.html",
         "app/templates/forgot_password.html","app/templates/reset_password.html",
         "app/templates/legal/terms.html","app/templates/legal/privacy.html"]

pattern = re.compile(r'_\(\s*"((?:[^"\\]|\\.)*)"\s*(?:\|\s*tojson\s*)?\)|_\(\s*\'((?:[^\'\\]|\\.)*)\'\s*(?:\|\s*tojson\s*)?\)')

strings = []
for f in files:
    text = open(f, encoding='utf-8').read()
    for m in pattern.finditer(text):
        s = m.group(1) if m.group(1) is not None else m.group(2)
        strings.append(s)

uniq = sorted(set(strings))

TRANSLATIONS = {
 '1 заведение': '1 venue',
 '1. Какие данные мы собираем': '1. What data we collect',
 '1. Регистрация и учётная запись': '1. Registration and account',
 '14 дней бесплатно, без карты. Настройка занимает пару минут.': '14 days free, no card required. Setup takes a couple of minutes.',
 '14 дней бесплатно, без карты. Начните за 2 минуты.': '14 days free, no card required. Get started in 2 minutes.',
 '2. Для чего используются данные': '2. What the data is used for',
 '2. Пробный период и оплата': '2. Trial period and billing',
 '3. Данные и фискализация': '3. Data and fiscalization',
 '3. Передача третьим лицам': '3. Sharing with third parties',
 '4. Ограничение ответственности': '4. Limitation of liability',
 '4. Хранение и удаление': '4. Storage and deletion',
 '5. Безопасность': '5. Security',
 '5. Прекращение действия': '5. Termination',
 '6. Ваши права': '6. Your rights',
 '6. Изменения условий': '6. Changes to these terms',
 '7. Контакты': '7. Contact',
 'P&L, расходы, выручка по заведениям, NPS гостей — вся картина бизнеса в одном месте.': 'P&L, expenses, revenue by venue, guest NPS — the full business picture in one place.',
 'RestOS обрабатывает персональные данные владельцев ресторанов, их сотрудников и гостей (клиентов ресторанов) в объёме, необходимом для работы Сервиса.': 'RestOS processes personal data of restaurant owners, their staff, and guests (restaurant customers) to the extent necessary to operate the Service.',
 'RestOS — Восстановление пароля': 'RestOS — Password recovery',
 'RestOS — Вход': 'RestOS — Sign in',
 'RestOS — Новый пароль': 'RestOS — New password',
 'RestOS — Платформа управления рестораном': 'RestOS — Restaurant management platform',
 'RestOS — Регистрация': 'RestOS — Sign up',
 'RestOS — приём заказов, кухонный дисплей, склад, смены персонала, программа лояльности и фискализация чеков в одной панели. 14 дней бесплатно.': 'RestOS — order taking, kitchen display, inventory, staff shifts, loyalty program, and receipt fiscalization in one dashboard. 14 days free.',
 'Без карты. Отменить можно в любой момент.': 'No card required. Cancel anytime.',
 'Безлимит заведений': 'Unlimited venues',
 'Безлимит сотрудников': 'Unlimited staff',
 'Бонусные баллы, история визитов и Telegram-бот для гостей — без сторонних CRM.': 'Bonus points, visit history, and a Telegram bot for guests — no third-party CRM needed.',
 'Возможности': 'Features',
 'Войти': 'Sign in',
 'Восстановление пароля': 'Password recovery',
 'Всё, что нужно ресторану': 'Everything a restaurant needs',
 'Вход': 'Sign in',
 'Вы вправе запросить доступ к своим данным, их исправление или удаление. Для этого обратитесь через раздел поддержки в личном кабинете.': 'You may request access to, correction of, or deletion of your data. Contact us via the support section in your account.',
 'Вы можете отменить подписку в любой момент через раздел «Оплата». Мы вправе приостановить доступ при нарушении условий использования или систематической неоплате.': 'You may cancel your subscription anytime via the "Billing" section. We may suspend access for violating these terms or for repeated non-payment.',
 'Вы самостоятельно несёте ответственность за корректность данных, вносимых в Сервис (меню, цены, чеки), и за соблюдение налогового и фискального законодательства вашей юрисдикции. Интеграции с фискальными провайдерами (например, Webkassa) выполняются с использованием ваших собственных учётных данных, полученных непосредственно от этих провайдеров.': 'You are solely responsible for the accuracy of data entered into the Service (menu, prices, receipts) and for complying with the tax and fiscal laws of your jurisdiction. Integrations with fiscal providers (e.g. Webkassa) use your own credentials obtained directly from those providers.',
 'Готовы попробовать?': 'Ready to try it?',
 'График смен, роли официант/повар/кассир/менеджер, рейтинг сотрудников по отзывам гостей.': 'Shift schedules, waiter/cook/cashier/manager roles, staff ratings from guest reviews.',
 'Данные гостей: имя, телефон/Telegram ID, история заказов, баллы лояльности — используются для программы лояльности и уведомлений.': "Guest data: name, phone/Telegram ID, order history, loyalty points — used for the loyalty program and notifications.",
 'Данные сотрудников: имя, роль, отработанные смены — вносятся владельцем ресторана.': "Staff data: name, role, worked shifts — entered by the restaurant owner.",
 'Данные учётной записи владельца: имя ресторана, email, хешированный пароль.': "Owner account data: restaurant name, email, hashed password.",
 'Данные хранятся, пока учётная запись активна. Владелец аккаунта может запросить экспорт или удаление данных своей сети ресторанов, написав в поддержку — запрос будет обработан в разумный срок с учётом требований налогового и бухгалтерского законодательства о сроках хранения документов.': 'Data is retained while the account is active. The account owner may request export or deletion of their restaurant network\'s data by contacting support — the request will be handled within a reasonable time, subject to tax and accounting record-retention requirements.',
 'Для предоставления функций Сервиса (приём заказов, кухонный дисплей, лояльность, аналитика, фискализация чеков), обеспечения безопасности учётных записей и, при наличии согласия, для email-уведомлений (например, восстановление пароля).': 'To provide the Service\'s features (order taking, kitchen display, loyalty, analytics, receipt fiscalization), to secure accounts, and, where consented, for email notifications (e.g. password recovery).',
 'До 3 сотрудников': 'Up to 3 staff members',
 'До 5 заведений': 'Up to 5 venues',
 'Если такой email зарегистрирован, мы отправили ссылку для сброса пароля.': 'If that email is registered, we sent a password reset link.',
 'Забыли пароль?': 'Forgot password?',
 'Задайте новый пароль': 'Set a new password',
 'Заказы, склад, смены': 'Orders, inventory, shifts',
 'Интеграция с Webkassa (Казахстан) — чек пробивается автоматически при закрытии заказа.': 'Integration with Webkassa (Kazakhstan) — the receipt is fiscalized automatically when an order closes.',
 'Конфиденциальность': 'Privacy',
 'Кухонный дисплей (KDS)': 'Kitchen display (KDS)',
 'Мой ресторан': 'My Restaurant',
 'Мультисеть': 'Multi-location',
 'Мы можем обновлять эти условия. Существенные изменения будут доведены до вашего сведения по email или через интерфейс Сервиса.': 'We may update these terms. Material changes will be communicated to you by email or through the Service interface.',
 'Мы передаём данные третьим лицам только в объёме, необходимом для работы Сервиса: платёжному процессору (Stripe), фискальным провайдерам, выбранным вами (например, Webkassa) — с использованием ваших собственных учётных данных, и провайдеру email-рассылок. Мы не продаём персональные данные третьим лицам.': 'We share data with third parties only as needed to operate the Service: the payment processor (Stripe), the fiscal provider you chose (e.g. Webkassa) using your own credentials, and our email delivery provider. We do not sell personal data to third parties.',
 'Назад ко входу': 'Back to sign in',
 'Название сети / ресторана': 'Restaurant / network name',
 'Настоящие условия регулируют использование платформы RestOS (далее — «Сервис»), предоставляемой для управления ресторанами: приём заказов, лояльность гостей, склад, смены персонала, аналитика и фискализация чеков.': 'These terms govern the use of the RestOS platform (the "Service"), provided for restaurant management: order taking, guest loyalty, inventory, staff shifts, analytics, and receipt fiscalization.',
 'Начать бесплатно': 'Start free',
 'Нет аккаунта?': "Don't have an account?",
 'Новый пароль': 'New password',
 'Новым аккаунтам предоставляется бесплатный пробный период 14 дней. По истечении пробного периода для продолжения использования Сервиса требуется активная оплаченная подписка. Оплата обрабатывается через Stripe; RestOS не хранит данные вашей карты.': 'New accounts get a free 14-day trial. After the trial, continued use of the Service requires an active paid subscription. Payments are processed via Stripe; RestOS does not store your card details.',
 'Обновлено:': 'Last updated:',
 'Отправить ссылку для сброса': 'Send reset link',
 'Официант, кухня и касса видят заказ в реальном времени. Столы, статусы, комментарии к позициям.': 'Waiter, kitchen, and register see the order in real time. Tables, statuses, item comments.',
 'Ошибка входа': 'Sign-in error',
 'Ошибка отправки. Попробуйте позже.': 'Failed to send. Please try again later.',
 'Ошибка регистрации': 'Registration error',
 'Панель управления сетью ресторанов': 'Restaurant network management dashboard',
 'Пароли хранятся в виде необратимых хешей (bcrypt). Соединение с Сервисом защищено HTTPS. Доступ к данным одной сети ресторанов технически изолирован от данных других сетей.': 'Passwords are stored as irreversible hashes (bcrypt). The connection to the Service is protected by HTTPS. Access to one restaurant network\'s data is technically isolated from other networks\' data.',
 'Пароль': 'Password',
 'Платёжные данные обрабатываются напрямую Stripe; RestOS не хранит номера карт.': 'Payment data is processed directly by Stripe; RestOS does not store card numbers.',
 'По вопросам, связанным с условиями использования, пишите на адрес, указанный в вашем аккаунте платформы, или через раздел поддержки.': 'For questions about these terms, contact the address listed in your platform account, or via the support section.',
 'Политика конфиденциальности': 'Privacy Policy',
 'Политика конфиденциальности — RestOS': 'Privacy Policy — RestOS',
 'Политика конфиденциальности →': 'Privacy Policy →',
 'Попробовать 14 дней бесплатно': 'Try 14 days free',
 'Посмотреть цены': 'See pricing',
 'Приоритетная поддержка': 'Priority support',
 'Приём заказов и касса': 'Order taking and register',
 'Приём заказов, кухонный дисплей, склад с автосписанием по техкартам, смены персонала, программа лояльности гостей и фискализация чеков — без Excel и десятка разных приложений.': 'Order taking, kitchen display, inventory with automatic deduction by recipe, staff shifts, guest loyalty program, and receipt fiscalization — no Excel, no dozen different apps.',
 'Программа лояльности': 'Loyalty program',
 'Прозрачные цены': 'Transparent pricing',
 'Регистрируясь, вы подтверждаете, что представляете юридическое лицо или ИП, имеющее право заключать договоры на оказание услуг общественного питания. Вы несёте ответственность за сохранность учётных данных и действия под вашей учётной записью.': 'By registering, you confirm that you represent a legal entity or sole proprietor entitled to enter into contracts for food service. You are responsible for safeguarding your credentials and for actions taken under your account.',
 'Сервис предоставляется «как есть». RestOS не несёт ответственности за косвенные убытки, упущенную выгоду или потерю данных, возникшие в результате использования или невозможности использования Сервиса, в пределах, допустимых применимым законодательством.': 'The Service is provided "as is". RestOS is not liable for indirect losses, lost profits, or data loss arising from the use or inability to use the Service, to the extent permitted by applicable law.',
 'Склад и техкарты': 'Inventory and recipes',
 'Смены и персонал': 'Shifts and staff',
 'Согласен с': 'I agree to the',
 'Создать': 'Sign up',
 'Создать аккаунт': 'Create account',
 'Сохранить пароль': 'Save password',
 'Списание ингредиентов автоматически при закрытии заказа по рецептуре блюда — остатки всегда актуальны.': 'Ingredients are deducted automatically when an order closes, based on the dish recipe — stock levels stay accurate.',
 'Ссылка недействительна или устарела': 'The link is invalid or has expired',
 'Технические данные: IP-адрес, тип браузера — для безопасности и предотвращения злоупотреблений (например, ограничение частоты запросов при входе).': 'Technical data: IP address, browser type — for security and abuse prevention (e.g. rate limiting on sign-in).',
 'Уже есть аккаунт?': 'Already have an account?',
 'Управляйте несколькими заведениями из одного аккаунта с отдельными данными по каждому.': 'Manage multiple venues from one account, each with its own separate data.',
 'Управляйте рестораном': 'Run your restaurant',
 'Условия использования': 'Terms of Service',
 'Условия использования — RestOS': 'Terms of Service — RestOS',
 'Финансы P&L, аналитика': 'P&L finance, analytics',
 'Финансы и аналитика': 'Finance and analytics',
 'Фискализация чеков': 'Receipt fiscalization',
 'Цены': 'Pricing',
 'Экран для кухни на любом планшете — очередь заказов по колонкам, таймеры готовки, без бумажных чеков.': 'A kitchen screen on any tablet — orders queued by column, cook timers, no paper tickets.',
 'и': 'and',
 'из одной панели': 'from one dashboard',
 'мес': 'mo',
 'политикой конфиденциальности': 'Privacy Policy',
 'условиями использования': 'Terms of Service',
 '← Условия использования': '← Terms of Service',
}

missing = [s for s in uniq if s not in TRANSLATIONS]
if missing:
    print("MISSING TRANSLATIONS:")
    for m in missing:
        print(repr(m))
    raise SystemExit(1)

catalog = Catalog(locale='en')
for msgid in uniq:
    catalog.add(msgid, TRANSLATIONS[msgid])

import os
os.makedirs('locales/en/LC_MESSAGES', exist_ok=True)
with open('locales/en/LC_MESSAGES/messages.mo', 'wb') as f:
    write_mo(f, catalog)

# also save a .po for readability/future editing
from babel.messages.pofile import write_po
with open('locales/en/LC_MESSAGES/messages.po', 'wb') as f:
    write_po(f, catalog)

print(f"Compiled {len(uniq)} strings.")
