"""Configuration management for DentalResearchBot."""

import json
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str

    # OpenRouter
    openrouter_api_key: str
    openrouter_default_model: str = "x-ai/grok-4.1-fast:free"

    # Database
    database_url: str = "postgresql+asyncpg://dentalbot:dentalbot_secret@localhost:5432/dentalbot_db"

    # Bot Configuration
    admin_user_ids: str = "[]"
    feed_check_interval_hours: int = 1

    # Application
    log_level: str = "INFO"

    @property
    def admin_ids(self) -> List[int]:
        """Parse admin user IDs from JSON string."""
        try:
            return json.loads(self.admin_user_ids)
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def openrouter_base_url(self) -> str:
        """OpenRouter API base URL."""
        return "https://openrouter.ai/api/v1"


# Education levels for user selection
EDUCATION_LEVELS = {
    "dds_student": {
        "name_en": "DDS Student",
        "name_fa": "دانشجوی دندانپزشکی",
        "years": ["1", "2", "3", "4", "5", "6"],
    },
    "general_dentist": {
        "name_en": "General Dentist",
        "name_fa": "دندانپزشک عمومی",
    },
    "resident": {
        "name_en": "Specialty Resident",
        "name_fa": "دستیار تخصصی",
    },
    "specialist": {
        "name_en": "Specialist",
        "name_fa": "متخصص",
    },
    "faculty": {
        "name_en": "Faculty/Professor",
        "name_fa": "هیئت علمی/استاد",
    },
}

# Dental specialties
SPECIALTIES = [
    "Orthodontics",
    "Periodontics",
    "Prosthodontics",
    "Endodontics",
    "Oral and Maxillofacial Surgery",
    "Restorative Dentistry",
    "Oral and Maxillofacial Radiology",
    "Oral and Maxillofacial Pathology",
    "Pediatric Dentistry",
    "Oral Medicine",
    "Community Oral Health",
    "Dental Materials",
]


def load_journals() -> List[Dict[str, str]]:
    """Load journals from CSV file."""
    import csv
    journals = []
    journals_path = Path(__file__).parent.parent / "journals.csv"
    
    if journals_path.exists():
        with open(journals_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                journals.append({
                    "name": row["journal"],
                    "feed_url": row["link"],
                    "feed_type": row["type"],
                    "category": row.get("category", "General"),
                })
    return journals


# Journal categories with icons
JOURNAL_CATEGORIES = {
    "Periodontology": "🦷",
    "Endodontics": "🔬",
    "Prosthodontics": "🦿",
    "Orthodontics": "😁",
    "Oral Surgery": "🏥",
    "Implantology": "⚙️",
    "General Dentistry": "📚",
    "Oral Medicine": "💊",
    "Dental Materials": "🧪",
    "Public Health": "🌍",
    "Oral Rehabilitation": "♻️",
}

JOURNAL_CATEGORIES_FA = {
    "Periodontology": "پریودنتولوژی",
    "Endodontics": "اندودانتیکس",
    "Prosthodontics": "پروتزهای دندانی",
    "Orthodontics": "ارتودنسی",
    "Oral Surgery": "جراحی دهان، فک و صورت",
    "Implantology": "ایمپلنت",
    "General Dentistry": "دندانپزشکی عمومی",
    "Oral Medicine": "بیماری‌های دهان و فک و صورت",
    "Dental Materials": "مواد دندانی",
    "Public Health": "سلامت دهان و دندان جامعه‌نگر",
    "Oral Rehabilitation": "بازسازی دهان و دندان",
}


def load_education_data() -> Dict[str, Any]:
    """Load education structure from JSON file."""
    data_path = Path(__file__).parent.parent / "dental_education_iran.json"
    
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
