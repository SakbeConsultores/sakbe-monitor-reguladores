"""
Cliente HTTP para la base de datos de Notion.

Habla directo con la API de Notion (https://api.notion.com/v1).
Dos operaciones principales:

    get_existing_urls()  Trae todas las URLs ya guardadas en la base,
                         para dedupear localmente antes de insertar.

    insert_item(item)    Inserta un item nuevo. El item debe traer
                         todos los campos que mapean a las columnas
                         del schema de Notion.
"""

import time
import logging

import requests


log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Notion permite 3 requests por segundo en promedio.
# Dejamos margen para no rozar el límite.
RATE_LIMIT_SLEEP = 0.4

# Notion limita los campos rich_text a 2000 caracteres por bloque.
# Truncamos por seguridad.
MAX_TEXT = 2000


class NotionClient:
    """Wrapper minimal sobre la API REST de Notion."""

    def __init__(self, token: str, database_id: str):
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # -----------------------------------------------------------------
    # Lectura: traer URLs existentes para dedupear
    # -----------------------------------------------------------------
    def get_existing_urls(self) -> set:
        """
        Itera todas las páginas de la base de datos y devuelve un set
        con las URLs presentes en la columna URL.
        Notion entrega en páginas de 100; iteramos con paginación.
        """
        urls = set()
        cursor = None
        has_more = True

        while has_more:
            payload = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor

            resp = requests.post(
                f"{NOTION_API}/databases/{self.database_id}/query",
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for page in data.get("results", []):
                props = page.get("properties", {})
                url_prop = props.get("URL", {})
                if url_prop.get("type") == "url":
                    url_val = url_prop.get("url")
                    if url_val:
                        urls.add(url_val)

            has_more = data.get("has_more", False)
            cursor = data.get("next_cursor")
            time.sleep(RATE_LIMIT_SLEEP)

        log.info("Notion tiene %d URLs ya registradas", len(urls))
        return urls

    # -----------------------------------------------------------------
    # Escritura: insertar un item nuevo
    # -----------------------------------------------------------------
    def insert_item(self, item: dict) -> bool:
        """
        Crea una página nueva en la base. Devuelve True si tuvo éxito.

        El parámetro item debe traer estas llaves:
            title, url, published, summary,
            regulator, country, type, feed_url
        """
        properties = {
            "Título": {
                "title": [{"text": {"content": item["title"][:MAX_TEXT]}}]
            },
            "URL": {
                "url": item["url"]
            },
            "Resumen": {
                "rich_text": [{"text": {"content": item["summary"][:MAX_TEXT]}}]
            },
            "Regulador": {
                "select": {"name": item["regulator"]}
            },
            "Pais": {
                "select": {"name": item["country"]}
            },
            "Tipo": {
                "select": {"name": item["type"]}
            },
            "Feed RSS": {
                "rich_text": [{"text": {"content": item["feed_url"][:MAX_TEXT]}}]
            },
        }

        # La fecha solo se agrega si viene parseable.
        # Notion rechaza fechas vacías o mal formateadas.
        if item.get("published"):
            properties["Fecha Publicación"] = {
                "date": {"start": item["published"]}
            }

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
        }

        resp = requests.post(
            f"{NOTION_API}/pages",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        time.sleep(RATE_LIMIT_SLEEP)

        if resp.ok:
            return True

        # Loggeamos error con contexto suficiente para diagnosticar
        log.error(
            "Error insertando '%s': %s - %s",
            item["title"][:60],
            resp.status_code,
            resp.text[:300],
        )
        return False
