"""Basic command handlers for the bot."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database.repository import Repository
from src.config import EDUCATION_LEVELS, SPECIALTIES

logger = logging.getLogger(__name__)

# Translations
TEXTS = {
    "en": {
        "welcome": "🦷 *Welcome to DentalResearchBot!*\n\nI help dental professionals stay updated with the latest research, tailored to your education level.\n\nLet's set up your profile first.",
        "select_language": "Please select your preferred language:",
        "help": """*DentalResearchBot Help*

*Commands:*
/start - Start the bot and set up your profile
/settings - Change your preferences
/journals - Manage journal subscriptions
/latest - Get latest articles from your subscriptions
/link <url> - Get a tailored summary of any article
/help - Show this help message

*How it works:*
1. Set your language and education level
2. Subscribe to journals you're interested in
3. Receive tailored summaries when new articles are published

The bot will automatically tailor the content based on your education level - simpler language for students, more technical for specialists.""",
        "settings_updated": "✅ Settings updated successfully!",
        "not_onboarded": "Please complete your profile first with /start",
    },
    "fa": {
        "welcome": "🦷 *به DentalResearchBot خوش آمدید!*\n\nاین ربات به دندانپزشکان و دانشجویان کمک می‌کند تا از جدیدترین مقالات علمی، متناسب با سطح دانش خود آگاه شوند.\n\nلطفاً برای شروع، پروفایل خود را تنظیم کنید.",
        "select_language": "لطفاً زبان مورد نظر خود را انتخاب کنید:",
        "help": """*راهنمای استفاده از DentalResearchBot*

*دستورات:*
/start - اجرای ربات و تنظیم پروفایل کاربری
/settings - تغییر تنظیمات کاربری
/journals - مدیریت اشتراک مجلات
/latest - دریافت آخرین مقالات از اشتراک‌های فعال
/link <آدرس> - دریافت خلاصه اختصاصی برای هر مقاله
/help - نمایش همین راهنما

*راهنمای استفاده:*
۱. زبان و سطح تحصیلات خود را تنظیم کنید.
۲. مجلات علمی مورد علاقه خود را انتخاب نمایید.
۳. با انتشار مقالات جدید، خلاصه آن‌ها را دریافت کنید.

ربات به صورت هوشمند، محتوای علمی را بر اساس سطح دانش و تخصص شما ساده‌سازی و متناسب می‌کند.""",
        "settings_updated": "✅ تنظیمات با موفقیت به‌روزرسانی شد!",
        "not_onboarded": "لطفاً ابتدا با دستور /start پروفایل خود را تکمیل کنید.",
    },
}


class CommandHandler:
    """Handler for basic bot commands."""

    def __init__(self, repository: Repository):
        self.repository = repository

    def get_text(self, key: str, language: str = "en") -> str:
        """Get translated text."""
        return TEXTS.get(language, TEXTS["en"]).get(key, TEXTS["en"].get(key, key))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command - begin onboarding."""
        if not update.effective_user or not update.message:
            return

        user_id = update.effective_user.id
        
        # Create or get user
        user = await self.repository.get_or_create_user(
            telegram_id=user_id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )

        # Show language selection
        keyboard = [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
                InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang:fa"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            self.get_text("select_language", user.language),
            reply_markup=reply_markup,
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not update.effective_user or not update.message:
            return

        user = await self.repository.get_user(update.effective_user.id)
        language = user.language if user else "en"

        await update.message.reply_text(
            self.get_text("help", language),
            parse_mode="Markdown",
        )

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /settings command."""
        if not update.effective_user or not update.message:
            return

        user = await self.repository.get_user(update.effective_user.id)
        
        if not user or not user.onboarding_complete:
            await update.message.reply_text(
                self.get_text("not_onboarded", user.language if user else "en")
            )
            return

        language = user.language

        # Show settings menu
        if language == "fa":
            keyboard = [
                [InlineKeyboardButton("🌐 زبان", callback_data="settings:language")],
                [InlineKeyboardButton("🎓 سطح تحصیلات", callback_data="settings:education")],
                [InlineKeyboardButton("📚 مجلات", callback_data="settings:journals")],
            ]
            text = "*تنظیمات فعلی:*\n\n"
            text += f"🌐 زبان: فارسی\n"
            text += f"🎓 سطح: {user.education_level or 'تنظیم نشده'}\n"
            if user.specialty:
                text += f"📋 تخصص: {user.specialty}\n"
            if user.education_year:
                text += f"📅 سال: {user.education_year}\n"
        else:
            keyboard = [
                [InlineKeyboardButton("🌐 Language", callback_data="settings:language")],
                [InlineKeyboardButton("🎓 Education Level", callback_data="settings:education")],
                [InlineKeyboardButton("📚 Journals", callback_data="settings:journals")],
            ]
            text = "*Current Settings:*\n\n"
            text += f"🌐 Language: English\n"
            text += f"🎓 Level: {user.education_level or 'Not set'}\n"
            if user.specialty:
                text += f"📋 Specialty: {user.specialty}\n"
            if user.education_year:
                text += f"📅 Year: {user.education_year}\n"

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
