"""
Scraper para World Bank - News.

URL: https://www.worldbank.org/ext/en/news
Regulador: World Bank (World Bank Group)

Sitio client-rendered: requiere Playwright.

Estructura HTML real (mayo 2026):
    La página tiene un tablist con las categorías:
        Press Release, Statements, Feature Stories, Blogs, Speeches and Transcript.

    Todos los tabpanels están presentes en el DOM simultáneamente (SSR).

    Cada item de noticias tiene una URL con la fecha embebida:
        https://www.worldbank.org/en/news/{tipo}/YYYY/MM/DD/{slug}

    Tipos observados: press-release, statement, feature, speech, podcast, video.
    La fecha se extrae directamente del patrón /YYYY/MM/DD/ en la URL.

    Los blogs apuntan a blogs.worldbank.org (dominio externo), se omiten:
    no tienen fecha en la URL y no son worldbank.org canonical.
"""

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._playwright_helper import render_page

logger = logging.getLogger(__name__)

BASE_URL = "https://www.worldbank.org"

# Patrón de URL de noticias del World Bank: incluye la fecha en la ruta.
# Aplica a press-release, statement, feature, speech, podcast, video, etc.
_URL_PATTERN = re.compile(r'/en/news/[^/]+/(\d{4})/(\d{2})/(\d{2})/')


def parse(url):
    logger.info("--- World Bank (Global) - News")
    logger.info(f"World Bank News: fetching {url}")

    # wait_for_selector='[role="tablist"]' garantiza que el tablist con todas
    # las categorías ya está en el DOM antes de capturar el HTML.
    html = render_page(
        url,
        wait_for_selector='[role="tablist"]',
        timeout_ms=60000,
    )
    if not html:
        return []

    items = _parse_html(html)
    logger.info(f"World Bank News: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    seen_urls = set()

    for a in soup.find_all('a', href=True):
        href = a.get('href', '')

        # Solo enlaces a noticias del worldbank.org con fecha en la URL.
        m = _URL_PATTERN.search(href)
        if not m:
            continue

        # Normalizar a URL absoluta.
        full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Fecha extraída de la URL: /YYYY/MM/DD/
        published = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # Título: primer heading dentro del enlace, o texto completo del enlace.
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
