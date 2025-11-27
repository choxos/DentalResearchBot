"""Multi-format RSS/RDF feed parser for dental journals."""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from html import unescape

import feedparser
import httpx

logger = logging.getLogger(__name__)


@dataclass
class ParsedArticle:
    """Parsed article from feed."""
    title: str
    link: str
    abstract: Optional[str]
    authors: Optional[str]
    doi: Optional[str]
    published_date: Optional[datetime]
    volume: Optional[str] = None
    issue: Optional[str] = None


class FeedParser:
    """Multi-format feed parser supporting RSS 2.0, RDF/RSS 1.0, Atom."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    async def fetch_feed(self, feed_url: str) -> Optional[str]:
        """Fetch feed content from URL."""
        try:
            response = await self.client.get(feed_url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            logger.error(f"Error fetching feed {feed_url}: {e}")
            return None

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and clean text."""
        if not text:
            return ""
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        # Unescape HTML entities
        clean = unescape(clean)
        # Clean up whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _extract_doi(self, entry: dict) -> Optional[str]:
        """Extract DOI from feed entry."""
        # Try common locations
        if hasattr(entry, 'prism_doi'):
            return entry.prism_doi
        if 'dc_identifier' in entry:
            identifier = entry.dc_identifier
            if 'doi.org' in identifier or identifier.startswith('10.'):
                return identifier
        # Try to extract from link
        link = entry.get('link', '')
        doi_match = re.search(r'(10\.\d{4,}/[^\s]+)', link)
        if doi_match:
            return doi_match.group(1)
        return None

    def _extract_authors(self, entry: dict) -> Optional[str]:
        """Extract authors from feed entry."""
        authors = []
        
        # Try different author fields
        if 'authors' in entry:
            for author in entry.authors:
                if isinstance(author, dict):
                    name = author.get('name', '')
                else:
                    name = str(author)
                if name:
                    authors.append(name)
        
        if 'author' in entry:
            author = entry.author
            if isinstance(author, str):
                authors.append(author)
        
        if 'dc_creator' in entry:
            creator = entry.dc_creator
            if isinstance(creator, list):
                authors.extend(creator)
            else:
                authors.append(creator)
        
        return ', '.join(authors) if authors else None

    def _parse_date(self, entry: dict) -> Optional[datetime]:
        """Parse publication date from entry."""
        date_fields = ['published_parsed', 'updated_parsed', 'created_parsed']
        
        for field in date_fields:
            if field in entry and entry[field]:
                try:
                    import time
                    return datetime.fromtimestamp(time.mktime(entry[field]))
                except (TypeError, ValueError):
                    continue
        
        # Try string dates
        date_str_fields = ['published', 'updated', 'dc_date', 'prism_publicationdate']
        for field in date_str_fields:
            if field in entry and entry[field]:
                try:
                    from dateutil import parser
                    return parser.parse(entry[field])
                except (ImportError, ValueError):
                    continue
        
        return None

    def _extract_abstract(self, entry: dict) -> Optional[str]:
        """Extract abstract from feed entry."""
        abstract = None
        
        # Priority order for abstract extraction
        if 'summary' in entry:
            abstract = entry.summary
        elif 'description' in entry:
            abstract = entry.description
        elif 'content' in entry and entry.content:
            # Atom feeds
            content = entry.content[0]
            if isinstance(content, dict):
                abstract = content.get('value', '')
            else:
                abstract = str(content)
        
        if abstract:
            abstract = self._clean_html(abstract)
            # Some feeds just have "..." or very short text
            if len(abstract) < 50:
                return None
        
        return abstract

    def _extract_volume_issue(self, entry: dict) -> tuple[Optional[str], Optional[str]]:
        """Extract volume and issue from entry."""
        volume = entry.get('prism_volume')
        issue = entry.get('prism_number') or entry.get('prism_issue')
        return volume, issue

    def _parse_feed_content(self, feed_content: str) -> List[ParsedArticle]:
        """Parse feed content and extract articles (CPU-bound task)."""
        articles = []
        
        if not feed_content:
            return articles
        
        parsed = feedparser.parse(feed_content)
        
        if parsed.bozo and not parsed.entries:
            logger.warning(f"Feed parsing error: {parsed.bozo_exception}")
            return articles
        
        for entry in parsed.entries:
            try:
                # Get title
                title = self._clean_html(entry.get('title', ''))
                if not title:
                    continue
                
                # Get link
                link = entry.get('link', '')
                if not link:
                    # Try alternate links
                    links = entry.get('links', [])
                    for l in links:
                        if isinstance(l, dict) and l.get('href'):
                            link = l['href']
                            break
                
                if not link:
                    continue
                
                # Extract other fields
                abstract = self._extract_abstract(entry)
                authors = self._extract_authors(entry)
                doi = self._extract_doi(entry)
                published_date = self._parse_date(entry)
                volume, issue = self._extract_volume_issue(entry)
                
                articles.append(ParsedArticle(
                    title=title,
                    link=link,
                    abstract=abstract,
                    authors=authors,
                    doi=doi,
                    published_date=published_date,
                    volume=volume,
                    issue=issue,
                ))
                
            except Exception as e:
                logger.error(f"Error parsing entry: {e}")
                continue
        
        return articles

    async def parse_from_url(self, feed_url: str) -> List[ParsedArticle]:
        """Fetch and parse feed from URL."""
        content = await self.fetch_feed(feed_url)
        if content:
            # Run CPU-bound parsing in a separate thread
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._parse_feed_content, content)
        return []


# Global parser instance
_parser: Optional[FeedParser] = None


def get_feed_parser() -> FeedParser:
    """Get or create feed parser instance."""
    global _parser
    if _parser is None:
        _parser = FeedParser()
    return _parser


async def close_feed_parser() -> None:
    """Close feed parser."""
    global _parser
    if _parser is not None:
        await _parser.close()
        _parser = None
