import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import engine
from app.models import *  # noqa: F401,F403 — registers all models with Base
from app.routers import auth, dashboard, venues, menu, orders, guests, analytics, staff, settings, inventory, finance, shifts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RestOS starting up")
    yield
    await engine.dispose()
    logger.info("RestOS shut down")


app = FastAPI(title="RestOS", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(venues.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(guests.router)
app.include_router(analytics.router)
app.include_router(staff.router)
app.include_router(settings.router)
app.include_router(inventory.router)
app.include_router(finance.router)
app.include_router(shifts.router)
