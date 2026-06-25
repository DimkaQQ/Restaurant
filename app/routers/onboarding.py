from app.templates_env import templates
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.onboarding import OnboardingModule, OnboardingQuestion, OnboardingProgress
from app.models.staff import Staff
from app.models.user import User
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids

router = APIRouter(tags=["onboarding"])
logger = logging.getLogger(__name__)


# ── Manager views ─────────────────────────────────────────────────────────────

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        modules = (await db.execute(
            select(OnboardingModule)
            .options(selectinload(OnboardingModule.questions))
            .where(OnboardingModule.network_id == current_user.network_id)
            .order_by(OnboardingModule.order_index, OnboardingModule.created_at)
        )).scalars().all()

        accessible_ids = await get_accessible_venue_ids(current_user, db)
        staff_list = (await db.execute(
            select(Staff)
            .where(Staff.venue_id.in_(accessible_ids), Staff.is_active == True)
            .order_by(Staff.name)
        )).scalars().all()

        # Build progress map: {staff_id: {module_id: OnboardingProgress}}
        progress_rows = (await db.execute(
            select(OnboardingProgress).where(
                OnboardingProgress.staff_id.in_([s.id for s in staff_list])
            )
        )).scalars().all()

        progress_map: dict[uuid.UUID, dict[uuid.UUID, OnboardingProgress]] = {}
        for p in progress_rows:
            progress_map.setdefault(p.staff_id, {})[p.module_id] = p

        active_modules = [m for m in modules if m.is_active]

        # For each staff, determine if they completed all modules (certificate earned)
        staff_completed = {}
        for s in staff_list:
            s_prog = progress_map.get(s.id, {})
            if active_modules and all(s_prog.get(m.id, None) and s_prog[m.id].passed for m in active_modules):
                staff_completed[s.id] = True

        return templates.TemplateResponse("onboarding.html", {
            "request": request,
            "user": current_user,
            "modules": modules,
            "active_modules": active_modules,
            "staff_list": staff_list,
            "progress_map": progress_map,
            "staff_completed": staff_completed,
        })
    except Exception as e:
        logger.error("Onboarding page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки онбординга")


# ── Module CRUD API ───────────────────────────────────────────────────────────

class ModuleCreate(BaseModel):
    title: str
    description: str | None = None
    video_url: str | None = None
    order_index: int = 0
    pass_threshold: int = 70


class QuestionCreate(BaseModel):
    question: str
    option_a: str
    option_b: str
    option_c: str | None = None
    option_d: str | None = None
    correct_option: str  # 'a', 'b', 'c', 'd'
    order_index: int = 0


@router.post("/api/onboarding/modules")
async def create_module(
    data: ModuleCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("owner", "manager", "administrator"):
        raise HTTPException(status_code=403, detail="Нет прав")
    module = OnboardingModule(
        id=uuid.uuid4(),
        network_id=current_user.network_id,
        **data.model_dump(),
    )
    db.add(module)
    await db.commit()
    return {"id": str(module.id)}


@router.delete("/api/onboarding/modules/{module_id}")
async def delete_module(
    module_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("owner", "manager", "administrator"):
        raise HTTPException(status_code=403, detail="Нет прав")
    module = (await db.execute(
        select(OnboardingModule).where(
            OnboardingModule.id == module_id,
            OnboardingModule.network_id == current_user.network_id,
        )
    )).scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Модуль не найден")
    await db.delete(module)
    await db.commit()
    return {"ok": True}


@router.post("/api/onboarding/modules/{module_id}/questions")
async def add_question(
    module_id: uuid.UUID,
    data: QuestionCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("owner", "manager", "administrator"):
        raise HTTPException(status_code=403, detail="Нет прав")
    if data.correct_option not in ('a', 'b', 'c', 'd'):
        raise HTTPException(status_code=400, detail="correct_option должен быть a/b/c/d")
    module = (await db.execute(
        select(OnboardingModule).where(
            OnboardingModule.id == module_id,
            OnboardingModule.network_id == current_user.network_id,
        )
    )).scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Модуль не найден")
    q = OnboardingQuestion(id=uuid.uuid4(), module_id=module_id, **data.model_dump())
    db.add(q)
    await db.commit()
    return {"id": str(q.id)}


@router.delete("/api/onboarding/questions/{question_id}")
async def delete_question(
    question_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("owner", "manager", "administrator"):
        raise HTTPException(status_code=403, detail="Нет прав")
    q = (await db.execute(
        select(OnboardingQuestion)
        .options(selectinload(OnboardingQuestion.module))
        .where(OnboardingQuestion.id == question_id)
    )).scalar_one_or_none()
    if not q or q.module.network_id != current_user.network_id:
        raise HTTPException(status_code=404, detail="Вопрос не найден")
    await db.delete(q)
    await db.commit()
    return {"ok": True}


# ── Staff-facing onboarding (no auth — UUID as access token) ──────────────────

@router.get("/onboard/{staff_id}", response_class=HTMLResponse)
async def staff_onboarding_portal(
    request: Request,
    staff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    staff = (await db.execute(
        select(Staff).where(Staff.id == staff_id, Staff.is_active == True)
    )).scalar_one_or_none()
    if not staff:
        return HTMLResponse("<h2 style='font-family:sans-serif;padding:2rem'>Ссылка недействительна</h2>", status_code=404)

    modules = (await db.execute(
        select(OnboardingModule)
        .options(selectinload(OnboardingModule.questions))
        .where(OnboardingModule.network_id == staff.network_id, OnboardingModule.is_active == True)
        .order_by(OnboardingModule.order_index, OnboardingModule.created_at)
    )).scalars().all()

    progress_rows = (await db.execute(
        select(OnboardingProgress).where(OnboardingProgress.staff_id == staff_id)
    )).scalars().all()
    progress_map = {p.module_id: p for p in progress_rows}

    all_passed = bool(modules) and all(
        progress_map.get(m.id) and progress_map[m.id].passed for m in modules
    )

    # Determine unlocked: sequential — unlock next module only after previous passed
    unlocked: set[uuid.UUID] = set()
    for i, m in enumerate(modules):
        if i == 0:
            unlocked.add(m.id)
        elif progress_map.get(modules[i - 1].id) and progress_map[modules[i - 1].id].passed:
            unlocked.add(m.id)

    return templates.TemplateResponse("onboarding_do.html", {
        "request": request,
        "staff": staff,
        "modules": modules,
        "progress_map": progress_map,
        "unlocked": unlocked,
        "all_passed": all_passed,
        "mode": "list",
    })


@router.get("/onboard/{staff_id}/module/{module_id}", response_class=HTMLResponse)
async def staff_do_module(
    request: Request,
    staff_id: uuid.UUID,
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    staff = (await db.execute(
        select(Staff).where(Staff.id == staff_id, Staff.is_active == True)
    )).scalar_one_or_none()
    if not staff:
        return HTMLResponse("<h2 style='font-family:sans-serif;padding:2rem'>Ссылка недействительна</h2>", status_code=404)

    module = (await db.execute(
        select(OnboardingModule)
        .options(selectinload(OnboardingModule.questions))
        .where(
            OnboardingModule.id == module_id,
            OnboardingModule.network_id == staff.network_id,
            OnboardingModule.is_active == True,
        )
    )).scalar_one_or_none()
    if not module:
        return RedirectResponse(f"/onboard/{staff_id}")

    progress = (await db.execute(
        select(OnboardingProgress).where(
            OnboardingProgress.staff_id == staff_id,
            OnboardingProgress.module_id == module_id,
        )
    )).scalar_one_or_none()

    return templates.TemplateResponse("onboarding_do.html", {
        "request": request,
        "staff": staff,
        "module": module,
        "progress": progress,
        "mode": "module",
    })


class TestSubmit(BaseModel):
    answers: dict[str, str]  # {question_id: 'a'/'b'/'c'/'d'}


@router.post("/onboard/{staff_id}/module/{module_id}/submit")
async def submit_module_test(
    staff_id: uuid.UUID,
    module_id: uuid.UUID,
    data: TestSubmit,
    db: AsyncSession = Depends(get_db),
):
    staff = (await db.execute(
        select(Staff).where(Staff.id == staff_id, Staff.is_active == True)
    )).scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    module = (await db.execute(
        select(OnboardingModule)
        .options(selectinload(OnboardingModule.questions))
        .where(
            OnboardingModule.id == module_id,
            OnboardingModule.network_id == staff.network_id,
        )
    )).scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Модуль не найден")

    # If no questions — auto-pass (video-only module)
    if not module.questions:
        score, passed = 100, True
    else:
        correct = sum(
            1 for q in module.questions
            if data.answers.get(str(q.id)) == q.correct_option
        )
        score = round(correct / len(module.questions) * 100)
        passed = score >= module.pass_threshold

    # Upsert progress
    progress = (await db.execute(
        select(OnboardingProgress).where(
            OnboardingProgress.staff_id == staff_id,
            OnboardingProgress.module_id == module_id,
        )
    )).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if progress:
        progress.score = score
        progress.passed = passed
        progress.attempts += 1
        if passed and not progress.completed_at:
            progress.completed_at = now
    else:
        progress = OnboardingProgress(
            id=uuid.uuid4(),
            staff_id=staff_id,
            module_id=module_id,
            score=score,
            passed=passed,
            attempts=1,
            completed_at=now if passed else None,
        )
        db.add(progress)

    await db.commit()
    return {"score": score, "passed": passed, "threshold": module.pass_threshold}


@router.get("/onboard/{staff_id}/certificate", response_class=HTMLResponse)
async def staff_certificate(
    request: Request,
    staff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    staff = (await db.execute(
        select(Staff).where(Staff.id == staff_id)
    )).scalar_one_or_none()
    if not staff:
        return HTMLResponse("<h2 style='font-family:sans-serif;padding:2rem'>Ссылка недействительна</h2>", status_code=404)

    modules = (await db.execute(
        select(OnboardingModule)
        .where(OnboardingModule.network_id == staff.network_id, OnboardingModule.is_active == True)
        .order_by(OnboardingModule.order_index)
    )).scalars().all()

    progress_rows = (await db.execute(
        select(OnboardingProgress).where(
            OnboardingProgress.staff_id == staff_id,
            OnboardingProgress.passed == True,
        )
    )).scalars().all()
    passed_ids = {p.module_id for p in progress_rows}
    progress_map = {p.module_id: p for p in progress_rows}

    all_passed = bool(modules) and all(m.id in passed_ids for m in modules)
    if not all_passed:
        return RedirectResponse(f"/onboard/{staff_id}")

    completed_at = max((p.completed_at for p in progress_rows if p.completed_at), default=datetime.now(timezone.utc))

    return templates.TemplateResponse("onboarding_certificate.html", {
        "request": request,
        "staff": staff,
        "modules": modules,
        "progress_map": progress_map,
        "completed_at": completed_at,
    })
