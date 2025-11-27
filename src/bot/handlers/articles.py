"""Article delivery and custom link handlers."""

import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database.repository import Repository
from src.services.grok_tailoring import GrokTailoringService
from src.services.feed_parser import FeedParser
from src.services.abstract_scraper import AbstractScraper
from src.utils.formatting import markdown_to_telegram

logger = logging.getLogger(__name__)

# URL pattern
URL_PATTERN = re.compile(r'https?://[^\s]+')

# Texts
TEXTS = {
    "en": {
        "not_onboarded": "Please complete your profile first with /start",
        "no_subscriptions": "You don't have any journal subscriptions.\n\nUse /journals to subscribe to journals first.",
        "no_new_articles": "No new articles from your subscribed journals.\n\nCheck back later or use /journals to subscribe to more journals.",
        "fetching_latest": "📚 Fetching latest articles from your subscriptions...",
        "processing_link": "🔄 Processing article...",
        "link_usage": "Please provide an article URL:\n\n`/link https://example.com/article`",
        "error_processing": "❌ Error processing the article. Please try again.",
        "article_not_found": "❌ Could not find or access the article at this URL.",
        "export_options": "Export as:",
    },
    "fa": {
        "not_onboarded": "لطفاً ابتدا با استفاده از دستور /start پروفایل خود را تکمیل نمایید.",
        "no_subscriptions": "شما هیچ اشتراک فعالی ندارید.\n\nلطفاً ابتدا با دستور /journals مجلات مورد نظر را انتخاب کنید.",
        "no_new_articles": "مقاله جدیدی در مجلات منتخب شما یافت نشد.\n\nمی‌توانید بعداً مجدداً بررسی کنید یا با /journals منابع بیشتری اضافه نمایید.",
        "fetching_latest": "📚 در حال جستجو برای آخرین مقالات در اشتراک‌های شما...",
        "processing_link": "🔄 در حال پردازش و آماده‌سازی مقاله...",
        "link_usage": "لطفاً لینک مقاله را به صورت زیر ارسال کنید:\n\n`/link https://example.com/article`",
        "error_processing": "❌ خطا در پردازش مقاله. لطفاً مجدداً تلاش کنید.",
        "article_not_found": "❌ دسترسی به مقاله در این آدرس امکان‌پذیر نشد.",
        "export_options": "خروجی به صورت:",
    },
}


class ArticlesHandler:
    """Handler for article delivery."""

    def __init__(
        self,
        repository: Repository,
        tailoring_service: GrokTailoringService,
        feed_parser: FeedParser,
        abstract_scraper: AbstractScraper,
    ):
        self.repository = repository
        self.tailoring_service = tailoring_service
        self.feed_parser = feed_parser
        self.abstract_scraper = abstract_scraper

    def get_text(self, key: str, language: str = "en") -> str:
        """Get translated text."""
        return TEXTS.get(language, TEXTS["en"]).get(key, TEXTS["en"].get(key, key))

    async def _send_tailored_message(self, update: Update, text: str, reply_markup: InlineKeyboardMarkup) -> None:
        """Send message with fallback for markdown parsing errors."""
        try:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send markdown message, retrying plain text: {e}")
            try:
                await update.message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=None,
                    disable_web_page_preview=True,
                )
            except Exception as e2:
                logger.error(f"Failed to send message: {e2}")

    async def latest_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /latest command - get latest articles from subscriptions."""
        if not update.effective_user or not update.message:
            return

        user = await self.repository.get_user(update.effective_user.id)
        
        if not user or not user.onboarding_complete:
            language = user.language if user else "en"
            await update.message.reply_text(self.get_text("not_onboarded", language))
            return

        language = user.language

        # Check subscriptions
        subscriptions = await self.repository.get_user_subscriptions(user.telegram_id)
        if not subscriptions:
            await update.message.reply_text(self.get_text("no_subscriptions", language))
            return

        # Send loading message
        loading_msg = await update.message.reply_text(self.get_text("fetching_latest", language))

        # Get unsent articles
        articles = await self.repository.get_unsent_articles_for_user(user.telegram_id)
        
        if not articles:
            await loading_msg.edit_text(self.get_text("no_new_articles", language))
            return

        # Delete loading message
        await loading_msg.delete()

        # Send each article (limit to 5 at a time)
        for article in articles[:5]:
            try:
                # Get journal name
                journal_name = article.journal.name if article.journal else "Unknown"
                
                # Tailor content
                tailored = await self.tailoring_service.tailor_article(
                    user=user,
                    article=article,
                    journal_name=journal_name,
                )
                
                if tailored:
                    # Convert to Telegram format for display
                    telegram_text = markdown_to_telegram(tailored)
                    
                    # Add export buttons
                    keyboard = [
                        [
                            InlineKeyboardButton("📄 PDF", callback_data=f"export:pdf:{article.id}"),
                            InlineKeyboardButton("📝 MD", callback_data=f"export:md:{article.id}"),
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await self._send_tailored_message(update, telegram_text, reply_markup)
                    
                    # Mark as sent
                    await self.repository.mark_article_sent(
                        telegram_id=user.telegram_id,
                        article_id=article.id,
                        tailored_content=tailored, # Store standard Markdown
                    )
                    
            except Exception as e:
                logger.error(f"Error sending article {article.id}: {e}")

    async def link_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /link command - process a custom article URL."""
        if not update.effective_user or not update.message:
            return

        user = await self.repository.get_user(update.effective_user.id)
        
        if not user or not user.onboarding_complete:
            language = user.language if user else "en"
            await update.message.reply_text(self.get_text("not_onboarded", language))
            return

        language = user.language

        # Get URL from command arguments
        if not context.args:
            await update.message.reply_text(
                self.get_text("link_usage", language),
                parse_mode="Markdown",
            )
            return

        url = context.args[0]
        
        # Validate URL
        if not URL_PATTERN.match(url):
            await update.message.reply_text(
                self.get_text("link_usage", language),
                parse_mode="Markdown",
            )
            return

        # Send processing message
        processing_msg = await update.message.reply_text(self.get_text("processing_link", language))

        try:
            # Try to scrape abstract from the page
            abstract = await self.abstract_scraper.scrape_abstract(url)
            
            if not abstract:
                await processing_msg.edit_text(self.get_text("article_not_found", language))
                return
            
            # Extract title from URL or use generic
            title = self._extract_title_from_url(url)
            
            # Detect journal from URL
            journal_name = self._detect_journal_from_url(url)
            
            # Tailor content
            tailored = await self.tailoring_service.tailor_custom_article(
                user=user,
                title=title,
                abstract=abstract,
                link=url,
                journal_name=journal_name,
            )
            
            if tailored:
                # Delete processing message
                await processing_msg.delete()
                
                # Convert to Telegram format for display
                telegram_text = markdown_to_telegram(tailored)
                
                # Add export buttons
                keyboard = [
                    [
                        InlineKeyboardButton("📄 PDF", callback_data=f"export:pdf:custom"),
                        InlineKeyboardButton("📝 MD", callback_data=f"export:md:custom"),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Store tailored content for export
                context.user_data["last_custom_article"] = tailored
                
                await self._send_tailored_message(update, telegram_text, reply_markup)
            else:
                await processing_msg.edit_text(self.get_text("error_processing", language))
                
        except Exception as e:
            logger.error(f"Error processing link {url}: {e}")
            await processing_msg.edit_text(self.get_text("error_processing", language))

    def _extract_title_from_url(self, url: str) -> str:
        """Extract a readable title from URL."""
        # Try to get the last part of the path
        from urllib.parse import urlparse, unquote
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        if path:
            # Get last segment
            last_segment = path.split('/')[-1]
            # Clean it up
            last_segment = unquote(last_segment)
            last_segment = last_segment.replace('-', ' ').replace('_', ' ')
            # Remove file extension
            if '.' in last_segment:
                last_segment = last_segment.rsplit('.', 1)[0]
            return last_segment.title()
        return "Article"

    def _detect_journal_from_url(self, url: str) -> str:
        """Detect journal name from URL."""
        url_lower = url.lower()
        
        journal_patterns = {
            "nature.com": "Nature",
            "wiley.com": "Wiley Journal",
            "sciencedirect.com": "ScienceDirect",
            "sagepub.com": "Sage Journal",
            "oup.com": "Oxford University Press",
            "karger.com": "Karger",
            "ada.org": "ADA Journal",
            "aap.org": "AAP Journal",
        }
        
        for pattern, name in journal_patterns.items():
            if pattern in url_lower:
                return name
        
        return "Scientific Journal"

    async def handle_message_with_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular messages that contain links."""
        if not update.effective_user or not update.message or not update.message.text:
            return

        # Check if message contains a URL
        urls = URL_PATTERN.findall(update.message.text)
        if not urls:
            return

        user = await self.repository.get_user(update.effective_user.id)
        
        if not user or not user.onboarding_complete:
            return

        # Check if URL is an article link (not just any URL)
        url = urls[0]
        if not self._is_article_url(url):
            return

        # Process like /link command
        context.args = [url]
        await self.link_command(update, context)

    def _is_article_url(self, url: str) -> bool:
        """Check if URL appears to be a scientific article."""
        article_domains = [
            'nature.com',
            'wiley.com',
            'sciencedirect.com',
            'sagepub.com',
            'oup.com',
            'karger.com',
            'ada.org',
            'aap.org',
            'springer.com',
            'tandfonline.com',
            'elsevier.com',
            'pubmed',
            'ncbi.nlm.nih.gov',
            'doi.org',
        ]
        
        url_lower = url.lower()
        return any(domain in url_lower for domain in article_domains)
