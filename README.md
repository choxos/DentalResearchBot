# DentalResearchBot 🦷

A powerful Telegram bot that delivers and explains scientific articles from dental journals, tailored to your level of education (from students to professors).

## Features

-   **Tailored Summaries:** Uses AI (Grok 4.1) to rewrite article titles and abstracts based on your profile (Student, Resident, Specialist, Faculty).
-   **Education Profile:** Supports the Iranian dental education system (DDS years 1-6, various specialties).
-   **Journal Subscriptions:** Subscribe to 28+ top dental journals (Nature, Wiley, Elsevier, etc.).
-   **Smart Categorization:** Journals are categorized (e.g., Endodontics, Orthodontics).
-   **Automatic Delivery:** Checks feeds hourly and delivers new articles automatically.
-   **PDF & Markdown Export:** Download beautifully formatted summaries (with Farsi support) as PDF or Markdown.
-   **Custom Article Links:** Send any article URL (e.g., `/link https://nature.com/...`) to get a tailored summary.

## Setup & Deployment

### Prerequisites

-   Docker & Docker Compose
-   Telegram Bot Token (from @BotFather)
-   OpenRouter API Key (for Grok AI)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/DentalResearchBot.git
cd DentalResearchBot
```

### 2. Configure Environment

Create a `.env` file in the root directory:

```bash
# .env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_DEFAULT_MODEL=x-ai/grok-4.1-fast:free
DATABASE_URL=postgresql+asyncpg://dentalbot:dentalbot_secret@postgres:5432/dentalbot_db
ADMIN_USER_IDS=[123456789]
FEED_CHECK_INTERVAL_HOURS=1
LOG_LEVEL=INFO
```

### 3. Add Logo (Optional)

Place your bot logo as `dental_research_demystifier_bot_logo.jpg` in the root or `assets/` directory for it to appear in PDF exports.

### 4. Deploy with Docker (Recommended for VPS)

This is the easiest way to run the bot on a VPS (Virtual Private Server).

```bash
# Build and start the containers
docker-compose up -d --build
```

This will start:
-   **PostgreSQL** database container.
-   **Bot** container (with all system dependencies for PDF generation).

To view logs:
```bash
docker-compose logs -f
```

To stop:
```bash
docker-compose down
```

### 5. Local Development (Optional)

If you want to run it locally without Docker, you need system libraries for PDF generation (WeasyPrint).

**macOS:**
```bash
brew install python-tk pango gobject-introspection
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libjpeg62-turbo libopenjp2-7 libxcb1
```

**Install Python Dependencies:**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Run:**
```bash
python -m src.main
```

## Usage

1.  Start the bot: `/start`
2.  Select Language (English/Farsi).
3.  Select Education Level (e.g., Resident -> Orthodontics).
4.  Subscribe to Journals via `/journals`.
5.  Get latest articles immediately via `/latest` or wait for hourly updates.
6.  Summarize a specific link: `/link <url>`.

## Project Structure

-   `src/bot`: Telegram handlers and conversation logic.
-   `src/services`: Core logic (Feed parsing, Scraping, AI tailoring, Scheduler).
-   `src/database`: SQL models and repository.
-   `data/`: JSON/CSV data for education levels and journals.
-   `assets/`: Fonts and images.

## License

MIT
