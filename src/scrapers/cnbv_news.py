"""
Scraper para CNBV México - Prensa (Comunicados).

URL: https://www.gob.mx/cnbv/archivo/prensa?idiom=es
Regulador: CNBV (Comisión Nacional Bancaria y de Valores)

Sitio client-rendered: requiere Playwright.

Estructura HTML (mayo 2026):
    <article>
        <div>21 de abril de 2026<span>Fecha de publicación</span></div>
        <div>Comunicado</div>
        <h3><a href="/cnbv/prensa/{slug}?idiom=es">Título del comunicado</a></h3>
    </article>
"""

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._playwright_helper import render_page

logger = logging.getLogger(__name__)

BASE_URL = "https://www.gob.mx"

MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}


def parse(url):
    logger.info("--- CNBV (MX) - Prensa")
    logger.info(f"CNBV News: fetching {url}")

    html = render_page(url, wait_for_selector='article', timeout_ms=30000)
    if not html:
        return []

    items = _parse_html(html)
    logger.info(f"CNBV News: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    items = []

    for article in soup.find_all('article'):
        try:
            item = _parse_article(article)
            if item:
                items.append(item)
        except Exception as e:
            logger.warning(f"CNBV News: error parseando artículo: {e}")
            continue

    return items


def _parse_article(article):
    # Fecha: buscamos cualquier elemento que contenga un hijo con
    # texto "Fecha de publicación". El texto de fecha es el texto directo
    # del padre menos ese label.
    date_str = None
    for elem in article.find_all(True):
        child_texts = [
            c.get_text(strip=True)
            for c in elem.children
            if hasattr(c, 'get_text')
        ]
        if 'Fecha de publicación' in child_texts:
            full_text = elem.get_text(separator=' ', strip=True)
            date_str = full_text.replace('Fecha de publicación', '').strip()
            break

    # Heading y link
    heading = article.find(['h2', 'h3', 'h4'])
    link = article.find('a')

    if not link:
        return None

    href = (link.get('href') or '').strip()
    if not href:
        return None

    title = heading.get_text(strip=True) if heading else link.get_text(strip=True)
    if not title:
        return None

    full_url = urljoin(BASE_URL, href)

    return {
        'title': title,
        'url': full_url,
        'published': _parse_date(date_str),
        'summary': '',
    }


def _parse_date(date_str):
    """
    Parsea "DD de mes de YYYY" → "YYYY-MM-DD".
    Ej: "21 de abril de 2026" → "2026-04-21".
    """
    if not date_str:
        return None

    match = re.search(
        r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(20\d{2})',
        date_str,
        re.IGNORECASE,
    )
    if not match:
        return None

    day = int(match.group(1))
    month = MESES.get(match.group(2).lower())
    year = int(match.group(3))

    if not month:
        return None

    try:
        datetime(year, month, day)
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None
