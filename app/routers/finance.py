from app.templates_env import templates
import logging
import uuid
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, cast, Date, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.finance import Expense, EXPENSE_CATEGORIES
from app.models.order import Order
from app.models.venue import Venue
from app.models.user import User
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids

router = APIRouter(tags=["finance"])
logger = logging.getLogger(__name__)


class ExpenseCreate(BaseModel):
    venue_id: uuid.UUID
    category: str = "other"
    amount: Decimal = Field(..., gt=0)
    description: str | None = None
    expense_date: date


@router.get("/finance", response_class=HTMLResponse)
async def finance_page(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    period: str = Query("month"),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        now = datetime.now(timezone.utc)
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        venues = (await db.execute(
            select(Venue).where(Venue.id.in_(accessible_ids), Venue.is_active == True).order_by(Venue.name)
        )).scalars().all()

        filter_ids = [venue_id] if venue_id and venue_id in accessible_ids else accessible_ids
        selected_venue_id = str(venue_id) if venue_id and venue_id in accessible_ids else ""

        # Period boundaries
        if period == "week":
            start_date = now.date() - timedelta(days=7)
        elif period == "quarter":
            start_date = now.date() - timedelta(days=90)
        elif period == "year":
            start_date = now.date().replace(month=1, day=1)
        else:  # month
            start_date = now.date().replace(day=1)

        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)

        # Revenue from orders (done)
        revenue = (await db.execute(
            select(func.coalesce(func.sum(Order.total_amount), 0))
            .where(Order.venue_id.in_(filter_ids), Order.status == "done", Order.created_at >= start_dt)
        )).scalar() or Decimal(0)

        # Expenses
        expenses_total = (await db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0))
            .where(Expense.venue_id.in_(filter_ids), Expense.expense_date >= start_date)
        )).scalar() or Decimal(0)

        profit = Decimal(str(revenue)) - Decimal(str(expenses_total))
        margin = round(float(profit) / float(revenue) * 100, 1) if revenue else 0

        # Expenses by category
        category_rows = (await db.execute(
            select(Expense.category, func.sum(Expense.amount).label("total"))
            .where(Expense.venue_id.in_(filter_ids), Expense.expense_date >= start_date)
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )).all()
        by_category = [
            {"key": r.category, "label": EXPENSE_CATEGORIES.get(r.category, r.category), "amount": float(r.total)}
            for r in category_rows
        ]

        # Monthly chart (last 6 months)
        six_months_ago = now.date() - timedelta(days=180)
        revenue_monthly = (await db.execute(
            select(
                extract("year", Order.created_at).label("yr"),
                extract("month", Order.created_at).label("mo"),
                func.sum(Order.total_amount).label("rev"),
            )
            .where(Order.venue_id.in_(filter_ids), Order.status == "done", Order.created_at >= datetime.combine(six_months_ago, datetime.min.time()).replace(tzinfo=timezone.utc))
            .group_by("yr", "mo")
            .order_by("yr", "mo")
        )).all()

        expenses_monthly = (await db.execute(
            select(
                extract("year", cast(Expense.expense_date, Date)).label("yr"),
                extract("month", cast(Expense.expense_date, Date)).label("mo"),
                func.sum(Expense.amount).label("exp"),
            )
            .where(Expense.venue_id.in_(filter_ids), Expense.expense_date >= six_months_ago)
            .group_by("yr", "mo")
            .order_by("yr", "mo")
        )).all()

        # Merge into chart data
        chart_map: dict = {}
        for r in revenue_monthly:
            key = f"{int(r.yr)}-{int(r.mo):02d}"
            chart_map.setdefault(key, {"label": key, "revenue": 0, "expenses": 0})["revenue"] = float(r.rev)
        for r in expenses_monthly:
            key = f"{int(r.yr)}-{int(r.mo):02d}"
            chart_map.setdefault(key, {"label": key, "revenue": 0, "expenses": 0})["expenses"] = float(r.exp)
        chart_data = sorted(chart_map.values(), key=lambda x: x["label"])

        # Recent expenses list
        recent_expenses = (await db.execute(
            select(Expense)
            .where(Expense.venue_id.in_(filter_ids), Expense.expense_date >= start_date)
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .limit(50)
        )).scalars().all()

        return templates.TemplateResponse("finance.html", {
            "request": request,
            "user": current_user,
            "venues": venues,
            "selected_venue_id": selected_venue_id,
            "period": period,
            "revenue": float(revenue),
            "expenses_total": float(expenses_total),
            "profit": float(profit),
            "margin": margin,
            "by_category": by_category,
            "chart_data": chart_data,
            "recent_expenses": recent_expenses,
            "expense_categories": EXPENSE_CATEGORIES,
            "now": now,
        })
    except Exception as e:
        logger.error("Finance page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки финансов")


@router.post("/api/expenses")
async def create_expense(
    data: ExpenseCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        if data.venue_id not in accessible_ids:
            raise HTTPException(status_code=403, detail="Нет доступа к заведению")
        if data.category not in EXPENSE_CATEGORIES:
            raise HTTPException(status_code=400, detail="Неверная категория")

        expense = Expense(
            id=uuid.uuid4(),
            network_id=current_user.network_id,
            created_by_id=current_user.id,
            **data.model_dump(),
        )
        db.add(expense)
        await db.commit()
        return {"id": str(expense.id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create expense error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка создания расхода")


@router.delete("/api/expenses/{expense_id}")
async def delete_expense(
    expense_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        expense = (await db.execute(
            select(Expense).where(Expense.id == expense_id, Expense.venue_id.in_(accessible_ids))
        )).scalar_one_or_none()
        if not expense:
            raise HTTPException(status_code=404, detail="Расход не найден")
        await db.delete(expense)
        await db.commit()
        return {"message": "Удалено"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete expense error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка удаления")
