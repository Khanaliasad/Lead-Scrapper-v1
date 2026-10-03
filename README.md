# Social Commerce Lead Scraper — v1

The original, simplest version. Finds public **Instagram** businesses in Pakistan that show ordering signals and checks whether they have a website.

> A visual version of this guide is in `GUIDE.html` (open it in any browser). For Facebook support, two-list export, SQLite history and the free DuckDuckGo engine, use **v2**.

## Purpose

Small Pakistani shops often sell only through Instagram DMs and WhatsApp. v1 surfaces them from public search results so you can pitch websites, ecommerce or SaaS tools. It never logs in to Instagram, bypasses bot protection or uses private APIs.

## How it works

1. **Discover** – for each city × category it runs 6 Brave queries, e.g. `site:instagram.com "Karachi" "clothing" "DM to order"` (also `WhatsApp`, `COD`, `PKR`, `delivery`, `order`).
2. **Filter** – keeps only Instagram profile URLs (posts, reels, stories, explore are dropped) and de-duplicates them.
3. **Extract** – business name from the result title, a Pakistani mobile number (03xx / +92 3xx) from the snippets, and the buying signals found.
4. **Website check** – looks for external links in the snippet and searches `"business name" "city"` on Brave, then loads up to 8 candidate domains. A live non-social domain means `WEBSITE_FOUND`; otherwise `SOCIAL_ONLY_LIKELY`.
5. **Score** and write a CSV sorted by score.

## Setup

Python 3.10+.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `BRAVE_SEARCH_API_KEY=your_key_here`.

### Getting a Brave key
1. Register at https://api-dashboard.search.brave.com/register
2. Add a credit card (required even for free credits; it becomes a live billing card once free credit is used).
3. Choose the Search plan, then **API Keys → generate a subscription token**.
4. Set a spending cap if offered.

## Usage

```bash
python lead_scraper.py --cities Karachi Lahore --categories clothing cosmetics --max-results 100 --output leads.csv
```

| Option | Default | Meaning |
|---|---|---|
| `--cities` | Karachi | One or more cities |
| `--categories` | clothing | One or more niches |
| `--max-results` | 100 | Total leads wanted, split evenly across city × category pairs |
| `--output` | leads.csv | Output CSV |
| `--skip-website-check` | off | Skip website detection (status becomes `NOT_CHECKED`) |

## Output

One CSV (UTF-8 with BOM, opens cleanly in Excel) sorted by `lead_score`:

`business_name`, `instagram_url`, `facebook_url`, `city`, `category`, `phone`, `whatsapp`, `email`, `website`, `website_status`, `order_signals`, `snippet`, `source_query`, `lead_score`, `confidence`

`facebook_url`, `email` and `confidence` exist as columns but v1 does not fill them. `whatsapp` simply copies `phone`.

## Scoring (max 100)

Instagram profile +25, "DM to order"-style phrase +20, WhatsApp +15, COD +10, delivery/shipping +10, PKR/Rs. +10, phone found +10. A detected website subtracts 60.

Statuses: `SOCIAL_ONLY_LIKELY`, `WEBSITE_FOUND`, `NOT_CHECKED`.

## Limitations

- Instagram only; Brave API key required (no free engine).
- `SOCIAL_ONLY_LIKELY` is a heuristic: an unindexed or new website can be missed.
- Only search snippets are read, so many leads have no phone number.
- Mobile-number pattern only; no landlines.
- `beautifulsoup4` is listed in requirements and imported but not used by the current code.
- Roughly 6 Brave requests per pair plus 1 per lead for the website search.

## Responsible use

Contact data is public, but outreach is subject to local law, platform terms and anti-spam rules.

## Files

```
lead_scraper.py   main script
queries.txt       example search templates
requirements.txt  dependencies
.env.example      template for the Brave key
GUIDE.html        visual user guide
```
