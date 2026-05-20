"""
Scraper para IMF - News (Latest News).

URL: https://www.imf.org/en/news
Regulador: IMF (International Monetary Fund)

Sitio client-rendered: requiere Playwright.

Estructura HTML (mayo 2026):
    <h2>Latest News</h2>
    <ul>
        <li>
            <a href="/en/news/articles/2026/05/18/{slug}">
                IMF Executive Board Concludes...
                <span>May 18, 2026</span>
            </a>
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
    logger.info("--- IMF (Global) - News")
    logger.info(f"IMF News: fetching {url}")

    html = render_page(url, sleep_after_load_ms=15000, timeout_ms=60000)
    if not html:
        return []

    logger.info(f"IMF News: 'Latest News' en HTML: {'latest news' in html.lower()}")
    pos = html.lower().find('latest news')
    if pos >= 0:
        logger.info(f"IMF News: HTML alrededor de 'Latest News': {html[max(0, pos - 200):pos + 1000]}")
    items = _parse_html(html)
    logger.info(f"IMF News: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    if not main:
        main = soup

    # Buscar heading "Latest News" dentro de main y tomar el ul siguiente
    news_list = _find_list_after_heading(main, 'Latest News')
    if not news_list:
        logger.warning("IMF News: no se encontró la sección 'Latest News'")
        return []

    items = []
    for li in news_list.find_all('li'):
        try:
            item = _parse_item(li)
            if item:
                items.append(item)
        except Exception as e:
            logger.warning(f"IMF News: error parseando item: {e}")
            continue

    return items


def _parse_item(li):
    link = li.find('a')
    if not link:
        return None

    href = (link.get('href') or '').strip()
    if not href:
        return None

    # La fecha está en un elemento hijo del link.
    # Extraemos su texto y lo quitamos del texto completo para obtener el título.
    date_el = None
    for child in link.find_all(True):
        text = child.get_text(strip=True)
        if re.search(r'\w+ \d{1,2}, 20\d{2}', text):
            date_el = child
            break

    date_str = date_el.get_text(strip=True) if date_el else ''
    full_text = link.get_text(separator=' ', strip=True)
    title = full_text.replace(date_str, '').strip()

    if not title:
        return None

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
    Ej: "May 18, 2026" → "2026-05-18".
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
