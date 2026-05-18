"""
Lector de feeds RSS y Atom.

Usa la librería feedparser para procesar feeds estándar.
Devuelve una lista de items normalizados con la misma estructura
que producirán los scrapers (módulos en src/scrapers/), de modo
que el resto del pipeline no distingue entre RSS y scraping.
"""

import re
import logging
from datetime import datetime, timezone

import feedparser


log = logging.getLogger(__name__)


def parse_feed(url: str) -> list[dict]:
    """
    Parsea un feed RSS y devuelve una lista de items.

    Cada item es un diccionario con:
        title     - título del comunicado (str)
        url       - URL al comunicado original (str)
        published - fecha en formato ISO 8601 YYYY-MM-DD (str, puede ser "")
        summary   - resumen del item, sin HTML (str, puede ser "")
    """
    feed = feedparser.parse(url)

    # Si feedparser marca un error y no obtuvo entries, abortamos
    if feed.bozo and not feed.entries:
        log.warning("Feed con problemas: %s - %s", url, feed.bozo_exception)
        return []

    items = []
    for entry in feed.entries:
        title = _clean(entry.get("title", ""))
        link = entry.get("link", "")
        summary = _clean(
            entry.get("summary", "")
            or entry.get("description", "")
        )
        published = _parse_date(entry)

        # Skip items sin título o sin link, no nos sirven
        if not title or not link:
            continue

        items.append({
            "title": title,
            "url": link,
            "published": published,
            "summary": summary,
        })

    log.info("Feed %s entregó %d items", url, len(items))
    return items


def _clean(text: str) -> str:
    """Quita etiquetas HTML, normaliza espacios y decodifica entidades."""
    if not text:
        return ""
    # Quitar tags HTML
    text = re.sub(r"<[^>]+>", " ", text)
    # Decodificar entidades HTML básicas
    text = (text
            .replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'"))
    # Normalizar espacios
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(entry) -> str:
    """
    Extrae la fecha del item RSS y devuelve YYYY-MM-DD.
    feedparser ya parsea la fecha en .published_parsed (tupla).
    Si no hay fecha válida, retorna "".
    """
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                continue
    return ""
