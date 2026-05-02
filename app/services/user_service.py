from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models import User, FoodLog, Milestone
from app.services.calorie_service import (
    calculate_daily_calories,
    generate_milestones,
)


async def get_or_create_user(db: AsyncSession, telegram_id: int, username: str | None = None, first_name: str | None = None) -> User:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def get_user(db: AsyncSession, telegram_id: int) -> User | None:
    result = await db.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
        .options(selectinload(User.milestones))
    )
    return result.scalar_one_or_none()


async def update_user_profile(
    db: AsyncSession,
    telegram_id: int,
    age: int,
    gender: str,
    weight: float,
    height: float,
    target_weight: float,
    activity_level: str,
) -> User:
    user = await get_user(db, telegram_id)
    if not user:
        raise ValueError(f"User {telegram_id} not found")

    user.age = age
    user.gender = gender
    user.weight = weight
    user.height = height
    user.target_weight = target_weight
    user.activity_level = activity_level
    user.daily_calories = calculate_daily_calories(weight, height, age, gender, activity_level, target_weight)
    user.profile_complete = True

    # Remove old milestones and create new ones
    result = await db.execute(select(Milestone).where(Milestone.user_id == user.id))
    for m in result.scalars().all():
        await db.delete(m)

    milestone_weights = generate_milestones(weight, target_weight)
    for mw in milestone_weights:
        db.add(Milestone(user_id=user.id, target_weight=mw))

    await db.commit()
    await db.refresh(user)
    return user


async def get_today_consumed(db: AsyncSession, user_id: int) -> int:
    today = date.today()
    result = await db.execute(
        select(func.sum(FoodLog.calories))
        .where(FoodLog.user_id == user_id)
        .where(FoodLog.date == today)
        .where(FoodLog.confirmed == True)  # noqa: E712
    )
    return result.scalar() or 0


async def add_food_log(
    db: AsyncSession,
    user_id: int,
    food_description: str,
    calories: int,
    photo_file_id: str | None = None,
    confirmed: bool = False,
) -> FoodLog:
    log = FoodLog(
        user_id=user_id,
        food_description=food_description,
        calories=calories,
        photo_file_id=photo_file_id,
        confirmed=confirmed,
        date=date.today(),
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def confirm_food_log(db: AsyncSession, log_id: int) -> FoodLog | None:
    result = await db.execute(select(FoodLog).where(FoodLog.id == log_id))
    log = result.scalar_one_or_none()
    if log:
        log.confirmed = True
        await db.commit()
        await db.refresh(log)
    return log


async def get_today_logs(db: AsyncSession, user_id: int) -> list[FoodLog]:
    today = date.today()
    result = await db.execute(
        select(FoodLog)
        .where(FoodLog.user_id == user_id)
        .where(FoodLog.date == today)
        .where(FoodLog.confirmed == True)  # noqa: E712
        .order_by(FoodLog.created_at)
    )
    return list(result.scalars().all())


async def check_milestones(db: AsyncSession, user: User) -> list[Milestone]:
    """Check and mark achieved milestones. Returns newly achieved ones."""
    achieved = []
    if user.weight is None or user.target_weight is None:
        return achieved

    result = await db.execute(
        select(Milestone)
        .where(Milestone.user_id == user.id)
        .where(Milestone.achieved == False)  # noqa: E712
        .where(Milestone.notified == False)
    )
    milestones = result.scalars().all()

    losing = user.target_weight < user.weight

    for milestone in milestones:
        reached = (
            (losing and user.weight <= milestone.target_weight)
            or (not losing and user.weight >= milestone.target_weight)
        )
        if reached:
            from datetime import datetime
            milestone.achieved = True
            milestone.achieved_at = datetime.utcnow()
            milestone.notified = True
            achieved.append(milestone)

    if achieved:
        await db.commit()

    return achieved
