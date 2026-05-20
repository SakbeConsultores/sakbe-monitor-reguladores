"""
Scraper para CNBV México - Documentos (Publicaciones).

URL: https://www.gob.mx/cnbv/archivo/documentos?idiom=es&filter_origin=archive
Regulador: CNBV (Comisión Nacional Bancaria y de Valores)

Sitio client-rendered: requiere Playwright.

Estructura HTML (mayo 2026):
    <article>
        <div>16 de enero de 2026<span>Fecha de publicación</span></div>
        <h3>Edictos publicados por la CNBV</h3>
        <a href="/cnbv/documentos/{slug}">Continuar leyendo</a>
    </article>

A diferencia de la página de Prensa, el link tiene texto "Continuar leyendo"
y el título está en el heading. La lógica de parseo es idéntica.
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
    logger.info("--- CNBV (MX) - Documentos")
    logger.info(f"CNBV Publications: fetching {url}")

    html = render_page(url, wait_for_selector='article', timeout_ms=30000)
    if not html:
        return []

    items = _parse_html(html)
    logger.info(f"CNBV Publications: {len(items)} items extraídos de {url}")
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
            logger.warning(f"CNBV Publications: error parseando artículo: {e}")
            continue

    return items


def _parse_article(article):
    # Fecha: buscamos cualquier elemento que contenga un hijo con
    # texto "Fecha de publicación".
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

    # Título: viene en el heading, no en el link
    heading = article.find(['h2', 'h3', 'h4'])
    link = article.find('a')

    if not link:
        return None

    href = (link.get('href') or '').strip()
    if not href:
        return None

    title = heading.get_text(strip=True) if heading else link.get_text(strip=True)
    if not title or title.lower() == 'continuar leyendo':
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
    Ej: "16 de enero de 2026" → "2026-01-16".
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
