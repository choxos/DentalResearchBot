"""Abstract scraper for articles without abstracts in feed (mainly Nature journals)."""

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class AbstractScraper:
    """Scrape abstracts from article pages."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page HTML."""
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            logger.error(f"Error fetching page {url}: {e}")
            return None

    def _scrape_nature(self, soup: BeautifulSoup) -> Optional[str]:
        """Scrape abstract from Nature journal pages."""
        # Try multiple selectors
        selectors = [
            'section[aria-labelledby="Abs1"] p',
            '#Abs1-content p',
            '.c-article-section__content p',
            '[data-article-body] section[id*="abstract"] p',
            '.abstract p',
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                paragraphs = [el.get_text(strip=True) for el in elements]
                abstract = ' '.join(paragraphs)
                if len(abstract) > 50:  # Reasonable abstract length
                    return abstract
        
        return None

    def _scrape_wiley(self, soup: BeautifulSoup) -> Optional[str]:
        """Scrape abstract from Wiley journal pages."""
        selectors = [
            '.article-section__content.en.main p',
            '.abstract-group p',
            '#abstract .article-section__content p',
            '.abstract p',
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                paragraphs = [el.get_text(strip=True) for el in elements]
                abstract = ' '.join(paragraphs)
                if len(abstract) > 50:
                    return abstract
        
        return None

    def _scrape_sciencedirect(self, soup: BeautifulSoup) -> Optional[str]:
        """Scrape abstract from ScienceDirect pages."""
        selectors = [
            '.abstract.author p',
            '#abstracts .abstract p',
            '.Abstracts p',
            '[class*="abstract"] p',
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                paragraphs = [el.get_text(strip=True) for el in elements]
                abstract = ' '.join(paragraphs)
                if len(abstract) > 50:
                    return abstract
        
        return None

    def _scrape_sage(self, soup: BeautifulSoup) -> Optional[str]:
        """Scrape abstract from Sage journal pages."""
        selectors = [
            '.abstractSection.abstractInFull p',
            '.hlFld-Abstract p',
            '#abstract p',
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                paragraphs = [el.get_text(strip=True) for el in elements]
                abstract = ' '.join(paragraphs)
                if len(abstract) > 50:
                    return abstract
        
        return None

    def _scrape_generic(self, soup: BeautifulSoup) -> Optional[str]:
        """Generic abstract scraping for unknown sites."""
        # Try common patterns
        selectors = [
            '[class*="abstract"]',
            '#abstract',
            '.abstract',
            '[id*="abstract"]',
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for el in elements:
                # Get all paragraph text
                paragraphs = el.find_all('p')
                if paragraphs:
                    text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                else:
                    text = el.get_text(strip=True)
                
                if len(text) > 100:  # Reasonable abstract
                    return text
        
        return None

    def _detect_site_and_scrape(self, url: str, soup: BeautifulSoup) -> Optional[str]:
        """Detect site type and use appropriate scraper."""
        url_lower = url.lower()
        
        if 'nature.com' in url_lower:
            return self._scrape_nature(soup)
        elif 'wiley.com' in url_lower or 'onlinelibrary' in url_lower:
            return self._scrape_wiley(soup)
        elif 'sciencedirect.com' in url_lower:
            return self._scrape_sciencedirect(soup)
        elif 'sagepub.com' in url_lower:
            return self._scrape_sage(soup)
        else:
            return self._scrape_generic(soup)

    async def scrape_abstract(self, article_url: str) -> Optional[str]:
        """Scrape abstract from article page."""
        html = await self.fetch_page(article_url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'lxml')
        
        # Try site-specific scraping first
        abstract = self._detect_site_and_scrape(article_url, soup)
        
        if not abstract:
            # Try generic scraping
            abstract = self._scrape_generic(soup)
        
        if abstract:
            # Clean up the abstract
            abstract = re.sub(r'\s+', ' ', abstract).strip()
            # Remove common prefixes
            abstract = re.sub(r'^(Abstract\.?\s*|Summary\.?\s*)', '', abstract, flags=re.IGNORECASE)
        
        return abstract


# Global scraper instance
_scraper: Optional[AbstractScraper] = None


def get_abstract_scraper() -> AbstractScraper:
    """Get or create abstract scraper instance."""
    global _scraper
    if _scraper is None:
        _scraper = AbstractScraper()
    return _scraper


async def close_abstract_scraper() -> None:
    """Close abstract scraper."""
    global _scraper
    if _scraper is not None:
        await _scraper.close()
        _scraper = None

