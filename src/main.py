"""Main entry point for DentalResearchBot."""

import logging
import sys
import asyncio

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler as TelegramCommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from src.config import get_settings, load_journals
from src.database.repository import Repository
from src.services.openrouter import OpenRouterClient, close_openrouter_client
from src.services.feed_parser import FeedParser, close_feed_parser
from src.services.abstract_scraper import AbstractScraper, close_abstract_scraper
from src.services.grok_tailoring import GrokTailoringService
from src.services.scheduler import init_scheduler, get_scheduler
from src.bot.handlers.commands import CommandHandler
from src.bot.handlers.onboarding import OnboardingHandler
from src.bot.handlers.journals import JournalsHandler
from src.bot.handlers.articles import ArticlesHandler
from src.bot.handlers.export import ExportHandler

# Global instances
repository = None
openrouter_client = None
feed_parser = None
abstract_scraper = None
tailoring_service = None
scheduler = None


def setup_logging() -> None:
    """Configure logging for the application."""
    settings = get_settings()

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def send_message_to_user(telegram_id: int, text: str) -> None:
    """Send a message to a user (callback for scheduler)."""
    # This will be set up with the application context
    pass


async def post_init(application: Application) -> None:
    """Initialize resources after application starts."""
    global repository, openrouter_client, feed_parser, abstract_scraper, tailoring_service, scheduler

    logger = logging.getLogger(__name__)
    logger.info("Initializing DentalResearchBot...")

    settings = get_settings()

    # Initialize core services
    repository = Repository(settings.database_url)
    await repository.init_db()
    logger.info("Database initialized")

    # Initialize journals from CSV
    journals = load_journals()
    await repository.init_journals_from_config(journals)
    logger.info(f"Loaded {len(journals)} journals")

    # Initialize API clients
    openrouter_client = OpenRouterClient()
    feed_parser = FeedParser()
    abstract_scraper = AbstractScraper()
    tailoring_service = GrokTailoringService(openrouter_client)
    
    # Create send message callback
    async def send_message_callback(telegram_id: int, text: str, reply_markup=None) -> None:
        try:
            await application.bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send markdown message, retrying plain text: {e}")
            try:
                await application.bot.send_message(
                    chat_id=telegram_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=None,
                    disable_web_page_preview=True,
                )
            except Exception as e2:
                logger.error(f"Error sending message to {telegram_id}: {e2}")

    # Initialize and start scheduler
    scheduler = init_scheduler(
        repository=repository,
        feed_parser=feed_parser,
        abstract_scraper=abstract_scraper,
        tailoring_service=tailoring_service,
        send_message_callback=send_message_callback,
    )
    scheduler.start()
    logger.info("Feed scheduler started")

    # Start background feed sync
    asyncio.create_task(scheduler.sync_all_feeds_silent())
    logger.info("Started background feed sync")

    # Set bot commands
    commands = [
        BotCommand("start", "Start bot & setup profile"),
        BotCommand("latest", "Get latest articles"),
        BotCommand("journals", "Manage subscriptions"),
        BotCommand("settings", "User settings"),
        BotCommand("link", "Summarize article URL"),
        BotCommand("help", "Show help"),
    ]
    await application.bot.set_my_commands(commands)

    # Create handlers
    command_handler = CommandHandler(repository)
    onboarding_handler = OnboardingHandler(repository)
    journals_handler = JournalsHandler(repository)
    journals_handler.set_services(tailoring_service, feed_parser, abstract_scraper)
    articles_handler = ArticlesHandler(
        repository=repository,
        tailoring_service=tailoring_service,
        feed_parser=feed_parser,
        abstract_scraper=abstract_scraper,
    )
    export_handler = ExportHandler(repository)

    # Store handlers in bot_data
    application.bot_data["repository"] = repository
    application.bot_data["tailoring_service"] = tailoring_service

    # ===== Command Handlers =====
    application.add_handler(TelegramCommandHandler("start", command_handler.start_command))
    application.add_handler(TelegramCommandHandler("help", command_handler.help_command))
    application.add_handler(TelegramCommandHandler("settings", command_handler.settings_command))
    application.add_handler(TelegramCommandHandler("journals", journals_handler.journals_command))
    application.add_handler(TelegramCommandHandler("latest", articles_handler.latest_command))
    application.add_handler(TelegramCommandHandler("link", articles_handler.link_command))

    # ===== Callback Query Handlers =====
    # Language selection
    application.add_handler(CallbackQueryHandler(
        onboarding_handler.handle_language_callback, pattern="^lang:"
    ))
    # Education level selection
    application.add_handler(CallbackQueryHandler(
        onboarding_handler.handle_education_callback, pattern="^edu:"
    ))
    # Year selection (DDS students)
    application.add_handler(CallbackQueryHandler(
        onboarding_handler.handle_year_callback, pattern="^year:"
    ))
    # Specialty selection
    application.add_handler(CallbackQueryHandler(
        onboarding_handler.handle_specialty_callback, pattern="^spec:"
    ))
    # Settings menu
    application.add_handler(CallbackQueryHandler(
        onboarding_handler.handle_settings_callback, pattern="^settings:"
    ))
    # Language change from settings
    application.add_handler(CallbackQueryHandler(
        onboarding_handler.handle_setlang_callback, pattern="^setlang:"
    ))
    # Journal category selection
    application.add_handler(CallbackQueryHandler(
        journals_handler.handle_category_callback, pattern="^jcat:"
    ))
    # Journal subscription toggle
    application.add_handler(CallbackQueryHandler(
        journals_handler.handle_journal_callback, pattern="^journal:"
    ))
    # Fetch articles after subscribe
    application.add_handler(CallbackQueryHandler(
        journals_handler.handle_fetch_callback, pattern="^jfetch:"
    ))
    # Skip fetch after subscribe
    application.add_handler(CallbackQueryHandler(
        journals_handler.handle_skip_callback, pattern="^jskip:"
    ))
    # Back to categories
    application.add_handler(CallbackQueryHandler(
        journals_handler.handle_back_callback, pattern="^jback"
    ))
    # Journal done button
    application.add_handler(CallbackQueryHandler(
        journals_handler.handle_done_callback, pattern="^jdone"
    ))
    # Export handlers
    application.add_handler(CallbackQueryHandler(
        export_handler.handle_export_callback, pattern="^export:"
    ))

    # ===== Message Handlers =====
    # Handle messages with article links (Private and Groups)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.Entity("url") | filters.Entity("text_link")),
        articles_handler.handle_message_with_link,
    ))

    logger.info("All handlers registered")
    logger.info(f"Bot is ready! Using model: {settings.openrouter_default_model}")


async def post_shutdown(application: Application) -> None:
    """Cleanup resources on shutdown."""
    global repository, scheduler

    logger = logging.getLogger(__name__)
    logger.info("Shutting down DentalResearchBot...")

    # Stop scheduler
    if scheduler:
        scheduler.stop()

    # Close services
    await close_openrouter_client()
    await close_feed_parser()
    await close_abstract_scraper()

    if repository:
        await repository.close()

    logger.info("Cleanup complete")


def main() -> None:
    """Run the bot."""
    setup_logging()
    logger = logging.getLogger(__name__)

    settings = get_settings()

    logger.info("Starting DentalResearchBot...")
    logger.info(f"Model: {settings.openrouter_default_model}")
    logger.info(f"Feed check interval: {settings.feed_check_interval_hours} hour(s)")

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

