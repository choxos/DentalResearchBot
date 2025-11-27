"""Grok-based content tailoring service for dental research articles."""

import logging
from typing import Optional

from src.database.models import User, Article
from src.services.openrouter import OpenRouterClient, ChatMessage, OpenRouterError

logger = logging.getLogger(__name__)


# Tailoring prompt templates
SYSTEM_PROMPT_EN = """You are a dental education assistant specializing in making scientific research accessible. 
Your task is to tailor article abstracts based on the reader's level of dental education.

Guidelines for each level:
- DDS Students Year 1-2: Use very simple language, explain all technical terms, focus on basic science relevance
- DDS Students Year 3-4: Include pre-clinical implications, moderate complexity
- DDS Students Year 5-6: Include clinical relevance, practical applications
- General Dentists: Professional language, focus on clinical implications for daily practice
- Residents/Specialists: Expert-level language, field-specific implications, methodology insights
- Faculty/Professors: Scholarly analysis, research methodology critique, academic implications

Output format:
1. Brief tailored summary (2-3 paragraphs)
2. Key takeaways (3-5 bullet points)
3. Implications for their practice/study
4. Link to original article

Write in a clear, engaging style. Be informative but concise."""

SYSTEM_PROMPT_FA = """شما یک دستیار آموزش دندانپزشکی هستید که در قابل فهم کردن تحقیقات علمی تخصص دارید.
وظیفه شما تطبیق چکیده مقالات بر اساس سطح تحصیلات دندانپزشکی خواننده است.

راهنمای هر سطح:
- دانشجویان سال ۱-۲: زبان بسیار ساده، توضیح همه اصطلاحات فنی، تمرکز بر اهمیت علوم پایه
- دانشجویان سال ۳-۴: شامل کاربردهای پیش‌بالینی، پیچیدگی متوسط
- دانشجویان سال ۵-۶: شامل ارتباط بالینی، کاربردهای عملی
- دندانپزشکان عمومی: زبان حرفه‌ای، تمرکز بر کاربردهای بالینی در کار روزانه
- دستیاران/متخصصین: زبان سطح تخصصی، کاربردهای مختص رشته، بینش‌های روش‌شناسی
- اساتید دانشگاه: تحلیل علمی، نقد روش‌شناسی تحقیق، کاربردهای آکادمیک

فرمت خروجی:
۱. خلاصه تطبیق‌یافته (۲-۳ پاراگراف)
۲. نکات کلیدی (۳-۵ مورد)
۳. کاربردها برای کار/تحصیلشان
۴. لینک مقاله اصلی

به سبکی واضح و جذاب بنویسید. آموزنده اما مختصر باشید."""


def _get_education_description(user: User, language: str) -> str:
    """Get human-readable description of user's education level."""
    level = user.education_level or "general_dentist"
    specialty = user.specialty
    year = user.education_year
    
    if language == "fa":
        level_names = {
            "dds_student": "دانشجوی دندانپزشکی",
            "general_dentist": "دندانپزشک عمومی",
            "resident": "دستیار تخصصی",
            "specialist": "متخصص",
            "faculty": "عضو هیئت علمی",
        }
        base = level_names.get(level, "دندانپزشک")
        
        if level == "dds_student" and year:
            return f"{base} سال {year}"
        elif specialty and level in ["resident", "specialist"]:
            return f"{base} {specialty}"
        return base
    else:
        level_names = {
            "dds_student": "DDS Student",
            "general_dentist": "General Dentist",
            "resident": "Specialty Resident",
            "specialist": "Specialist",
            "faculty": "Faculty/Professor",
        }
        base = level_names.get(level, "Dentist")
        
        if level == "dds_student" and year:
            return f"{base} - Year {year}"
        elif specialty and level in ["resident", "specialist"]:
            return f"{specialty} {base}"
        return base


def _build_tailoring_prompt(
    user: User,
    article: Article,
    journal_name: str,
    language: str
) -> str:
    """Build the user prompt for tailoring."""
    education_desc = _get_education_description(user, language)
    
    if language == "fa":
        prompt = f"""لطفاً این مقاله را برای یک {education_desc} تطبیق دهید.

عنوان مقاله: {article.title}

مجله: {journal_name}

چکیده اصلی:
{article.abstract or 'چکیده در دسترس نیست'}

لینک مقاله: {article.link}

لطفاً خلاصه‌ای تطبیق‌یافته به فارسی ارائه دهید که برای سطح تحصیلی این خواننده مناسب باشد.

فرمت خروجی باید **Markdown استاندارد** باشد:
- از `#`، `##`، `###` برای عنوان‌ها استفاده کنید.
- از `**` برای متن ضخیم (Bold) استفاده کنید.
- از `-` برای لیست‌های موردی استفاده کنید.
- از ایموجی استفاده نکنید (فقط متن و فرمتینگ).

ساختار پیشنهادی:
# عنوان خلاصه
## خلاصه
(متن خلاصه در ۲-۳ پاراگراف)

## نکات کلیدی
- نکته ۱
- نکته ۲
- ...

## کاربرد بالینی/علمی
(توضیحات)

## لینک مقاله
{article.link}"""
    else:
        prompt = f"""Please tailor this article for a {education_desc}.

Article Title: {article.title}

Journal: {journal_name}

Original Abstract:
{article.abstract or 'Abstract not available'}

Article Link: {article.link}

Please provide a tailored summary in English appropriate for this reader's education level.

Output format must be **Standard Markdown**:
- Use `#`, `##`, `###` for headers.
- Use `**` for bold text.
- Use `-` for bullet points.
- Do NOT use emojis (text and formatting only).

Suggested structure:
# Summary Title
## Summary
(Summary text in 2-3 paragraphs)

## Key Takeaways
- Point 1
- Point 2
- ...

## Clinical/Scientific Implications
(Description)

## Article Link
{article.link}"""

    return prompt


class GrokTailoringService:
    """Service for tailoring article content using Grok."""

    def __init__(self, openrouter_client: OpenRouterClient):
        self.client = openrouter_client

    async def tailor_article(
        self,
        user: User,
        article: Article,
        journal_name: str,
    ) -> Optional[str]:
        """Generate tailored content for an article based on user's education level."""
        language = user.language or "en"
        
        # Select system prompt based on language
        system_prompt = SYSTEM_PROMPT_FA if language == "fa" else SYSTEM_PROMPT_EN
        
        # Build user prompt
        user_prompt = _build_tailoring_prompt(user, article, journal_name, language)
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        
        try:
            response = await self.client.chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
            )
            
            tailored_content = response.content
            
            # Prepend Original Title
            if language == "fa":
                tailored_content = f"**عنوان مقاله:**\n{article.title}\n\n{tailored_content}"
            else:
                tailored_content = f"**Original Title:**\n{article.title}\n\n{tailored_content}"
            
            # Ensure link is included
            if article.link not in tailored_content:
                if language == "fa":
                    tailored_content += f"\n\n🔗 لینک مقاله اصلی: {article.link}"
                else:
                    tailored_content += f"\n\n🔗 Original Article: {article.link}"
            
            return tailored_content
            
        except OpenRouterError as e:
            logger.error(f"Error tailoring article: {e.message}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error tailoring article: {e}")
            return None

    async def tailor_custom_article(
        self,
        user: User,
        title: str,
        abstract: str,
        link: str,
        journal_name: str = "Unknown Journal",
    ) -> Optional[str]:
        """Tailor a custom article (from user-provided link)."""
        # Create a temporary article-like object
        class TempArticle:
            pass
        
        temp = TempArticle()
        temp.title = title
        temp.abstract = abstract
        temp.link = link
        
        return await self.tailor_article(user, temp, journal_name)


# Global service instance
_service: Optional[GrokTailoringService] = None


def get_tailoring_service(openrouter_client: OpenRouterClient) -> GrokTailoringService:
    """Get or create tailoring service instance."""
    global _service
    if _service is None:
        _service = GrokTailoringService(openrouter_client)
    return _service

