"""
Scraper para IMF - News.

URL: https://www.imf.org/en/news
Regulador: IMF (International Monetary Fund)

Sitio client-rendered: requiere Playwright.

Estructura HTML real (mayo 2026):
    No hay <main> ni <ul><li>. El contenido son tarjetas con:
        <a href="https://www.imf.org/en/news/articles/YYYY/MM/DD/{slug}"
           class="feature-card ...">
            <h4>Título del artículo</h4>
            ...
        </a>

    La fecha se extrae directamente de la URL (patrón /YYYY/MM/DD/).
"""

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._playwright_helper import render_page

logger = logging.getLogger(__name__)

BASE_URL = "https://www.imf.org"

# Patrón de URL de artículos de noticias del IMF: incluye la fecha.
_URL_PATTERN = re.compile(r'/en/news/articles/(\d{4})/(\d{2})/(\d{2})/')


def parse(url):
    logger.info("--- IMF (Global) - News")
    logger.info(f"IMF News: fetching {url}")

    html = render_page(url, sleep_after_load_ms=15000, timeout_ms=60000)
    if not html:
        return []

    items = _parse_html(html)
    logger.info(f"IMF News: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    seen_urls = set()

    for a in soup.find_all('a', href=True):
        href = a.get('href', '')

        # Solo enlaces a artículos de noticias con fecha en la URL
        m = _URL_PATTERN.search(href)
        if not m:
            continue

        # Normalizar URL absoluta
        full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Fecha extraída de la URL: /YYYY/MM/DD/
        published = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # Título: heading dentro del enlace, o texto completo del enlace
        heading = a.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        title = heading.get_text(strip=True) if heading else a.get_text(strip=True)

        if not title:
            continue

        items.append({
            'title': title,
            'url': full_url,
            'published': published,
            'summary': '',
        })

    return items
