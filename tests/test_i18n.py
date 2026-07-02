"""i18n: landing/auth/legal pages support ?lang=en via a gettext catalog,
default to Russian, and persist the choice in a cookie."""
from httpx import AsyncClient


async def test_landing_defaults_to_russian(client: AsyncClient):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Управляйте рестораном" in resp.text


async def test_landing_lang_en_switches_to_english(client: AsyncClient):
    resp = await client.get("/?lang=en")
    assert resp.status_code == 200
    assert "Run your restaurant" in resp.text
    assert resp.cookies.get("lang") == "en"


async def test_login_page_translates(client: AsyncClient):
    resp = await client.get("/auth/login?lang=en")
    assert resp.status_code == 200
    assert "Sign in" in resp.text


async def test_legal_pages_translate(client: AsyncClient):
    terms = await client.get("/legal/terms?lang=en")
    privacy = await client.get("/legal/privacy?lang=en")
    assert "Terms of Service" in terms.text
    assert "Privacy Policy" in privacy.text


async def test_lang_cookie_persists_choice(client: AsyncClient):
    first = await client.get("/?lang=en")
    assert first.cookies.get("lang") == "en"
    second = await client.get("/")
    assert "Run your restaurant" in second.text
