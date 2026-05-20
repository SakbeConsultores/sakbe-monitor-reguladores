"""
Scraper para IMF - Publications (Latest Releases).

URL: https://www.imf.org/en/publications
Regulador: IMF (International Monetary Fund)

Sitio client-rendered: requiere Playwright.

Estructura HTML (mayo 2026):
    <h2>Latest Releases</h2>
    <ul>
        <li>
            <a href="https://www.imf.org/en/publications/...">
                Republic of Kyrgyzstan: Review of...
            </a>
            <span>May 19, 2026</span>
        </li>
        ...
    </ul>

A diferencia de imf_news, la fecha es un elemento hermano del link,
no un hijo.
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
    logger.info("--- IMF (Global) - Publications")
    logger.info(f"IMF Publications: fetching {url}")

    html = render_page(url, sleep_after_load_ms=8000, timeout_ms=60000)
    if not html:
        return []

    items = _parse_html(html)
    logger.info(f"IMF Publications: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    if not main:
        main = soup

    # Buscar heading "Latest Releases" y tomar el ul siguiente
    releases_list = _find_list_after_heading(main, 'Latest Releases')
    if not releases_list:
        logger.warning("IMF Publications: no se encontró la sección 'Latest Releases'")
        return []

    items = []
    for li in releases_list.find_all('li'):
        try:
            item = _parse_item(li)
            if item:
                items.append(item)
        except Exception as e:
            logger.warning(f"IMF Publications: error parseando item: {e}")
            continue

    return items


def _parse_item(li):
    link = li.find('a')
    if not link:
        return None

    href = (link.get('href') or '').strip()
    if not href:
        return None

    title = link.get_text(strip=True)
    if not title:
        return None

    # La fecha es un elemento hermano del link dentro del li.
    # Buscamos cualquier elemento en el li que tenga patrón de fecha.
    date_str = ''
    for child in li.find_all(True):
        if child == link or link in child.parents:
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


def _find_list_after_heading(soup, heading_text):
    for tag in soup.find_all(['h1', 'h2', 'h3', 'h4']):
        if heading_text.lower() in tag.get_text().lower():
            sib = tag.find_next_sibling('ul')
            if sib:
                return sib
    return None


def _parse_date(date_str):
    """
    Parsea "Month DD, YYYY" → "YYYY-MM-DD".
    Ej: "May 19, 2026" → "2026-05-19".
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
