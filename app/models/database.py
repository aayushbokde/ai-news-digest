"""
app/models/database.py
──────────────────────
SQLAlchemy ORM models.

Tables
  sources  – a channel or blog we scrape
  articles – a single piece of content (video or blog post)
  digests  – a generated daily digest
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey,
    UniqueConstraint, Enum as SAEnum, create_engine
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session
import enum


# ── Enums ──────────────────────────────────────────────────────────────────────

class SourceType(str, enum.Enum):
    youtube_channel = "youtube_channel"
    blog = "blog"


class ArticleStatus(str, enum.Enum):
    pending   = "pending"    # scraped, not yet summarised
    summarised = "summarised" # LLM summary attached
    skipped   = "skipped"    # no transcript / content available


# ── Base ───────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Models ─────────────────────────────────────────────────────────────────────

class Source(Base):
    """A content source – either a YouTube channel or a blog."""
    __tablename__ = "sources"

    id         = Column(String(64),  primary_key=True)   # channel_id or slug
    name       = Column(String(256), nullable=False)
    source_type = Column(SAEnum(SourceType), nullable=False)
    url        = Column(String(512), nullable=False)      # RSS / homepage URL
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    articles = relationship("Article", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Source {self.source_type.value}:{self.name}>"


class Article(Base):
    """A single piece of content scraped from a source."""
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("external_id", "source_id", name="uq_article_external_source"),)

    id          = Column(String(64),  primary_key=True)   # video_id or url hash
    external_id = Column(String(256), nullable=False)     # video_id / post url
    source_id   = Column(String(64),  ForeignKey("sources.id"), nullable=False)
    title       = Column(String(512), nullable=False)
    url         = Column(String(512), nullable=False)
    raw_content = Column(Text,        nullable=True)      # transcript / HTML text
    summary     = Column(Text,        nullable=True)      # LLM-generated summary
    language    = Column(String(16),  nullable=True)
    status      = Column(SAEnum(ArticleStatus), default=ArticleStatus.pending, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=False)
    scraped_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    source = relationship("Source", back_populates="articles")

    def __repr__(self) -> str:
        return f'<Article {self.id[:8]}…  "{self.title[:40]}">'


class Digest(Base):
    """A generated daily digest."""
    __tablename__ = "digests"

    id         = Column(String(64),  primary_key=True)
    content    = Column(Text,        nullable=False)   # full HTML / markdown digest
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sent_at    = Column(DateTime(timezone=True), nullable=True)
    sent_to    = Column(String(256), nullable=True)

    def __repr__(self) -> str:
        return f"<Digest {self.id[:8]}… {self.created_at.date()}>"


# ── Helpers ────────────────────────────────────────────────────────────────────

def create_tables(engine) -> None:
    """Create all tables (idempotent)."""
    Base.metadata.create_all(engine)


def get_engine(database_url: str):
    return create_engine(database_url, echo=False)


def get_session(engine) -> Session:
    return Session(engine)