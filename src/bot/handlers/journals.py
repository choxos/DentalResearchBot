"""Journal subscription management handlers."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database.repository import Repository
from src.config import JOURNAL_CATEGORIES, JOURNAL_CATEGORIES_FA
from src.utils.formatting import markdown_to_telegram

logger = logging.getLogger(__name__)

# Texts
TEXTS = {
    "en": {
        "not_onboarded": "Please complete your profile first with /start",
        "select_category": "📚 *Journal Categories*\n\nSelect a category to see journals:",
        "select_journals": "📚 *{category}*\n\nSelect journals to subscribe/unsubscribe.\n✅ = Subscribed",
        "subscribed": "✅ Subscribed to {journal}!",
        "unsubscribed": "❌ Unsubscribed from {journal}",
        "no_subscriptions": "You don't have any subscriptions yet.\n\nUse /journals to subscribe to journals.",
        "your_subscriptions": "📚 *Your Subscriptions:*\n\n{journals}",
        "fetch_latest_prompt": "Would you like to fetch the latest articles from this journal now?",
        "fetching_articles": "📥 Fetching latest articles from {journal}...",
        "no_articles": "No articles found in this journal yet.",
        "articles_sent": "✅ Sent {count} article(s) from {journal}!",
        "back": "⬅️ Back",
        "done": "✅ Done",
        "my_subscriptions": "⭐ My Subscriptions",
        "tap_to_unsubscribe": "📚 *Your Subscriptions*\n\nTap to unsubscribe:",
    },
    "fa": {
        "not_onboarded": "لطفاً ابتدا پروفایلتان را با /start تکمیل کنید",
        "select_category": "📚 *دسته‌بندی مجلات*\n\nلطفاً یک دسته‌بندی را جهت مشاهده مجلات انتخاب کنید:",
        "select_journals": "📚 *{category}*\n\nبرای اشتراک یا لغو اشتراک، روی نام مجله ضربه بزنید.\n✅ = اشتراک فعال",
        "subscribed": "✅ اشتراک در {journal} فعال شد!",
        "unsubscribed": "❌ اشتراک {journal} لغو گردید",
        "no_subscriptions": "شما هنوز در هیچ مجله‌ای عضو نشده‌اید.\n\nلطفاً برای عضویت از دستور /journals استفاده کنید.",
        "your_subscriptions": "📚 *فهرست اشتراک‌های شما:*\n\n{journals}",
        "fetch_latest_prompt": "آیا مایلید آخرین مقالات منتشر شده در این مجله را هم‌اکنون دریافت کنید؟",
        "fetching_articles": "📥 در حال بازیابی آخرین مقالات از {journal}...",
        "no_articles": "در حال حاضر مقاله جدیدی در این مجله یافت نشد.",
        "articles_sent": "✅ تعداد {count} مقاله از {journal} ارسال شد.",
        "back": "⬅️ بازگشت",
        "done": "✅ اتمام",
        "my_subscriptions": "⭐ اشتراک‌های من",
        "tap_to_unsubscribe": "📚 *اشتراک‌های شما*\n\nبرای لغو اشتراک ضربه بزنید:",
    },
}


class JournalsHandler:
    """Handler for journal subscription management."""

    def __init__(self, repository: Repository):
        self.repository = repository
        self.tailoring_service = None
        self.feed_parser = None
        self.abstract_scraper = None

    def set_services(self, tailoring_service, feed_parser, abstract_scraper):
        """Set additional services for fetching articles."""
        self.tailoring_service = tailoring_service
        self.feed_parser = feed_parser
        self.abstract_scraper = abstract_scraper

    def get_text(self, key: str, language: str = "en") -> str:
        """Get translated text."""
        return TEXTS.get(language, TEXTS["en"]).get(key, TEXTS["en"].get(key, key))

    async def journals_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /journals command - show journal category menu."""
        if not update.effective_user or not update.message:
            return

        user = await self.repository.get_user(update.effective_user.id)
        
        if not user or not user.onboarding_complete:
            language = user.language if user else "en"
            await update.message.reply_text(self.get_text("not_onboarded", language))
            return

        await self.show_categories(user.language, message=update.message)

    async def show_categories(self, language: str, message=None, query=None) -> None:
        """Show journal category selection."""
        categorized = await self.repository.get_journals_by_category()
        
        keyboard = []
        
        # Add "My Subscriptions" button
        keyboard.append([
            InlineKeyboardButton(self.get_text("my_subscriptions", language), callback_data="jcat:my_subs")
        ])
        
        for category in categorized.keys():
            icon = JOURNAL_CATEGORIES.get(category, "📖")
            if language == "fa":
                label = f"{icon} {JOURNAL_CATEGORIES_FA.get(category, category)}"
            else:
                label = f"{icon} {category}"
            
            count = len(categorized[category])
            keyboard.append([
                InlineKeyboardButton(f"{label} ({count})", callback_data=f"jcat:{category}")
            ])
        
        # Add done button
        keyboard.append([InlineKeyboardButton(self.get_text("done", language), callback_data="jdone")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = self.get_text("select_category", language)
        
        if query:
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        elif message:
            await message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )

    async def _show_categories(self, message, language: str) -> None:
        """Deprecated: Use show_categories instead."""
        await self.show_categories(language, message=message)

    async def handle_category_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle category selection callback."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        data = query.data.split(":", 1)
        if len(data) != 2:
            return

        category = data[1]
        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        if category == "my_subs":
            await self.show_user_subscriptions(query, language)
            return

        await self._show_journals_in_category(query, category, language)

    async def show_user_subscriptions(self, query, language: str) -> None:
        """Show user's subscribed journals."""
        subscriptions = await self.repository.get_user_subscriptions(query.from_user.id)
        
        if not subscriptions:
            await query.answer(self.get_text("no_subscriptions", language), show_alert=True)
            return

        keyboard = []
        for journal in subscriptions:
            # Add Unsubscribe button (❌ Journal Name)
            # Using a special callback format to know we are in "my_subs" view
            # journal:ID:1:my_subs (1 means is_subscribed, my_subs is the view)
            name = journal.name if len(journal.name) <= 30 else journal.name[:27] + "..."
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ {name}",
                    callback_data=f"journal:{journal.id}:1:my_subs"
                )
            ])
        
        # Back button
        keyboard.append([
            InlineKeyboardButton(self.get_text("back", language), callback_data="jback")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = self.get_text("tap_to_unsubscribe", language)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    async def _show_journals_in_category(self, query, category: str, language: str) -> None:
        """Show journals in a specific category."""
        categorized = await self.repository.get_journals_by_category()
        journals = categorized.get(category, [])
        
        # Get user's subscriptions
        subscriptions = await self.repository.get_user_subscriptions(query.from_user.id)
        subscribed_ids = {j.id for j in subscriptions}
        
        keyboard = []
        for journal in journals:
            is_subscribed = journal.id in subscribed_ids
            prefix = "✅ " if is_subscribed else "⬜ "
            # Shorten long names
            name = journal.name if len(journal.name) <= 35 else journal.name[:32] + "..."
            keyboard.append([
                InlineKeyboardButton(
                    f"{prefix}{name}",
                    callback_data=f"journal:{journal.id}:{1 if is_subscribed else 0}"
                )
            ])
        
        # Back and done buttons
        keyboard.append([
            InlineKeyboardButton(self.get_text("back", language), callback_data="jback"),
            InlineKeyboardButton(self.get_text("done", language), callback_data="jdone"),
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        cat_label = JOURNAL_CATEGORIES_FA.get(category, category) if language == "fa" else category
        text = self.get_text("select_journals", language).format(category=cat_label)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    async def handle_journal_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle journal toggle callback."""
        if not update.callback_query:
            return

        query = update.callback_query
        data = query.data.split(":")
        
        # Data format: journal:ID:is_subscribed[:view_mode]
        if len(data) < 3:
            return

        journal_id = int(data[1])
        is_subscribed = int(data[2])
        view_mode = data[3] if len(data) > 3 else "category"
        
        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        journal = await self.repository.get_journal_by_id(journal_id)
        if not journal:
            await query.answer("Journal not found")
            return

        if is_subscribed:
            # Unsubscribe
            await self.repository.unsubscribe_user_from_journal(query.from_user.id, journal_id)
            msg = self.get_text("unsubscribed", language).format(journal=journal.name)
            await query.answer(msg)
            
            if view_mode == "my_subs":
                # Refresh the my_subs list
                await self.show_user_subscriptions(query, language)
            else:
                # Refresh the category view
                await self._refresh_category_view(query, journal.category, language)
        else:
            # Subscribe
            await self.repository.subscribe_user_to_journal(query.from_user.id, journal_id)
            msg = self.get_text("subscribed", language).format(journal=journal.name)
            await query.answer(msg)
            
            # Ask if user wants to fetch latest articles
            await self._show_fetch_prompt(query, journal, language)

    async def _show_fetch_prompt(self, query, journal, language: str) -> None:
        """Show prompt to fetch latest articles after subscribing."""
        keyboard = [
            [
                InlineKeyboardButton(
                    "📥 Yes" if language == "en" else "📥 بله",
                    callback_data=f"jfetch:{journal.id}"
                ),
                InlineKeyboardButton(
                    "⏭️ Skip" if language == "en" else "⏭️ رد کردن",
                    callback_data=f"jskip:{journal.category}"
                ),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"✅ *Subscribed to {journal.name}!*\n\n" if language == "en" else f"✅ *در {journal.name} اشتراک گرفتید!*\n\n"
        text += self.get_text("fetch_latest_prompt", language)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    async def handle_fetch_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle fetch articles callback."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        data = query.data.split(":")
        if len(data) != 2:
            return

        journal_id = int(data[1])
        
        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        journal = await self.repository.get_journal_by_id(journal_id)
        if not journal:
            return

        # Show fetching message
        await query.edit_message_text(
            self.get_text("fetching_articles", language).format(journal=journal.name)
        )

        # Fetch articles from feed
        try:
            if self.feed_parser:
                articles = await self.feed_parser.parse_from_url(journal.feed_url)
                
                if not articles:
                    await query.edit_message_text(self.get_text("no_articles", language))
                    return
                
                # Process up to 3 latest articles
                sent_count = 0
                for parsed in articles[:3]:
                    # Check if article already exists
                    if await self.repository.article_exists(parsed.link):
                        article = await self.repository.get_article_by_link(parsed.link)
                    else:
                        abstract = parsed.abstract
                        
                        # Scrape abstract if needed
                        if journal.needs_scraping and not abstract and self.abstract_scraper:
                            abstract = await self.abstract_scraper.scrape_abstract(parsed.link)
                        
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
                    
                    if article and self.tailoring_service:
                        # Check if already sent
                        if await self.repository.was_article_sent_to_user(user.telegram_id, article.id):
                            continue
                        
                        # Tailor and send
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

                            try:
                                await query.message.reply_text(
                                    telegram_text,
                                    reply_markup=reply_markup,
                                    parse_mode="Markdown",
                                    disable_web_page_preview=True,
                                )
                            except Exception as e:
                                logger.warning(f"Failed to send markdown message, retrying plain text: {e}")
                                await query.message.reply_text(
                                    telegram_text,
                                    reply_markup=reply_markup,
                                    parse_mode=None,
                                    disable_web_page_preview=True,
                                )
                            
                            await self.repository.mark_article_sent(
                                telegram_id=user.telegram_id,
                                article_id=article.id,
                                tailored_content=tailored, # Store Standard MD
                            )
                            sent_count += 1
                
                if sent_count > 0:
                    await query.edit_message_text(
                        self.get_text("articles_sent", language).format(count=sent_count, journal=journal.name)
                    )
                else:
                    await query.edit_message_text(self.get_text("no_articles", language))
            else:
                await query.edit_message_text("Service not available")
                
        except Exception as e:
            logger.error(f"Error fetching articles: {e}")
            await query.edit_message_text("Error fetching articles. Please try /latest later.")

    async def handle_skip_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle skip fetch callback - return to category view."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        data = query.data.split(":", 1)
        category = data[1] if len(data) == 2 else "General Dentistry"
        
        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        await self._show_journals_in_category(query, category, language)

    async def _refresh_category_view(self, query, category: str, language: str) -> None:
        """Refresh the journals view for a category."""
        await self._show_journals_in_category(query, category, language)

    async def handle_back_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle back button - return to categories."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        categorized = await self.repository.get_journals_by_category()
        
        keyboard = []
        for category in categorized.keys():
            icon = JOURNAL_CATEGORIES.get(category, "📖")
            if language == "fa":
                label = f"{icon} {JOURNAL_CATEGORIES_FA.get(category, category)}"
            else:
                label = f"{icon} {category}"
            
            count = len(categorized[category])
            keyboard.append([
                InlineKeyboardButton(f"{label} ({count})", callback_data=f"jcat:{category}")
            ])
        
        keyboard.append([InlineKeyboardButton(self.get_text("done", language), callback_data="jdone")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            self.get_text("select_category", language),
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )

    async def handle_done_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle done button callback."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer()

        user = await self.repository.get_user(query.from_user.id)
        language = user.language if user else "en"

        # Get user's subscriptions grouped by category
        subscriptions = await self.repository.get_user_subscriptions(query.from_user.id)
        
        if not subscriptions:
            await query.edit_message_text(self.get_text("no_subscriptions", language))
            return

        # Group by category
        by_category = {}
        for j in subscriptions:
            cat = j.category or "General Dentistry"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(j.name)
        
        # Format text
        text_parts = []
        for cat, journals in sorted(by_category.items()):
            icon = JOURNAL_CATEGORIES.get(cat, "📖")
            cat_name = JOURNAL_CATEGORIES_FA.get(cat, cat) if language == "fa" else cat
            text_parts.append(f"{icon} *{cat_name}*")
            for j in journals:
                text_parts.append(f"  • {j}")
        
        journals_text = "\n".join(text_parts)
        text = self.get_text("your_subscriptions", language).format(journals=journals_text)
        
        # Add tip about getting latest articles
        if language == "fa":
            text += "\n\n💡 از /latest برای دریافت آخرین مقالات استفاده کنید."
        else:
            text += "\n\n💡 Use /latest to get the latest articles from your subscriptions."
        
        await query.edit_message_text(text, parse_mode="Markdown")

    # Legacy handlers for backward compatibility
    async def handle_page_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle journal page navigation callback (legacy)."""
        pass
