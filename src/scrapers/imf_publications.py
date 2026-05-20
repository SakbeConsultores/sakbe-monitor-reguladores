"""
Scraper para IMF - Publications (Latest Releases).

URL: https://www.imf.org/en/publications
Regulador: IMF (International Monetary Fund)

Sitio client-rendered: requiere Playwright.

Estructura HTML real (mayo 2026):
    <div id="latest-publications">
      <h5 id="latestPublicationsTitle" aria-level="2">Latest Releases</h5>
      <ul id="latestPublicationsList">
        <li>
          <div class="high">
            <p><a href="https://www.imf.org/en/publications/...">Título</a></p>
            <p class="date"></p>
            <p class="date">May 20, 2026</p>
          </div>
        </li>
        ...
      </ul>
    </div>

Notas:
- El heading es <h5>, no <h2> (por eso fallaba _find_list_after_heading).
- El <ul> tiene id="latestPublicationsList" — se busca directamente por id.
- Hay dos <p class="date"> por item; el primero está vacío, el segundo tiene la fecha.
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

    html = render_page(url, sleep_after_load_ms=15000, timeout_ms=60000)
    if not html:
        return []

    items = _parse_html(html)
    logger.info(f"IMF Publications: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')

    # Buscar directamente por id del ul (más robusto que buscar por heading h5)
    releases_list = soup.find('ul', id='latestPublicationsList')
    if not releases_list:
        logger.warning("IMF Publications: no se encontró ul#latestPublicationsList")
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

    # Fecha: primer <p class="date"> con texto no vacío
    date_str = ''
    for p in li.find_all('p', class_='date'):
        text = p.get_text(strip=True)
        if text:
            date_str = text
            break

    full_url = href if href.startswith('http') else urljoin(BASE_URL, href)

    return {
        'title': title,
        'url': full_url,
        'published': _parse_date(date_str),
        'summary': '',
    }


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
