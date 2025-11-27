"""Feed checking scheduler using APScheduler."""

import logging
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.config import get_settings
from src.utils.formatting import markdown_to_telegram
from src.database.repository import Repository
from src.database.models import Journal, Article, User
from src.services.feed_parser import FeedParser
from src.services.abstract_scraper import AbstractScraper
from src.services.grok_tailoring import GrokTailoringService

logger = logging.getLogger(__name__)


class FeedScheduler:
    """Scheduler for checking feeds and delivering articles."""

    def __init__(
        self,
        repository: Repository,
        feed_parser: FeedParser,
        abstract_scraper: AbstractScraper,
        tailoring_service: GrokTailoringService,
        send_message_callback: Callable,
    ):
        self.repository = repository
        self.feed_parser = feed_parser
        self.abstract_scraper = abstract_scraper
        self.tailoring_service = tailoring_service
        self.send_message = send_message_callback
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self) -> None:
        """Start the scheduler."""
        settings = get_settings()
        interval_hours = settings.feed_check_interval_hours

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self.check_all_feeds,
            trigger=IntervalTrigger(hours=interval_hours),
            id="feed_checker",
            name="Check all feeds for new articles",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(f"Feed scheduler started, checking every {interval_hours} hour(s)")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("Feed scheduler stopped")

    async def check_all_feeds(self) -> None:
        """Check all journal feeds for new articles."""
        logger.info("Starting scheduled feed check...")
        
        journals = await self.repository.get_all_journals()
        
        total_new = 0
        for journal in journals:
            try:
                new_count = await self.check_journal_feed(journal)
                total_new += new_count
            except Exception as e:
                logger.error(f"Error checking feed for {journal.name}: {e}")
        
        logger.info(f"Feed check complete. Found {total_new} new articles.")

    async def check_journal_feed(self, journal: Journal) -> int:
        """Check a single journal feed for new articles."""
        logger.debug(f"Checking feed: {journal.name}")
        
        # Parse feed
        articles = await self.feed_parser.parse_from_url(journal.feed_url)
        
        new_count = 0
        for parsed in articles:
            # Check if article already exists
            if await self.repository.article_exists(parsed.link):
                continue
            
            abstract = parsed.abstract
            
            # Scrape abstract if needed (Nature journals)
            if journal.needs_scraping and not abstract:
                abstract = await self.abstract_scraper.scrape_abstract(parsed.link)
            
            # Create article in database
            article = await self.repository.create_article(
                journal_id=journal.id,
                title=parsed.title,
                link=parsed.link,
                abstract=abstract,
                authors=parsed.authors,
                doi=parsed.doi,
                published_date=parsed.published_date,
                volume=parsed.volume,
                issue=parsed.issue,
            )
            
            if article:
                new_count += 1
                # Notify subscribers
                await self.notify_subscribers(article, journal)
        
        # Update last checked timestamp
        await self.repository.update_journal_last_checked(journal.id)
        
        return new_count

    async def notify_subscribers(self, article: Article, journal: Journal) -> None:
        """Notify all subscribers of a new article."""
        subscribers = await self.repository.get_users_subscribed_to_journal(journal.id)
        
        for user in subscribers:
            try:
                # Check if already sent
                if await self.repository.was_article_sent_to_user(user.telegram_id, article.id):
                    continue
                
                # Tailor content
                tailored = await self.tailoring_service.tailor_article(
                    user=user,
                    article=article,
                    journal_name=journal.name,
                )
                
                if tailored:
                    # Convert to Telegram format
                    telegram_text = markdown_to_telegram(tailored)

                    # Add export buttons
                    keyboard = [
                        [
                            InlineKeyboardButton("📄 PDF", callback_data=f"export:pdf:{article.id}"),
                            InlineKeyboardButton("📝 MD", callback_data=f"export:md:{article.id}"),
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    # Send message
                    await self.send_message(user.telegram_id, telegram_text, reply_markup=reply_markup)
                    
                    # Mark as sent
                    await self.repository.mark_article_sent(
                        telegram_id=user.telegram_id,
                        article_id=article.id,
                        tailored_content=tailored, # Store Standard MD
                    )
                    
                    logger.debug(f"Sent article {article.id} to user {user.telegram_id}")
                    
            except Exception as e:
                logger.error(f"Error notifying user {user.telegram_id}: {e}")

    async def run_manual_check(self) -> int:
        """Run a manual feed check (for testing or admin commands)."""
        await self.check_all_feeds()
        return 0

    async def sync_all_feeds_silent(self) -> None:
        """Fetch and store articles from all feeds without notifying users."""
        logger.info("Starting silent feed sync...")
        journals = await self.repository.get_all_journals()
        
        total_new = 0
        for journal in journals:
            try:
                # Parse feed
                articles = await self.feed_parser.parse_from_url(journal.feed_url)
                
                for parsed in articles:
                    # Check existence
                    if await self.repository.article_exists(parsed.link):
                        continue
                    
                    # Scrape abstract if needed
                    abstract = parsed.abstract
                    if journal.needs_scraping and not abstract:
                        abstract = await self.abstract_scraper.scrape_abstract(parsed.link)
                    
                    # Create article
                    await self.repository.create_article(
                        journal_id=journal.id,
                        title=parsed.title,
                        link=parsed.link,
                        abstract=abstract,
                        authors=parsed.authors,
                        doi=parsed.doi,
                        published_date=parsed.published_date,
                        volume=parsed.volume,
                        issue=parsed.issue,
                    )
                    total_new += 1
                
                await self.repository.update_journal_last_checked(journal.id)
                
            except Exception as e:
                logger.error(f"Error syncing feed {journal.name}: {e}")
        
        logger.info(f"Silent sync complete. Stored {total_new} new articles.")


# Global scheduler instance
_scheduler: Optional[FeedScheduler] = None


def get_scheduler() -> Optional[FeedScheduler]:
    """Get scheduler instance."""
    return _scheduler


def init_scheduler(
    repository: Repository,
    feed_parser: FeedParser,
    abstract_scraper: AbstractScraper,
    tailoring_service: GrokTailoringService,
    send_message_callback: Callable,
) -> FeedScheduler:
    """Initialize and return scheduler."""
    global _scheduler
    _scheduler = FeedScheduler(
        repository=repository,
        feed_parser=feed_parser,
        abstract_scraper=abstract_scraper,
        tailoring_service=tailoring_service,
        send_message_callback=send_message_callback,
    )
    return _scheduler

