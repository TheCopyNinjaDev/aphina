from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/aphina"

    BOT_TOKEN: str = ""
    BOT_PASSWORD: str = "secret"

    # OpenRouter — all AI calls go through here
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Models (all via OpenRouter)
    VISION_MODEL: str = "openai/gpt-4o"          # food photo analysis
    TEXT_MODEL: str = "openai/gpt-4o"             # recipe text
    IMAGE_MODEL: str = "openai/dall-e-3"          # recipe illustration
    TRANSCRIPTION_MODEL: str = "google/gemini-2.0-flash-001"  # voice → text (supports audio)

    APP_NAME: str = "Aphina Calorie Tracker"
    APP_URL: str = "http://localhost:8000"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
