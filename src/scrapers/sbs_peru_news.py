"""
Scraper para SBS Perú - Notas de Prensa.

URL: https://www.sbs.gob.pe/notadeprensa
Regulador: SBS Perú (Superintendencia de Banca, Seguros y AFP)

El sitio es client-rendered: el HTML inicial viene vacío y los items
se cargan después con JavaScript. Por eso usamos el helper de Playwright
para renderizar antes de parsear con BeautifulSoup.

Estructura HTML observada (mayo 2026):
    <div class="list-news__item__body">
        <div class="list-news__item__title-section">Nota de prensa</div>
        <header class="list-news__item__header">
            <h3 class="list-news__item__header__title">
                <a href="/noticia/detallenoticia?IdNoticia=NNNN"
                   title="Título completo sin truncar">
                    <span>Título truncado ...</span>
                </a>
            </h3>
            <div class="date">15 MAYO 2026</div>
        </header>
        <div class="list-news__item__text">
            <p>
                <span>Resumen <a>...</a></span>
            </p>
        </div>
    </div>
"""

import logging
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import _playwright_helper

logger = logging.getLogger(__name__)

# Base URL para convertir las URLs relativas del sitio en absolutas.
BASE_URL = "https://www.sbs.gob.pe"

# Mapa de meses en español (mayúsculas) a número.
# El sitio publica fechas tipo "15 MAYO 2026", todo en mayúsculas y en
# español. Como Python no tiene un locale garantizado en GitHub Actions,
# parseamos manualmente con este diccionario.
MESES = {
    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4,
    'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
    'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12,
}


def parse(url):
    """
    Punto de entrada del scraper. Llamado por src/ingest.py vía el campo
    `scraper_module: sbs_peru_news` en config/feeds.yaml.

    Args:
        url: URL de la página listada (https://www.sbs.gob.pe/notadeprensa).

    Returns:
        list[dict] con items, cada uno con keys:
            - title (str): título completo sin truncar
            - url (str): URL absoluta de la nota
            - published (datetime | None): fecha de publicación
            - summary (str): resumen del item
    """
    logger.info(f"--- SBS Perú - Notas de Prensa")
    logger.info(f"SBS Perú: renderizando {url}")

    # Esperamos a que aparezca el primer item antes de capturar el HTML.
    # Si el selector nunca aparece (sitio caído, cambio de estructura),
    # render_page devuelve None y nosotros devolvemos lista vacía.
    html = _playwright_helper.render_page(
        url,
        wait_for_selector="div.list-news__item__body",
        timeout_ms=30000,
    )

    if not html:
        logger.error(f"SBS Perú: no se pudo renderizar la página")
        return []

    items = _parse_html(html)
    logger.info(f"SBS Perú Notas de Prensa: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    """
    Parsea el HTML renderizado y devuelve la lista de items.

    Función separada de parse() para poder testearla con HTML sintético
    sin necesidad de invocar Playwright. Útil cuando no podemos correr
    Chromium en el sandbox (ej. durante tests locales).
    """
    soup = BeautifulSoup(html, 'html.parser')
    items_html = soup.select("div.list-news__item__body")

    if not items_html:
        logger.warning(
            "SBS Perú: 0 items encontrados en el HTML renderizado. "
            "¿Cambió la estructura del sitio?"
        )
        return []

    items = []
    for item_html in items_html:
        try:
            item = _parse_item(item_html)
            if item:
                items.append(item)
        except Exception as e:
            # Un item malo no debe romper toda la corrida. Lo loggeamos
            # y seguimos con los demás.
            logger.warning(f"SBS Perú: error parseando item: {e}")
            continue

    return items


def _parse_item(item_html):
    """
    Parsea un solo bloque .list-news__item__body.

    Returns:
        dict con el item, o None si falta data crítica (título o URL).
    """
    # Título y URL: ambos vienen del <a> dentro del header.
    link = item_html.select_one("h3.list-news__item__header__title a")
    if not link:
        return None

    # Preferimos el atributo "title" sobre el texto visible, porque el
    # visible viene truncado con "..." mientras que title trae completo.
    title = (link.get('title') or '').strip()
    if not title:
        # Fallback: si no hay atributo title, usamos el span (truncado).
        span = link.select_one('span')
        title = span.get_text(strip=True) if span else ''

    if not title:
        return None

    # URL relativa → absoluta.
    href = (link.get('href') or '').strip()
    if not href:
        return None
    full_url = urljoin(BASE_URL, href)

    # Fecha en formato "DD MES YYYY", ej. "15 MAYO 2026".
    date_div = item_html.select_one("div.date")
    published = None
    if date_div:
        published = _parse_date(date_div.get_text(strip=True))

    # Resumen: texto del <span> dentro del primer <p> del bloque de texto.
    summary = ''
    text_p = item_html.select_one("div.list-news__item__text p")
    if text_p:
        span = text_p.select_one('span')
        if span:
            # El span suele tener un <a>...</a> al final como link
            # "continuar leyendo". Lo removemos antes de extraer texto.
            for a in span.select('a'):
                a.decompose()
            summary = span.get_text(strip=True)

    return {
        'title': title,
        'url': full_url,
        'published': published,
        'summary': summary,
    }


def _parse_date(date_str):
    """
    Parsea fecha del sitio SBS en formato 'DD MES YYYY'.

    Ejemplo: '15 MAYO 2026' -> datetime(2026, 5, 15).

    Returns:
        datetime o None si el formato no coincide.
    """
    if not date_str:
        return None

    parts = date_str.strip().upper().split()
    if len(parts) != 3:
        return None

    try:
        day = int(parts[0])
        month = MESES.get(parts[1])
        year = int(parts[2])
        if not month:
            return None
        return datetime(year, month, day)
    except (ValueError, KeyError):
        return None
