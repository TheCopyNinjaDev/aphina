"""
Calorie and nutrition calculation utilities.
Uses Mifflin-St Jeor equation for BMR, then applies TDEE multiplier.
"""

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,       # Little or no exercise
    "light": 1.375,         # Light exercise 1-3 days/week
    "moderate": 1.55,       # Moderate exercise 3-5 days/week
    "active": 1.725,        # Hard exercise 6-7 days/week
    "very_active": 1.9,     # Very hard exercise, physical job
}

ACTIVITY_LABELS = {
    "sedentary": "Сидячий образ жизни",
    "light": "Лёгкая активность (1-3 дня в неделю)",
    "moderate": "Умеренная активность (3-5 дней в неделю)",
    "active": "Высокая активность (6-7 дней в неделю)",
    "very_active": "Очень высокая активность / физическая работа",
}

# Fun food equivalents for progress display (kcal per item)
FOOD_EQUIVALENTS = {
    "🍫 сникерсов": 215,
    "🍎 яблок": 95,
    "🥚 яиц": 77,
    "🍕 кусков пиццы": 285,
    "🥑 авокадо": 234,
    "🍌 бананов": 105,
    "🥤 колы (0.5л)": 210,
    "🍗 куриных грудок": 165,
}


def calculate_bmr(weight: float, height: float, age: int, gender: str) -> float:
    """Mifflin-St Jeor BMR equation."""
    if gender == "male":
        return 10 * weight + 6.25 * height - 5 * age + 5
    else:
        return 10 * weight + 6.25 * height - 5 * age - 161


def calculate_daily_calories(
    weight: float,
    height: float,
    age: int,
    gender: str,
    activity_level: str,
    target_weight: float,
) -> int:
    """Calculate target daily calories based on goal."""
    bmr = calculate_bmr(weight, height, age, gender)
    tdee = bmr * ACTIVITY_MULTIPLIERS.get(activity_level, 1.375)

    if target_weight < weight:
        # Weight loss: 500 kcal deficit (≈ 0.5 kg/week), minimum 1200 kcal
        daily = max(tdee - 500, 1200)
    elif target_weight > weight:
        # Weight gain: 300 kcal surplus
        daily = tdee + 300
    else:
        # Maintenance
        daily = tdee

    return round(daily)


def generate_milestones(current_weight: float, target_weight: float) -> list[float]:
    """Generate milestone weights between current and target."""
    milestones = []
    diff = abs(current_weight - target_weight)

    if diff < 1:
        return []

    # Step size: 2kg for small goals, 5kg for larger
    step = 2.0 if diff <= 10 else 5.0

    if target_weight < current_weight:
        milestone = current_weight - step
        while milestone > target_weight:
            milestones.append(round(milestone, 1))
            milestone -= step
        milestones.append(target_weight)
    else:
        milestone = current_weight + step
        while milestone < target_weight:
            milestones.append(round(milestone, 1))
            milestone += step
        milestones.append(target_weight)

    return milestones[:10]  # Cap at 10 milestones


def format_progress_bar(consumed: int, total: int, width: int = 20) -> str:
    """Create a visual progress bar."""
    if total == 0:
        return "░" * width
    ratio = min(consumed / total, 1.0)
    filled = int(ratio * width)
    return "█" * filled + "░" * (width - filled)


def get_food_equivalents(calories: int) -> str:
    """Return a fun breakdown of calorie equivalents."""
    lines = []
    for name, kcal in list(FOOD_EQUIVALENTS.items())[:3]:
        count = round(calories / kcal, 1)
        lines.append(f"  {name}: {count}")
    return "\n".join(lines)


def estimate_weeks_to_goal(current: float, target: float, daily_calories: int, weight: float, height: float, age: int, gender: str, activity: str) -> int:
    """Estimate weeks to reach target weight."""
    bmr = calculate_bmr(weight, height, age, gender)
    tdee = bmr * ACTIVITY_MULTIPLIERS.get(activity, 1.375)
    deficit_per_day = tdee - daily_calories
    if deficit_per_day <= 0:
        return 0
    kg_per_week = (deficit_per_day * 7) / 7700  # 7700 kcal ≈ 1 kg
    if kg_per_week <= 0:
        return 0
    return round(abs(current - target) / kg_per_week)
