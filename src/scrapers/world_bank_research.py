"""
Scraper para World Bank - Research (Policy Research Working Papers).

URL: https://www.worldbank.org/en/research
Regulador: World Bank (World Bank Group)

Sitio client-rendered: requiere Playwright.

Estructura HTML real (mayo 2026):
    La sección "Policy Research Working Papers" es un <ul> donde cada <li>
    contiene, en este orden:
        1. Un elemento con la fecha: "May 20, 2026"
        2. Un <a href="http://documents.worldbank.org/curated/...">Título</a>

    La fecha NO está en la URL (las URLs son del tipo:
    /curated/undefined/NNNNNN/null), así que se extrae del texto
    del hermano anterior al <a> dentro del <li>.

    La sección "Blogs" (dominio blogs.worldbank.org) se omite.
    La sección "Open Knowledge Repository" no tiene fechas, se omite.
"""

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from scrapers._playwright_helper import render_page

logger = logging.getLogger(__name__)

# Prefijo que identifica los Policy Research Working Papers.
_WP_URL_PREFIX = "documents.worldbank.org/curated"

_MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}


def parse(url):
    logger.info("--- World Bank (Global) - Research")
    logger.info(f"World Bank Research: fetching {url}")

    # sleep_after_load_ms: la página tiene analytics en background que impiden
    # networkidle. Esperamos un tiempo fijo tras el evento load para que el
    # listado de working papers esté renderizado.
    html = render_page(
        url,
        sleep_after_load_ms=12000,
        timeout_ms=60000,
    )
    if not html:
        return []

    items = _parse_html(html)
    logger.info(f"World Bank Research: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    seen_urls = set()

    # Buscar todos los <a> que apunten a documents.worldbank.org/curated.
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if _WP_URL_PREFIX not in href:
            continue
        # Excluir el enlace "View All / docsearch" que comparte el prefijo
        # pero no es un paper individual.
        if '/docsearch/' in href:
            continue

        if href in seen_urls:
            continue
        seen_urls.add(href)

        title = a.get_text(strip=True)
        if not title:
            continue

        # La fecha está en el mismo <li> que el <a>, como primer texto.
        published = None
        parent_li = a.find_parent('li')
        if parent_li:
            # Recorrer todos los textos del <li> buscando "Mes D, YYYY".
            for text in parent_li.strings:
                text = text.strip()
                if re.match(r'[A-Za-z]+ \d{1,2}, 20\d{2}', text):
                    published = _parse_date(text)
                    break

        items.append({
            'title': title,
            'url': href,
            'published': published,
            'summary': '',
        })

    return items


def _parse_date(date_str):
    """
    Convierte "Month D, YYYY" → "YYYY-MM-DD" (string ISO).
    Ejemplo: "May 20, 2026" → "2026-05-20".
    Devuelve None si el formato no se reconoce.
    """
    if not date_str:
        return None

    m = re.search(r'(\w+)\s+(\d{1,2}),\s+(20\d{2})', date_str, re.IGNORECASE)
    if not m:
        return None

    month = _MONTHS.get(m.group(1).lower())
    day = int(m.group(2))
    year = int(m.group(3))

    if not month:
        return None

    try:
        # Validar fecha construyendo un datetime temporal (atrapa días inválidos).
        datetime(year, month, day)
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None
