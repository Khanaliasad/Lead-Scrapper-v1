#!/usr/bin/env python3
import argparse
import csv
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Iterable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.search.brave.com/res/v1/web/search"
SOCIAL_DOMAINS = {"instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com"}
WEBSITE_BLACKLIST = {
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com",
    "tiktok.com", "www.tiktok.com",
    "youtube.com", "www.youtube.com",
    "x.com", "twitter.com", "www.twitter.com",
    "linktr.ee", "www.linktr.ee",
    "wa.me", "api.whatsapp.com", "whatsapp.com",
    "google.com", "www.google.com",
    "youtube.com", "www.youtube.com",
}

BUYING_SIGNALS = [
    "dm to order", "dm for order", "order via dm", "order through dm",
    "whatsapp to order", "whatsapp order", "order on whatsapp",
    "cash on delivery", "cod available", "cod",
    "delivery all over pakistan", "delivery across pakistan",
    "nationwide delivery", "delivery available",
    "inbox to order", "message to order", "price", "pkr", "rs.",
    "shipping all over pakistan", "ship across pakistan",
]

CONTACT_RE = re.compile(
    r"(?<!\d)(?:\+92|0092|0)\s*3\d{2}[\s\-]?\d{3}[\s\-]?\d{4}(?!\d)"
)

@dataclass
class Lead:
    business_name: str = ""
    instagram_url: str = ""
    facebook_url: str = ""
    city: str = ""
    category: str = ""
    phone: str = ""
    whatsapp: str = ""
    email: str = ""
    website: str = ""
    website_status: str = ""
    order_signals: str = ""
    snippet: str = ""
    source_query: str = ""
    lead_score: int = 0
    confidence: str = ""

def host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""

def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("0092"):
        digits = "0" + digits[4:]
    elif digits.startswith("92") and len(digits) == 12:
        digits = "0" + digits[2:]
    return digits

def brave_search(api_key: str, query: str, count: int = 20, country="PK") -> list[dict]:
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {
        "q": query,
        "count": min(count, 20),
        "country": country,
        "search_lang": "en",
        "safesearch": "moderate",
        "extra_snippets": "true",
    }
    r = requests.get(API_URL, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("web", {}).get("results", [])

def extract_instagram(url: str) -> str:
    if host(url) != "instagram.com":
        return ""
    path = urlparse(url).path.strip("/")
    if not path:
        return ""
    first = path.split("/")[0]
    if first in {"p", "reel", "reels", "stories", "explore", "accounts", "direct"}:
        return ""
    return f"https://www.instagram.com/{first}/"

def extract_contact(text: str) -> str:
    m = CONTACT_RE.search(text or "")
    return normalize_phone(m.group(0)) if m else ""

def signal_hits(text: str) -> list[str]:
    t = (text or "").lower()
    return [s for s in BUYING_SIGNALS if s in t]

def likely_business_name(title: str, url: str) -> str:
    # Brave titles often look like "Brand Name (@handle) • Instagram photos..."
    if title:
        title = re.sub(r"\s*[•|]\s*Instagram.*$", "", title, flags=re.I)
        title = re.sub(r"\s*\(@[^)]+\)", "", title).strip()
        if title:
            return title
    ig = extract_instagram(url)
    if ig:
        return urlparse(ig).path.strip("/").split("/")[0]
    return ""

def discover(api_key: str, city: str, category: str, max_results: int) -> list[Lead]:
    query_templates = [
        'site:instagram.com "{city}" "{category}" "DM to order"',
        'site:instagram.com "{city}" "{category}" "WhatsApp"',
        'site:instagram.com "{city}" "{category}" "COD"',
        'site:instagram.com "{city}" "{category}" "PKR"',
        'site:instagram.com "{city}" "{category}" "delivery"',
        'site:instagram.com "{city}" "{category}" "order"',
    ]

    leads = []
    seen = set()

    for template in query_templates:
        q = template.format(city=city, category=category)
        try:
            results = brave_search(api_key, q, count=min(max_results, 20))
        except requests.HTTPError as e:
            print(f"[search error] {q}: {e}", file=sys.stderr)
            continue

        for r in results:
            url = r.get("url", "")
            ig = extract_instagram(url)
            if not ig:
                continue

            key = ig.lower()
            if key in seen:
                continue
            seen.add(key)

            text = " ".join([
                r.get("title", ""),
                r.get("description", ""),
                " ".join(r.get("extra_snippets", []) or []),
            ])
            hits = signal_hits(text)
            phone = extract_contact(text)

            leads.append(Lead(
                business_name=likely_business_name(r.get("title", ""), url),
                instagram_url=ig,
                city=city,
                category=category,
                phone=phone,
                whatsapp=phone if phone else "",
                order_signals="; ".join(hits),
                snippet=text[:1500],
                source_query=q,
            ))

            if len(leads) >= max_results:
                return leads

        time.sleep(0.2)

    return leads

def extract_domains(text: str) -> set[str]:
    domains = set()
    for match in re.findall(r'https?://[^\s<>"\']+', text or ""):
        h = host(match.rstrip(".,);"))
        if h and h not in WEBSITE_BLACKLIST:
            domains.add(h)
    return domains

def probe_url(domain: str) -> tuple[bool, str]:
    if not domain or domain in WEBSITE_BLACKLIST:
        return False, ""
    for scheme in ("https://", "http://"):
        try:
            r = requests.get(
                scheme + domain,
                timeout=8,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (lead research bot; public pages only)"},
            )
            final_host = host(r.url)
            if r.status_code < 500 and final_host and final_host not in WEBSITE_BLACKLIST:
                return True, r.url
        except requests.RequestException:
            pass
    return False, ""

def website_check(api_key: str, lead: Lead) -> Lead:
    # First inspect the social search snippet for a linked external domain.
    domains = extract_domains(lead.snippet)

    # Then search the exact business name + city. This catches websites that
    # are not linked from the social profile.
    name = lead.business_name.strip()
    if name:
        q = f'"{name}" "{lead.city}"'
        try:
            results = brave_search(api_key, q, count=10)
            for r in results:
                u = r.get("url", "")
                h = host(u)
                if h and h not in WEBSITE_BLACKLIST:
                    domains.add(h)
        except requests.RequestException:
            pass

    # Probe candidates. A reachable domain is evidence of a website, not proof
    # that it is the business's official site.
    for d in list(domains)[:8]:
        ok, final_url = probe_url(d)
        if ok:
            lead.website = final_url
            lead.website_status = "WEBSITE_FOUND"
            return lead

    lead.website_status = "SOCIAL_ONLY_LIKELY"
    return lead

def score(lead: Lead) -> int:
    text = (lead.order_signals + " " + lead.snippet).lower()
    s = 0

    if lead.instagram_url:
        s += 25
    if any(x in text for x in ["dm to order", "order via dm", "inbox to order"]):
        s += 20
    if "whatsapp" in text:
        s += 15
    if "cod" in text or "cash on delivery" in text:
        s += 10
    if "delivery" in text or "shipping" in text:
        s += 10
    if "pkr" in text or "rs." in text:
        s += 10
    if lead.phone:
        s += 10

    if lead.website_status == "WEBSITE_FOUND":
        s -= 60

    return max(0, min(100, s))

def dedupe(leads: Iterable[Lead]) -> list[Lead]:
    out = {}
    for lead in leads:
        key = (lead.instagram_url or lead.business_name).lower().strip()
        if not key:
            continue
        if key not in out or lead.lead_score > out[key].lead_score:
            out[key] = lead
    return sorted(out.values(), key=lambda x: x.lead_score, reverse=True)

def save_csv(leads: list[Lead], path: str):
    rows = [asdict(x) for x in leads]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [f.name for f in Lead.__dataclass_fields__.values()])
        writer.writeheader()
        writer.writerows(rows)

def main():
    p = argparse.ArgumentParser(description="Find public social-commerce leads without detected websites.")
    p.add_argument("--cities", nargs="+", default=["Karachi"])
    p.add_argument("--categories", nargs="+", default=["clothing"])
    p.add_argument("--max-results", type=int, default=100)
    p.add_argument("--output", default="leads.csv")
    p.add_argument("--skip-website-check", action="store_true")
    args = p.parse_args()

    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        raise SystemExit("Missing BRAVE_SEARCH_API_KEY. Copy .env.example to .env and add your API key.")

    all_leads = []
    per_search = max(1, args.max_results // max(1, len(args.cities) * len(args.categories)))

    for city in args.cities:
        for category in args.categories:
            print(f"[discover] {city} / {category}")
            all_leads.extend(discover(api_key, city, category, per_search))

    all_leads = dedupe(all_leads)
    print(f"[info] unique social leads: {len(all_leads)}")

    if not args.skip_website_check:
        checked = []
        for i, lead in enumerate(all_leads, 1):
            print(f"[website] {i}/{len(all_leads)} {lead.business_name}")
            checked.append(website_check(api_key, lead))
            lead.lead_score = score(lead)
            time.sleep(0.15)
        all_leads = dedupe(checked)
    else:
        for lead in all_leads:
            lead.website_status = "NOT_CHECKED"
            lead.lead_score = score(lead)

    save_csv(all_leads, args.output)
    print(f"[done] wrote {len(all_leads)} leads to {args.output}")

if __name__ == "__main__":
    main()
