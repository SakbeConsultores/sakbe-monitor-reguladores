"""
Scraper para Banxico - Noticias, anuncios.

URL: https://www.banxico.org.mx/noticias/noticias001.html
Regulador: Banxico (Banco de México)

El sitio renderiza la tabla de noticias con JavaScript (el HTML inicial
llega vacío, con el mensaje "Su navegador no soporta o tiene Javascript
deshabilitado"). Por eso usamos el helper de Playwright para renderizar
antes de parsear con BeautifulSoup, igual que sbs_peru_news.

Estructura HTML observada (agosto 2026):
    <table class="table table-striped bmtableview">
      <tr>
        <td class="bmdateview">26/08/2026</td>
        <td class="bmtextview">
          <a href="/publicaciones-y-prensa/.../archivo.pdf">Título completo</a>
        </td>
      </tr>
      ...
    </table>

Sin paginación visible en el DOM inicial (20 filas por carga). Los
enlaces son relativos (a veces apuntan directo a un PDF).
"""

import re
import logging
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import _playwright_helper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.banxico.org.mx"

# Regex: "26/08/2026" (DD/MM/YYYY)
DATE_RE = re.compile(r"^\s*(\d{2})/(\d{2})/(\d{4})\s*$")


def parse(url: str) -> list:
    """
    Punto de entrada del scraper. Llamado por src/ingest.py vía el campo
    `scraper_module: banxico_news` en config/feeds.yaml.

    Args:
        url: URL de la página de noticias
             (https://www.banxico.org.mx/noticias/noticias001.html).

    Returns:
        list[dict] con items, cada uno con keys: title, url, published,
        summary. `published` es string ISO 'YYYY-MM-DD' o None (contrato
        del pipeline, ver src/ingest.py / is_too_old). Banxico no entrega
        resumen en el listado, así que `summary` siempre es ''.
    """
    logger.info("--- Banxico - Noticias, anuncios")
    logger.info("Banxico: renderizando %s", url)

    html = _playwright_helper.render_page(
        url,
        wait_for_selector="table.bmtableview",
        timeout_ms=30000,
    )

    if not html:
        logger.error("Banxico: no se pudo renderizar la página")
        return []

    items = _parse_html(html)
    logger.info("Banxico Noticias: %d items extraídos de %s", len(items), url)
    return items


def _parse_html(html: str) -> list:
    """
    Parsea el HTML renderizado y devuelve la lista de items.

    Función separada de parse() para poder testearla con HTML sintético
    sin necesidad de invocar Playwright.
    """
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.select_one("table.bmtableview")

    if not table:
        logger.warning(
            "Banxico: no se encontró table.bmtableview. "
            "¿Cambió la estructura del sitio?"
        )
        return []

    rows = table.select("tr")
    items = []
    for row in rows:
        try:
            item = _parse_row(row)
            if item:
                items.append(item)
        except Exception as e:
            # Una fila mala no debe romper toda la corrida.
            logger.warning("Banxico: error parseando fila: %s", e)
            continue

    return items


def _parse_row(row) -> dict:
    """
    Parsea una sola fila <tr> de la tabla.

    Returns:
        dict con el item, o None si falta data crítica (título o URL).
    """
    link = row.select_one("td.bmtextview a")
    if not link:
        return None

    title = link.get_text(strip=True)
    href = (link.get('href') or '').strip()
    if not title or not href:
        return None

    full_url = urljoin(BASE_URL, href)

    date_td = row.select_one("td.bmdateview")
    published = _parse_date(date_td.get_text(strip=True)) if date_td else None

    return {
        'title': title,
        'url': full_url,
        'published': published,
        'summary': '',
    }


def _parse_date(date_str: str):
    """
    Parsea fecha del sitio Banxico y la devuelve en formato ISO.

    Ejemplo: '26/08/2026' -> '2026-08-26'.

    Returns:
        str con formato 'YYYY-MM-DD', o None si el formato no coincide.
    """
    if not date_str:
        return None

    m = DATE_RE.match(date_str.strip())
    if not m:
        return None

    day, month, year = m.groups()
    try:
        # Valida que la fecha sea real (atrapa cosas como '32/08/2026'),
        # pero el return final es string, no datetime.
        datetime(int(year), int(month), int(day))
    except ValueError:
        return None

    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
