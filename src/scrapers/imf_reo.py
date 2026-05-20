"""
Scraper para IMF - Regional Economic Outlook (REO).

URL: https://www.imf.org/en/publications/reo
Regulador: IMF (International Monetary Fund)

Sitio client-rendered: requiere Playwright.

Estructura HTML (mayo 2026):
    <ul>
        <li>
            <h3>
                <a href="https://www.imf.org/en/publications/reo/wh/...">
                    Regional Economic Outlook for the Western Hemisphere, April 2026
                </a>
            </h3>
            <span>April 17, 2026</span>
            <span>Description:</span>
            <span>The Western Hemisphere entered 2026...</span>
        </li>
        ...
    </ul>
"""

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._playwright_helper import render_page

logger = logging.getLogger(__name__)

BASE_URL = "https://www.imf.org"

MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}


def parse(url):
    logger.info("--- IMF (Global) - Regional Economic Outlook")
    logger.info(f"IMF REO: fetching {url}")

    html = render_page(url, wait_for_selector='main li h3 a', timeout_ms=30000)
    if not html:
        return []

    items = _parse_html(html)
    logger.info(f"IMF REO: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    if not main:
        main = soup

    items = []
    for li in main.find_all('li'):
        # Solo procesamos listitems que tengan heading con link (son los artículos)
        heading = li.find(['h2', 'h3', 'h4'])
        if not heading:
            continue
        link = heading.find('a')
        if not link:
            continue

        try:
            item = _parse_item(li, heading, link)
            if item:
                items.append(item)
        except Exception as e:
            logger.warning(f"IMF REO: error parseando item: {e}")
            continue

    return items


def _parse_item(li, heading, link):
    href = (link.get('href') or '').strip()
    if not href:
        return None

    title = link.get_text(strip=True)
    if not title:
        return None

    # La fecha es un elemento hermano del heading dentro del li.
    date_str = ''
    for child in li.find_all(True):
        if child == heading or heading in child.parents:
            continue
        if child.find_parent(['h2', 'h3', 'h4']):
            continue
        text = child.get_text(strip=True)
        if re.search(r'\w+ \d{1,2}, 20\d{2}', text):
            date_str = text
            break

    full_url = urljoin(BASE_URL, href)

    return {
        'title': title,
        'url': full_url,
        'published': _parse_date(date_str),
        'summary': '',
    }


def _parse_date(date_str):
    """
    Parsea "Month DD, YYYY" → "YYYY-MM-DD".
    Ej: "April 17, 2026" → "2026-04-17".
    """
    if not date_str:
        return None

    match = re.search(
        r'(\w+)\s+(\d{1,2}),\s+(20\d{2})',
        date_str,
        re.IGNORECASE,
    )
    if not match:
        return None

    month = MONTHS.get(match.group(1).lower())
    day = int(match.group(2))
    year = int(match.group(3))

    if not month:
        return None

    try:
        datetime(year, month, day)
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None
