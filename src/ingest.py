"""
Script principal de ingesta del Monitor de Reguladores Financieros.

Para cada feed definido en config/feeds.yaml:
    1. Lee los items (vía RSS o scraper, según el config).
    2. Filtra los que ya están en Notion (dedup por URL).
    3. Inserta los items nuevos en la base de Notion.

Está pensado para correr en GitHub Actions con cron job, pero también
funciona en local exportando las variables de entorno NOTION_TOKEN y
NOTION_DATABASE_ID.
"""

import os
import sys
import logging
import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

# Asegurar que src/ está en el path para imports relativos
SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))

import rss_parser
from notion_client import NotionClient


# Configuración global de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ingest")


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def load_config(config_path: Path) -> dict:
    """Lee y parsea el YAML de configuración de feeds."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_feed_items(feed_cfg: dict) -> list:
    """
    Dispatcher: según el source del feed, llama a rss_parser
    o al módulo de scraping correspondiente.
    """
    source = feed_cfg.get("source")
    url = feed_cfg.get("url")

    if source == "rss":
        return rss_parser.parse_feed(url)

    if source == "scraper":
        module_name = feed_cfg.get("scraper_module")
        if not module_name:
            log.error("Feed con source=scraper pero sin scraper_module: %s", url)
            return []
        try:
            module = importlib.import_module(f"scrapers.{module_name}")
            return module.parse(url)
        except ImportError:
            # Aún no hemos implementado este scraper. No es error fatal.
            log.warning("Scraper '%s' aún no implementado. Saltando %s",
                        module_name, url)
            return []
        except Exception as e:
            log.error("Error en scraper '%s' (%s): %s", module_name, url, e)
            return []

    log.error("Source desconocido '%s' para %s", source, url)
    return []


def is_too_old(published: str, max_age_days: int) -> bool:
    """
    Devuelve True si el item es más viejo que max_age_days.
    Si published está vacío o no parsea, devuelve False (lo deja pasar)
    porque algunos feeds no entregan fecha y preferimos capturar el item
    a perderlo. La decisión: errar del lado conservador en favor del usuario.
    """
    if not published:
        return False
    try:
        # rss_parser entrega published en formato YYYY-MM-DD
        item_date = datetime.strptime(published, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return item_date < cutoff


# -----------------------------------------------------------------
# Main
# -----------------------------------------------------------------

def main():
    # Credenciales y database id vienen de variables de entorno.
    # En GitHub Actions las inyectamos como secrets.
    # En local: export NOTION_TOKEN=... ; export NOTION_DATABASE_ID=...
    notion_token = os.environ.get("NOTION_TOKEN")
    notion_db_id = os.environ.get("NOTION_DATABASE_ID")

    if not notion_token or not notion_db_id:
        log.error("Faltan NOTION_TOKEN o NOTION_DATABASE_ID en el entorno")
        sys.exit(1)

    # Cargar configuración de feeds y settings globales
    config_path = SRC_DIR.parent / "config" / "feeds.yaml"
    config = load_config(config_path)
    feeds = config.get("feeds", [])
    settings = config.get("settings", {})
    max_age_days = settings.get("max_age_days", 20)

    log.info(
        "Procesando %d feeds. Filtro de antigüedad: %d días.",
        len(feeds), max_age_days,
    )

    # Cliente de Notion y carga de URLs ya guardadas para dedup
    notion = NotionClient(notion_token, notion_db_id)
    existing_urls = notion.get_existing_urls()

    # Contadores para el resumen final
    new_count = 0
    skipped_existing = 0  # ya estaba en Notion
    skipped_old = 0       # filtrado por max_age_days
    error_count = 0

    # Procesar cada feed
    for feed_cfg in feeds:
        regulator = feed_cfg.get("regulator", "?")
        country = feed_cfg.get("country", "?")
        feed_type = feed_cfg.get("type", "?")
        feed_url = feed_cfg.get("url", "")

        log.info("--- %s (%s) - %s", regulator, country, feed_type)

        items = fetch_feed_items(feed_cfg)

        for item in items:
            item_url = item.get("url", "")

            # Skip si no tiene URL o si ya está en Notion
            if not item_url or item_url in existing_urls:
                skipped_existing += 1
                continue

            # Skip si el item es más viejo que el límite configurado
            if is_too_old(item.get("published", ""), max_age_days):
                skipped_old += 1
                continue

            # Inyectar metadatos del config en el item
            item["regulator"] = regulator
            item["country"] = country
            item["type"] = feed_type
            item["feed_url"] = feed_url

            if notion.insert_item(item):
                # Agregamos al set local para evitar duplicados intra-corrida
                existing_urls.add(item_url)
                new_count += 1
            else:
                error_count += 1

    log.info(
        "Resumen final: %d nuevos, %d ya existían, %d muy viejos (>%dd), %d errores",
        new_count, skipped_existing, skipped_old, max_age_days, error_count,
    )


if __name__ == "__main__":
    main()
