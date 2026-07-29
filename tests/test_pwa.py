"""White-label guest PWA: per-venue manifest, service worker, and branding.
The guest installs the restaurant's own branded app — never "RestOS"."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _venue(client: AsyncClient, h: dict) -> str:
    return (await client.post("/api/venues/", json={"name": "Bistro"}, headers=h)).json()["id"]


async def test_manifest_defaults_to_venue_name(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    vid = await _venue(client, h)
    resp = await client.get(f"/order/{vid}/manifest.webmanifest")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/manifest+json")
    m = resp.json()
    assert m["name"] == "Bistro"
    assert m["start_url"] == f"/order/{vid}"
    assert m["scope"] == "/order/"
    assert m["display"] == "standalone"


async def test_branding_overrides_manifest(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    vid = await _venue(client, h)
    resp = await client.patch("/settings/api/branding", headers=h,
                              json={"brand_name": "Terra", "brand_color": "#2F6FB3"})
    assert resp.status_code == 200
    m = (await client.get(f"/order/{vid}/manifest.webmanifest")).json()
    assert m["name"] == "Terra"
    assert m["theme_color"] == "#2F6FB3"


async def test_branding_rejects_bad_color(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    resp = await client.patch("/settings/api/branding", headers=h, json={"brand_color": "red"})
    assert resp.status_code == 400


async def test_service_worker_served_with_order_scope(client: AsyncClient):
    resp = await client.get("/guest-sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    # Must be allowed to control the /order/ scope even though it lives at root.
    assert resp.headers.get("service-worker-allowed") == "/order/"


async def test_guest_page_is_installable(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    vid = await _venue(client, h)
    await client.patch("/settings/api/branding", headers=h, json={"brand_name": "Terra"})
    html = (await client.get(f"/order/{vid}")).text
    assert "manifest.webmanifest" in html
    assert "installBtn" in html
    assert "/guest-sw.js" in html
    assert "Terra" in html  # brand shown, not "RestOS"


async def test_manifest_404_for_unknown_venue(client: AsyncClient):
    resp = await client.get("/order/00000000-0000-0000-0000-000000000000/manifest.webmanifest")
    assert resp.status_code == 404
