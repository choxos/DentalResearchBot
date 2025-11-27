"""Onboarding handlers for user profile setup."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database.repository import Repository
from src.config import EDUCATION_LEVELS, SPECIALTIES

logger = logging.getLogger(__name__)

# Translations
TEXTS = {
    "en": {
        "language_set": "✅ Language set to English!\n\nNow, let's set your education level.",
        "select_education": "What is your current role in dentistry?",
        "select_year": "Which year are you in?",
        "select_specialty": "What is your specialty?",
        "onboarding_complete": "✅ *Profile setup complete!*\n\nNow let's subscribe you to some journals. Use /journals to select journals you're interested in.\n\nYou'll receive tailored summaries of new articles based on your education level.",
        "education_levels": {
            "dds_student": "🎓 DDS Student",
            "general_dentist": "👨‍⚕️ General Dentist",
            "resident": "📚 Specialty Resident",
            "specialist": "🏆 Specialist",
            "faculty": "👨‍🏫 Faculty/Professor",
        },
    },
    "fa": {
        "language_set": "✅ زبان فارسی انتخاب شد.\n\nاکنون لطفاً سطح تحصیلات خود را تعیین کنید.",
        "select_education": "موقعیت فعلی شما در حوزه دندانپزشکی چیست؟",
        "select_year": "در حال تحصیل در کدام سال هستید؟",
        "select_specialty": "تخصص شما چیست؟",
        "onboarding_complete": "✅ *تنظیم پروفایل با موفقیت انجام شد!*\n\nحالا نوبت انتخاب مجلات است. با دستور /journals مجلات مورد نظر خود را انتخاب کنید.\n\nشما خلاصه‌ای اختصاصی از جدیدترین مقالات را متناسب با سطح علمی خود دریافت خواهید کرد.",
        "education_levels": {
            "dds_student": "🎓 دانشجوی دندانپزشکی",
            "general_dentist": "👨‍⚕️ دندانپزشک عمومی",
            "resident": "📚 دستیار تخصصی",
            "specialist": "🏆 متخصص",
            "faculty": "👨‍🏫 هیئت علمی/استاد",
        },
    },
}


class OnboardingHandler:
    """Handler for user onboarding process."""

    def __init__(self, repository: Repository):
        self.repository = repository

    def get_text(self, key: str, language: str = "en") -> str:
        """Get translated text."""
        lang_texts = TEXTS.get(language, TEXTS["en"])
        return lang_texts.get(key, TEXTS["en"].get(key, key))

    async def handle_language_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle language selection callback."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        data = query.data.split(":")
        if len(data) != 2:
            return

        language = data[1]  # 'en' or 'fa'

        # Update user language
        user = await self.repository.update_user(
            query.from_user.id,
            language=language,
        )

        # Show education level selection
        await self._show_education_selection(query, language)

    async def _show_education_selection(self, query, language: str) -> None:
        """Show education level selection keyboard."""
        levels = self.get_text("education_levels", language)
        
        keyboard = []
        for key, label in levels.items():
            keyboard.append([InlineKeyboardButton(label, callback_data=f"edu:{key}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"{self.get_text('language_set', language)}\n\n{self.get_text('select_education', language)}",
            reply_markup=reply_markup,
        )

    async def handle_education_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle education level selection callback."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        data = query.data.split(":")
        if len(data) != 2:
            return

        education_level = data[1]
        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        # Update education level
        await self.repository.update_user(
            query.from_user.id,
            education_level=education_level,
        )

        # Decide next step based on education level
        if education_level == "dds_student":
            await self._show_year_selection(query, language)
        elif education_level in ["resident", "specialist"]:
            await self._show_specialty_selection(query, language)
        else:
            await self._complete_onboarding(query, language)

    async def _show_year_selection(self, query, language: str) -> None:
        """Show year selection for DDS students."""
        keyboard = []
        row = []
        for year in range(1, 7):
            if language == "fa":
                row.append(InlineKeyboardButton(f"سال {year}", callback_data=f"year:{year}"))
            else:
                row.append(InlineKeyboardButton(f"Year {year}", callback_data=f"year:{year}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            self.get_text("select_year", language),
            reply_markup=reply_markup,
        )

    async def _show_specialty_selection(self, query, language: str) -> None:
        """Show specialty selection for residents/specialists."""
        keyboard = []
        for specialty in SPECIALTIES:
            keyboard.append([InlineKeyboardButton(specialty, callback_data=f"spec:{specialty}")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            self.get_text("select_specialty", language),
            reply_markup=reply_markup,
        )

    async def handle_year_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle year selection callback."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        data = query.data.split(":")
        if len(data) != 2:
            return

        year = int(data[1])
        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        # Update year
        await self.repository.update_user(
            query.from_user.id,
            education_year=year,
        )

        await self._complete_onboarding(query, language)

    async def handle_specialty_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle specialty selection callback."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        data = query.data.split(":", 1)
        if len(data) != 2:
            return

        specialty = data[1]
        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        # Update specialty
        await self.repository.update_user(
            query.from_user.id,
            specialty=specialty,
        )

        await self._complete_onboarding(query, language)

    async def _complete_onboarding(self, query, language: str) -> None:
        """Complete the onboarding process."""
        await self.repository.update_user(
            query.from_user.id,
            onboarding_complete=True,
        )

        # Transition directly to Journal Selection
        from src.bot.handlers.journals import JournalsHandler
        handler = JournalsHandler(self.repository)
        await handler.show_categories(language, query=query)

    async def handle_settings_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle settings menu callbacks."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        data = query.data.split(":")
        if len(data) != 2:
            return

        setting = data[1]
        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        if setting == "language":
            keyboard = [
                [
                    InlineKeyboardButton("🇬🇧 English", callback_data="setlang:en"),
                    InlineKeyboardButton("🇮🇷 فارسی", callback_data="setlang:fa"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            text = "Select language:" if language == "en" else "زبان را انتخاب کنید:"
            await query.edit_message_text(text, reply_markup=reply_markup)

        elif setting == "education":
            await self._show_education_selection(query, language)

        elif setting == "journals":
            # Redirect to journals command
            if language == "fa":
                await query.edit_message_text("از دستور /journals برای مدیریت اشتراک‌ها استفاده کنید.")
            else:
                await query.edit_message_text("Use the /journals command to manage your subscriptions.")

    async def handle_setlang_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle language change from settings."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        data = query.data.split(":")
        if len(data) != 2:
            return

        language = data[1]

        await self.repository.update_user(
            query.from_user.id,
            language=language,
        )

        if language == "fa":
            await query.edit_message_text("✅ زبان به فارسی تغییر کرد.")
        else:
            await query.edit_message_text("✅ Language changed to English.")
