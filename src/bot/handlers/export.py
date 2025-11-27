"""Export handler for PDF/Markdown generation."""

import io
import logging
import os
import markdown
from datetime import datetime
from typing import Optional

from telegram import Update, InputFile
from telegram.ext import ContextTypes
from weasyprint import HTML, CSS

from src.database.repository import Repository

logger = logging.getLogger(__name__)

class ExportHandler:
    """Handles exporting articles to PDF and Markdown formats."""

    def __init__(self, repository: Repository):
        self.repository = repository

    async def handle_export_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle export button callbacks."""
        if not update.callback_query:
            return

        query = update.callback_query
        await query.answer("Generating file...")

        data = query.data.split(":")
        if len(data) != 3:
            return

        _, format_type, article_id_str = data
        user_id = update.effective_user.id
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # Fetch content
        content = None
        if article_id_str == "custom":
            content = context.user_data.get("last_custom_article")
        else:
            try:
                article_id = int(article_id_str)
                sent_article = await self.repository.get_sent_article(user_id, article_id)
                if sent_article:
                    content = sent_article.tailored_content
            except ValueError:
                pass

        # Fallback to message text if DB content missing
        if not content:
            content = query.message.text
            # If content is from telegram message, it has emojis instead of headers.
            # WeasyPrint will render emojis fine, but structure might be weak.
            # It's better to use the DB content whenever possible.

        if not content:
            await query.answer("No content to export", show_alert=True)
            return

        try:
            if format_type == "pdf":
                await self._export_pdf(query, content, timestamp)
            elif format_type == "md":
                await self._export_markdown(query, content, timestamp)
            else:
                await query.answer("Unknown format", show_alert=True)

        except Exception as e:
            logger.error(f"Export error: {e}")
            await query.answer("Failed to generate file", show_alert=True)

    async def _export_pdf(self, query, content: str, timestamp: str) -> None:
        """Generate PDF using WeasyPrint (Markdown -> HTML -> PDF)."""
        
        # Convert MD to HTML
        # Enable extensions for better formatting
        html_body = markdown.markdown(content, extensions=['extra', 'nl2br', 'sane_lists'])
        
        # Logo path
        logo_path = "dental_research_demystifier_bot_logo.jpg"
        if not os.path.exists(logo_path):
            logo_path = "assets/dental_research_demystifier_bot_logo.jpg"
        
        logo_html = ""
        if os.path.exists(logo_path):
            # WeasyPrint handles local paths fine
            logo_html = f'<div style="text-align: center;"><img src="{os.path.abspath(logo_path)}" width="150"></div>'

        # CSS with Vazirmatn font
        font_path = os.path.abspath("fonts/Vazirmatn-Regular.ttf")
        
        css = f"""
        @font-face {{
            font-family: 'Vazirmatn';
            src: url('file://{font_path}');
        }}
        
        body {{
            font-family: 'Vazirmatn', sans-serif;
            font-size: 12pt;
            line-height: 1.6;
            margin: 2cm;
        }}
        
        h1, h2, h3 {{
            color: #1a5276;
            margin-top: 1em;
            margin-bottom: 0.5em;
        }}
        
        h1 {{ font-size: 18pt; border-bottom: 1px solid #eee; padding-bottom: 0.5em; }}
        h2 {{ font-size: 14pt; color: #2874a6; }}
        
        a {{ color: #2874a6; text-decoration: none; }}
        
        .header {{ text-align: center; margin-bottom: 2em; border-bottom: 2px solid #eee; padding-bottom: 1em; }}
        .footer {{ 
            position: fixed; 
            bottom: 0; 
            left: 0; 
            right: 0; 
            text-align: center; 
            font-size: 8pt; 
            color: #888; 
            border-top: 1px solid #eee; 
            padding-top: 1em; 
        }}
        
        /* RTL Support */
        body.rtl {{
            direction: rtl;
            text-align: right;
        }}
        
        body.rtl h1, body.rtl h2, body.rtl h3 {{
            text-align: right;
        }}
        
        /* Fix for mixed text direction */
        p {{ unicode-bidi: embed; }}
        li {{ unicode-bidi: embed; }}
        """
        
        # Determine direction
        is_farsi = any(c in content for c in "آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی")
        body_class = "rtl" if is_farsi else "ltr"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>{css}</style>
        </head>
        <body class="{body_class}">
            <div class="header">
                {logo_html}
                <h1>🦷 DentalResearchBot</h1>
                <p><a href="https://t.me/dentalresearchbot">t.me/dentalresearchbot</a></p>
                <p style="font-size: 9pt; color: #666;">Generated: {timestamp.replace('_', ' ')}</p>
            </div>
            
            <div class="content">
                {html_body}
            </div>
            
            <div class="footer">
                Powered by DentalResearchBot
            </div>
        </body>
        </html>
        """
        
        # Generate PDF
        buffer = io.BytesIO()
        # write_pdf returns None, writes to buffer
        HTML(string=html_content).write_pdf(buffer)
        buffer.seek(0)
        
        await query.message.reply_document(
            document=InputFile(buffer, filename=f"dental_article_{timestamp}.pdf"),
            caption="📄 PDF exported!",
        )

    async def _export_markdown(self, query, content: str, timestamp: str) -> None:
        """Generate and send Markdown file."""
        lines = [
            "# DentalResearchBot Article Summary",
            "",
            f"*Generated: {timestamp.replace('_', ' ')}*",
            "",
            "---",
            "",
            content,
            "",
            "---",
            "",
            "*Powered by DentalResearchBot*",
        ]

        md_content = "\n".join(lines)
        buffer = io.BytesIO(md_content.encode('utf-8'))
        buffer.seek(0)

        await query.message.reply_document(
            document=InputFile(buffer, filename=f"dental_article_{timestamp}.md"),
            caption="📝 Markdown exported!",
        )
