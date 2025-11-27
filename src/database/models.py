"""SQLAlchemy database models for DentalResearchBot."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class User(Base):
    """Telegram user model with dental education profile."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Language preference
    language: Mapped[str] = mapped_column(String(10), default="en")  # 'en' or 'fa'
    
    # Education profile
    education_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # e.g., 'dds_student', 'general_dentist', 'resident', 'specialist', 'faculty'
    specialty: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # e.g., 'Orthodontics', 'Periodontics', etc.
    education_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # For DDS students: 1-6
    
    # Bot state
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    subscriptions: Mapped[List["UserJournal"]] = relationship(
        "UserJournal", back_populates="user", cascade="all, delete-orphan"
    )
    sent_articles: Mapped[List["SentArticle"]] = relationship(
        "SentArticle", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(telegram_id={self.telegram_id}, level={self.education_level})>"


class Journal(Base):
    """Dental journal with RSS feed information."""

    __tablename__ = "journals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    feed_url: Mapped[str] = mapped_column(String(500), nullable=False)
    feed_type: Mapped[str] = mapped_column(String(50), default="rss")  # 'rss' or 'xml'
    category: Mapped[str] = mapped_column(String(100), default="General Dentistry")
    
    # Feed processing
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Nature journals need scraping
    needs_scraping: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    articles: Mapped[List["Article"]] = relationship(
        "Article", back_populates="journal", cascade="all, delete-orphan"
    )
    subscribers: Mapped[List["UserJournal"]] = relationship(
        "UserJournal", back_populates="journal", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Journal(name={self.name})>"


class UserJournal(Base):
    """User subscription to a journal."""

    __tablename__ = "user_journals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    journal_id: Mapped[int] = mapped_column(Integer, ForeignKey("journals.id", ondelete="CASCADE"), nullable=False)
    
    # Subscription settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    journal: Mapped["Journal"] = relationship("Journal", back_populates="subscribers")

    def __repr__(self) -> str:
        return f"<UserJournal(user_id={self.user_id}, journal_id={self.journal_id})>"


class Article(Base):
    """Article from a journal feed."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    journal_id: Mapped[int] = mapped_column(Integer, ForeignKey("journals.id", ondelete="CASCADE"), nullable=False)
    
    # Article metadata
    title: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    volume: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    issue: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Deduplication
    link_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    
    # Dates
    published_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    journal: Mapped["Journal"] = relationship("Journal", back_populates="articles")
    sent_to: Mapped[List["SentArticle"]] = relationship(
        "SentArticle", back_populates="article", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Article(title={self.title[:50]}...)>"


class SentArticle(Base):
    """Track which articles have been sent to which users."""

    __tablename__ = "sent_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    
    # Tailored content that was sent
    tailored_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sent_articles")
    article: Mapped["Article"] = relationship("Article", back_populates="sent_to")

    def __repr__(self) -> str:
        return f"<SentArticle(user_id={self.user_id}, article_id={self.article_id})>"

