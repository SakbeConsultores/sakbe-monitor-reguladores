"""
Scraper de EBA Publications.

Fuente: https://www.eba.europa.eu/publications-and-media/publications

Estructura observada del listado:
    - Cada publicación es un bloque con:
        * Fecha en formato "DD Month YYYY" (ej. "30 April 2026"), en inglés.
        * Título como <h4> con un <a> al PDF o página.
        * Opcionalmente un link "Download document" o "View press release".
    - El listado tiene paginación; por ahora solo procesamos la primera página
      (que trae los items más recientes, suficiente con filtro de 20 días).
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
BASE_URL = "https://www.eba.europa.eu"


# Meses en inglés para parseo de fecha
MONTHS_EN = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Regex: "30 April 2026", "1 May 2026", etc.
DATE_RE = re.compile(
    r"\b(\d{1,2})\s+("
    r"January|February|March|April|May|June|July|August|"
    r"September|October|November|December"
    r")\s+(\d{4})\b",
    re.IGNORECASE,
)


def parse(url: str) -> list:
    """Devuelve items recientes de EBA Publications."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("EBA Publications: fetch falló (%s): %s", url, e)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    items = []
    seen_urls = set()

    # Estrategia: cada h4 con un <a> dentro es probablemente un título de
    # publicación. Para cada uno buscamos la fecha en texto cercano hacia
    # atrás (la fecha precede al título en el HTML).
    for h4 in soup.find_all(["h3", "h4"]):
        link = h4.find("a")
        if not link or not link.get("href"):
            continue

        title = link.get_text(strip=True)
        href = link["href"].strip()
        if not title or not href:
            continue

        # Filtramos elementos que no son publicaciones reales (menús, etc.)
        # Las publicaciones de EBA suelen apuntar a /sites/default/files/
        # (PDFs) o a /publications-and-media/...
        if not _looks_like_publication(href):
            continue

        # URL absoluta
        if href.startswith("/"):
            href = BASE_URL + href
        if href in seen_urls:
            continue
        seen_urls.add(href)

        published = _find_nearby_date(h4)

        items.append({
            "title": title,
            "url": href,
            "published": published,
            "summary": "",  # EBA Publications no entrega resumen en el listing
        })

    log.info("EBA Publications: %d items extraídos de %s", len(items), url)
    return items


def _looks_like_publication(href: str) -> bool:
    """Filtra links que claramente no son publicaciones."""
    href_lower = href.lower()
    # Aceptamos PDFs y páginas de publicación
    if "/sites/default/files/" in href_lower:
        return True
    if "/publications-and-media/" in href_lower and "publications" in href_lower:
        return True
    # Rechazamos links de navegación y menús
    blacklist = (
        "/about-us", "/activities", "/risk-and-data-analysis",
        "/contacts", "/news-press/news/rss",
        "/themes/", "/user/", "/subscribe", "/extranet",
    )
    if any(b in href_lower for b in blacklist):
        return False
    return False  # Por defecto rechaza si no matchea criterios positivos


def _find_nearby_date(element) -> str:
    """
    Busca una fecha tipo 'DD Month YYYY' en el texto cercano antes del
    elemento. EBA pone la fecha como texto plano arriba del título.
    Devuelve formato ISO YYYY-MM-DD, o "" si no encuentra.
    """
    # Buscamos en todos los textos anteriores en el árbol
    for text in element.find_all_previous(string=DATE_RE, limit=5):
        m = DATE_RE.search(str(text))
        if m:
            day, month, year = m.groups()
            month_num = MONTHS_EN.get(month.lower())
            if month_num:
                try:
                    return f"{year}-{month_num}-{int(day):02d}"
                except ValueError:
                    pass
    return ""
