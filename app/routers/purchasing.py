"""Suppliers and purchase invoices (goods receipts). Posting an invoice
atomically increases ingredient stock and updates each ingredient's
cost_per_unit to the latest purchase price — which feeds the food-cost
report. Invoices are immutable once posted."""
import logging
import uuid
from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.inventory import Ingredient
from app.models.purchasing import Supplier, PurchaseInvoice, PurchaseInvoiceLine
from app.models.user import User
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids

router = APIRouter(prefix="/api/purchasing", tags=["purchasing"])
logger = logging.getLogger(__name__)


class InvoiceLineIn(BaseModel):
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., ge=0)


class InvoiceIn(BaseModel):
    venue_id: uuid.UUID
    supplier_name: str | None = Field(None, max_length=255)
    number: str | None = Field(None, max_length=100)
    invoice_date: date_type | None = None
    lines: list[InvoiceLineIn] = Field(..., min_length=1)


def _invoice_out(inv: PurchaseInvoice) -> dict:
    return {
        "id": str(inv.id),
        "venue_id": str(inv.venue_id),
        "supplier": inv.supplier.name if inv.supplier else None,
        "number": inv.number,
        "invoice_date": inv.invoice_date.isoformat(),
        "total": float(inv.total),
        "created_by": inv.created_by,
        "lines": [
            {
                "ingredient_id": str(l.ingredient_id),
                "ingredient_name": l.ingredient_name,
                "quantity": float(l.quantity),
                "unit_cost": float(l.unit_cost),
            }
            for l in inv.lines
        ],
    }


@router.post("/invoices")
async def post_invoice(
    data: InvoiceIn,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    accessible = await get_accessible_venue_ids(current_user, db)
    if data.venue_id not in accessible:
        raise HTTPException(status_code=403, detail="Нет доступа к этому заведению")

    # All line ingredients must belong to this venue
    ingredient_ids = [l.ingredient_id for l in data.lines]
    ingredients = {
        i.id: i for i in (await db.execute(
            select(Ingredient)
            .where(Ingredient.id.in_(ingredient_ids), Ingredient.venue_id == data.venue_id)
            .with_for_update()
        )).scalars().all()
    }
    if len(ingredients) != len(set(ingredient_ids)):
        raise HTTPException(status_code=400, detail="Ингредиент не найден в этом заведении")

    supplier = None
    if data.supplier_name and data.supplier_name.strip():
        name = data.supplier_name.strip()
        supplier = (await db.execute(
            select(Supplier).where(Supplier.network_id == current_user.network_id, Supplier.name == name)
        )).scalar_one_or_none()
        if not supplier:
            supplier = Supplier(id=uuid.uuid4(), network_id=current_user.network_id, name=name)
            db.add(supplier)
            await db.flush()

    total = Decimal("0")
    invoice = PurchaseInvoice(
        id=uuid.uuid4(),
        venue_id=data.venue_id,
        supplier_id=supplier.id if supplier else None,
        number=data.number,
        invoice_date=data.invoice_date or date_type.today(),
        created_by=current_user.email,
    )
    db.add(invoice)
    await db.flush()

    for line in data.lines:
        ing = ingredients[line.ingredient_id]
        db.add(PurchaseInvoiceLine(
            id=uuid.uuid4(),
            invoice_id=invoice.id,
            ingredient_id=ing.id,
            ingredient_name=ing.name,
            quantity=line.quantity,
            unit_cost=line.unit_cost,
        ))
        # Apply to stock: quantity up, cost updated to the latest price.
        ing.quantity = (ing.quantity or Decimal("0")) + line.quantity
        ing.cost_per_unit = line.unit_cost
        total += line.quantity * line.unit_cost

    invoice.total = total
    await db.commit()
    logger.info("Invoice %s posted at venue %s by %s (total=%s)", invoice.id, data.venue_id, current_user.email, total)

    inv = (await db.execute(
        select(PurchaseInvoice)
        .options(selectinload(PurchaseInvoice.lines), selectinload(PurchaseInvoice.supplier))
        .where(PurchaseInvoice.id == invoice.id)
    )).scalar_one()
    return _invoice_out(inv)


@router.get("/invoices")
async def list_invoices(
    venue_id: uuid.UUID | None = Query(None),
    limit: int = Query(30, le=100),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    accessible = await get_accessible_venue_ids(current_user, db)
    filter_ids = [venue_id] if venue_id and venue_id in accessible else accessible
    invoices = (await db.execute(
        select(PurchaseInvoice)
        .options(selectinload(PurchaseInvoice.lines), selectinload(PurchaseInvoice.supplier))
        .where(PurchaseInvoice.venue_id.in_(filter_ids))
        .order_by(PurchaseInvoice.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return {"invoices": [_invoice_out(i) for i in invoices]}


@router.get("/suppliers")
async def list_suppliers(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    suppliers = (await db.execute(
        select(Supplier).where(Supplier.network_id == current_user.network_id).order_by(Supplier.name)
    )).scalars().all()
    return {"suppliers": [{"id": str(s.id), "name": s.name} for s in suppliers]}
