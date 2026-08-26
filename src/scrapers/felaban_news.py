"""
Scraper para FELABAN - Noticias.

URL: https://felaban.com/noticias/
Regulador: FELABAN (Federación Latinoamericana de Bancos)

El sitio es WordPress con el widget "Posts" de Elementor, renderizado en
el servidor (el HTML de la primera respuesta ya trae los items, sin
necesidad de JavaScript). La página no pagina: muestra un bloque fijo de
publicaciones recientes (7 items al momento de escribir este scraper).

Estructura HTML observada (agosto 2026):
    <article class="elementor-post elementor-grid-item post-NNNNN ...">
        <a class="elementor-post__thumbnail__link" href="...">...</a>
        <div class="elementor-post__text">
            <h3 class="elementor-post__title">
                <a href="https://felaban.com/slug-de-la-noticia/">Título</a>
            </h3>
            <div class="elementor-post__meta-data">
                <span class="elementor-post-date">agosto 25, 2026</span>
            </div>
            <div class="elementor-post__excerpt">
                <p>Resumen completo del item...</p>
            </div>
            <a class="elementor-post__read-more" href="...">Ampliar »</a>
        </div>
    </article>
"""

import re
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; SakbeMonitor/1.0; +https://sakbe.com) "
    "Python/requests"
)
TIMEOUT = 30

# Meses en español (minúsculas), tal como los publica el sitio:
# "agosto 25, 2026".
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Regex: "agosto 25, 2026" (mes en español, día, coma, año).
DATE_RE = re.compile(
    r"^\s*([a-záéíóúñ]+)\s+(\d{1,2}),\s*(\d{4})\s*$",
    re.IGNORECASE,
)


def parse(url: str) -> list:
    """
    Punto de entrada del scraper. Llamado por src/ingest.py vía el campo
    `scraper_module: felaban_news` en config/feeds.yaml.

    Args:
        url: URL de la página de noticias (https://felaban.com/noticias/).

    Returns:
        list[dict] con items, cada uno con keys: title, url, published,
        summary. `published` es string ISO 'YYYY-MM-DD' o None (contrato
        del pipeline, ver src/ingest.py / is_too_old).
    """
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("FELABAN Noticias: fetch falló (%s): %s", url, e)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    articles = soup.select("article.elementor-post")

    if not articles:
        log.warning(
            "FELABAN Noticias: 0 items encontrados en %s. "
            "¿Cambió la estructura del sitio?", url
        )
        return []

    items = []
    for article in articles:
        try:
            item = _parse_item(article)
            if item:
                items.append(item)
        except Exception as e:
            # Un item malo no debe romper toda la corrida.
            log.warning("FELABAN Noticias: error parseando item: %s", e)
            continue

    log.info("FELABAN Noticias: %d items extraídos de %s", len(items), url)
    return items


def _parse_item(article) -> dict:
    """Parsea un solo <article class="elementor-post">."""
    link = article.select_one(".elementor-post__title a")
    if not link:
        return None

    title = link.get_text(strip=True)
    href = (link.get("href") or "").strip()
    if not title or not href:
        return None

    date_span = article.select_one(".elementor-post-date")
    published = _parse_date(date_span.get_text(strip=True)) if date_span else None

    excerpt_p = article.select_one(".elementor-post__excerpt p")
    summary = excerpt_p.get_text(strip=True) if excerpt_p else ""

    return {
        "title": title,
        "url": href,
        "published": published,
        "summary": summary,
    }


def _parse_date(date_str: str):
    """
    Parsea fecha del sitio FELABAN y la devuelve en formato ISO.

    Ejemplo: 'agosto 25, 2026' -> '2026-08-25'.

    Returns:
        str con formato 'YYYY-MM-DD', o None si el formato no coincide.
    """
    if not date_str:
        return None

    m = DATE_RE.match(date_str.strip())
    if not m:
        return None

    month_name, day, year = m.groups()
    month = MESES.get(month_name.lower())
    if not month:
        return None

    try:
        # Valida que la fecha sea real (atrapa cosas como "32 agosto 2026"),
        # pero el return final es string, no datetime.
        datetime(int(year), month, int(day))
    except ValueError:
        return None

    return f"{int(year):04d}-{month:02d}-{int(day):02d}"
