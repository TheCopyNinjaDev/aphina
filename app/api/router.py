from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.services import user_service
from app.services.calorie_service import format_progress_bar, get_food_equivalents

router = APIRouter()


class UserProfileRequest(BaseModel):
    telegram_id: int
    age: int
    gender: str
    weight: float
    height: float
    target_weight: float
    activity_level: str


class TodayProgressResponse(BaseModel):
    consumed: int
    total: int
    remaining: int
    percent: float
    bar: str
    equivalents: str
    logs: list[dict]


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/users/{telegram_id}")
async def get_user(telegram_id: int, db: AsyncSession = Depends(get_db)):
    user = await user_service.get_user(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "profile_complete": user.profile_complete,
        "daily_calories": user.daily_calories,
        "weight": user.weight,
        "target_weight": user.target_weight,
    }


@router.post("/users/profile")
async def update_profile(body: UserProfileRequest, db: AsyncSession = Depends(get_db)):
    user = await user_service.update_user_profile(
        db,
        telegram_id=body.telegram_id,
        age=body.age,
        gender=body.gender,
        weight=body.weight,
        height=body.height,
        target_weight=body.target_weight,
        activity_level=body.activity_level,
    )
    return {"daily_calories": user.daily_calories}


@router.get("/progress/{telegram_id}/today", response_model=TodayProgressResponse)
async def today_progress(telegram_id: int, db: AsyncSession = Depends(get_db)):
    user = await user_service.get_user(db, telegram_id)
    if not user or not user.profile_complete:
        raise HTTPException(status_code=404, detail="User not found or profile incomplete")

    consumed = await user_service.get_today_consumed(db, user.id)
    total = user.daily_calories or 2000
    remaining = max(total - consumed, 0)
    percent = round(min(consumed / total * 100, 100), 1) if total else 0

    logs = await user_service.get_today_logs(db, user.id)
    logs_data = [
        {
            "id": log.id,
            "description": log.food_description,
            "calories": log.calories,
            "time": log.created_at.strftime("%H:%M"),
        }
        for log in logs
    ]

    return TodayProgressResponse(
        consumed=consumed,
        total=total,
        remaining=remaining,
        percent=percent,
        bar=format_progress_bar(consumed, total),
        equivalents=get_food_equivalents(consumed),
        logs=logs_data,
    )
