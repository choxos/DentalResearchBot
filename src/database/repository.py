"""Database repository for DentalResearchBot."""

import hashlib
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from src.database.models import Base, User, Journal, UserJournal, Article, SentArticle

logger = logging.getLogger(__name__)


class Repository:
    """Async database repository."""

    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init_db(self) -> None:
        """Initialize database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

    async def close(self) -> None:
        """Close database connection."""
        await self.engine.dispose()

    # ===== User Methods =====

    async def get_or_create_user(self, telegram_id: int, **kwargs) -> User:
        """Get existing user or create new one."""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(telegram_id=telegram_id, **kwargs)
                session.add(user)
                await session.commit()
                await session.refresh(user)
                logger.info(f"Created new user: {telegram_id}")

            return user

    async def get_user(self, telegram_id: int) -> Optional[User]:
        """Get user by Telegram ID."""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()

    async def update_user(self, telegram_id: int, **kwargs) -> Optional[User]:
        """Update user fields."""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user:
                for key, value in kwargs.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                await session.commit()
                await session.refresh(user)

            return user

    async def get_users_subscribed_to_journal(self, journal_id: int) -> List[User]:
        """Get all users subscribed to a journal."""
        async with self.async_session() as session:
            result = await session.execute(
                select(User)
                .join(UserJournal)
                .where(UserJournal.journal_id == journal_id)
                .where(UserJournal.is_active == True)
                .where(User.onboarding_complete == True)
            )
            return list(result.scalars().all())

    async def get_all_onboarded_users(self) -> List[User]:
        """Get all users who completed onboarding."""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.onboarding_complete == True)
            )
            return list(result.scalars().all())

    # ===== Journal Methods =====

    async def get_or_create_journal(self, name: str, feed_url: str, feed_type: str = "rss", category: str = "General Dentistry") -> Journal:
        """Get existing journal or create new one."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Journal).where(Journal.name == name)
            )
            journal = result.scalar_one_or_none()

            if not journal:
                # Check if it's a Nature journal that needs scraping
                needs_scraping = "nature.com" in feed_url.lower()
                
                journal = Journal(
                    name=name,
                    feed_url=feed_url,
                    feed_type=feed_type,
                    category=category,
                    needs_scraping=needs_scraping,
                )
                session.add(journal)
                await session.commit()
                await session.refresh(journal)

            return journal

    async def get_all_journals(self) -> List[Journal]:
        """Get all active journals."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Journal).where(Journal.is_active == True).order_by(Journal.name)
            )
            return list(result.scalars().all())

    async def get_journal_by_id(self, journal_id: int) -> Optional[Journal]:
        """Get journal by ID."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Journal).where(Journal.id == journal_id)
            )
            return result.scalar_one_or_none()

    async def update_journal_last_checked(self, journal_id: int) -> None:
        """Update last checked timestamp for a journal."""
        async with self.async_session() as session:
            await session.execute(
                update(Journal)
                .where(Journal.id == journal_id)
                .values(last_checked=datetime.utcnow())
            )
            await session.commit()

    # ===== Subscription Methods =====

    async def subscribe_user_to_journal(self, user_id: int, journal_id: int) -> UserJournal:
        """Subscribe a user to a journal."""
        async with self.async_session() as session:
            # Get internal user ID
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                raise ValueError(f"User {user_id} not found")

            # Check if subscription exists
            result = await session.execute(
                select(UserJournal)
                .where(UserJournal.user_id == user.id)
                .where(UserJournal.journal_id == journal_id)
            )
            subscription = result.scalar_one_or_none()

            if subscription:
                subscription.is_active = True
            else:
                subscription = UserJournal(user_id=user.id, journal_id=journal_id)
                session.add(subscription)

            await session.commit()
            await session.refresh(subscription)
            return subscription

    async def unsubscribe_user_from_journal(self, user_id: int, journal_id: int) -> bool:
        """Unsubscribe a user from a journal."""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return False

            result = await session.execute(
                select(UserJournal)
                .where(UserJournal.user_id == user.id)
                .where(UserJournal.journal_id == journal_id)
            )
            subscription = result.scalar_one_or_none()

            if subscription:
                subscription.is_active = False
                await session.commit()
                return True
            return False

    async def get_user_subscriptions(self, telegram_id: int) -> List[Journal]:
        """Get all journals a user is subscribed to."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Journal)
                .join(UserJournal)
                .join(User)
                .where(User.telegram_id == telegram_id)
                .where(UserJournal.is_active == True)
                .order_by(Journal.name)
            )
            return list(result.scalars().all())

    # ===== Article Methods =====

    @staticmethod
    def hash_link(link: str) -> str:
        """Generate hash for article link."""
        return hashlib.md5(link.encode()).hexdigest()

    async def article_exists(self, link: str) -> bool:
        """Check if article already exists by link."""
        link_hash = self.hash_link(link)
        async with self.async_session() as session:
            result = await session.execute(
                select(Article).where(Article.link_hash == link_hash)
            )
            return result.scalar_one_or_none() is not None

    async def create_article(
        self,
        journal_id: int,
        title: str,
        link: str,
        abstract: Optional[str] = None,
        authors: Optional[str] = None,
        doi: Optional[str] = None,
        published_date: Optional[datetime] = None,
    ) -> Optional[Article]:
        """Create a new article if it doesn't exist."""
        link_hash = self.hash_link(link)

        async with self.async_session() as session:
            # Check if exists
            result = await session.execute(
                select(Article).where(Article.link_hash == link_hash)
            )
            if result.scalar_one_or_none():
                return None

            article = Article(
                journal_id=journal_id,
                title=title,
                link=link,
                link_hash=link_hash,
                abstract=abstract,
                authors=authors,
                doi=doi,
                published_date=published_date,
            )
            session.add(article)
            await session.commit()
            await session.refresh(article)
            return article

    async def get_latest_articles(self, journal_id: int, limit: int = 10) -> List[Article]:
        """Get latest articles from a journal."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Article)
                .where(Article.journal_id == journal_id)
                .order_by(Article.fetched_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_article_by_link(self, link: str) -> Optional[Article]:
        """Get article by link."""
        link_hash = self.hash_link(link)
        async with self.async_session() as session:
            result = await session.execute(
                select(Article)
                .options(selectinload(Article.journal))
                .where(Article.link_hash == link_hash)
            )
            return result.scalar_one_or_none()

    # ===== Sent Article Methods =====

    async def was_article_sent_to_user(self, user_id: int, article_id: int) -> bool:
        """Check if article was already sent to user."""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return False

            result = await session.execute(
                select(SentArticle)
                .where(SentArticle.user_id == user.id)
                .where(SentArticle.article_id == article_id)
            )
            return result.scalar_one_or_none() is not None

    async def mark_article_sent(
        self, telegram_id: int, article_id: int, tailored_content: Optional[str] = None
    ) -> SentArticle:
        """Mark an article as sent to a user."""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                raise ValueError(f"User {telegram_id} not found")

            sent = SentArticle(
                user_id=user.id,
                article_id=article_id,
                tailored_content=tailored_content,
            )
            session.add(sent)
            await session.commit()
            await session.refresh(sent)
            return sent

    async def get_sent_article(self, telegram_id: int, article_id: int) -> Optional[SentArticle]:
        """Get a sent article record."""
        async with self.async_session() as session:
            result = await session.execute(
                select(SentArticle)
                .join(User)
                .where(User.telegram_id == telegram_id)
                .where(SentArticle.article_id == article_id)
                .order_by(SentArticle.sent_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_unsent_articles_for_user(self, telegram_id: int) -> List[Article]:
        """Get articles from subscribed journals not yet sent to user."""
        async with self.async_session() as session:
            # Get user
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return []

            # Get subscribed journal IDs
            result = await session.execute(
                select(UserJournal.journal_id)
                .where(UserJournal.user_id == user.id)
                .where(UserJournal.is_active == True)
            )
            journal_ids = [row[0] for row in result.all()]

            if not journal_ids:
                return []

            # Get sent article IDs
            result = await session.execute(
                select(SentArticle.article_id).where(SentArticle.user_id == user.id)
            )
            sent_ids = [row[0] for row in result.all()]

            # Get unsent articles
            query = (
                select(Article)
                .options(selectinload(Article.journal))
                .where(Article.journal_id.in_(journal_ids))
            )
            if sent_ids:
                query = query.where(Article.id.notin_(sent_ids))
            query = query.order_by(Article.fetched_at.desc()).limit(20)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_journals_by_category(self) -> dict:
        """Get all journals grouped by category."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Journal).where(Journal.is_active == True).order_by(Journal.category, Journal.name)
            )
            journals = result.scalars().all()
            
            categorized = {}
            for journal in journals:
                cat = journal.category or "General Dentistry"
                if cat not in categorized:
                    categorized[cat] = []
                categorized[cat].append(journal)
            
            return categorized

    # ===== Initialize Journals =====

    async def init_journals_from_config(self, journals: List[dict]) -> None:
        """Initialize journals from config."""
        for j in journals:
            await self.get_or_create_journal(
                name=j["name"],
                feed_url=j["feed_url"],
                feed_type=j.get("feed_type", "rss"),
                category=j.get("category", "General Dentistry"),
            )
        logger.info(f"Initialized {len(journals)} journals")

