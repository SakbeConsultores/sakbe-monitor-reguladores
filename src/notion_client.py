"""
Cliente HTTP para la base de datos de Notion.

Habla directo con la API de Notion (https://api.notion.com/v1) e incluye:

    - Retries automáticos con backoff exponencial cuando hay timeout,
      error de red, rate limit (429) o error de servidor (5xx).
    - Timeout amplio (60s) porque Notion bajo carga puede tardar.
    - Manejo gracioso: si una request falla después de todos los retries,
      devuelve False/None en lugar de propagar la excepción, para no
      tumbar todo el script por una sola noticia problemática.

Dos operaciones principales:

    get_existing_urls()  Trae todas las URLs ya guardadas en la base,
                         para dedupear localmente antes de insertar.

    insert_item(item)    Inserta un item nuevo en la base.
"""

import time
import logging

import requests


log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Pausa entre requests para respetar el rate limit de Notion
# (oficialmente 3 req/seg en promedio, dejamos margen).
RATE_LIMIT_SLEEP = 0.4

# Notion bajo carga puede tardar más de 30s. Subimos a 60.
REQUEST_TIMEOUT = 60

# Cuántas veces reintentar una request fallida por causas transitorias.
MAX_RETRIES = 3

# Notion limita los rich_text a 2000 caracteres por bloque. Truncamos.
MAX_TEXT = 2000


class NotionClient:
    """Wrapper minimal sobre la API REST de Notion, con retries."""

    def __init__(self, token: str, database_id: str):
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # -----------------------------------------------------------------
    # Helper privado: request con retries
    # -----------------------------------------------------------------
    def _request_with_retry(self, method: str, url: str, json_data=None):
        """
        Hace una request a Notion con reintentos automáticos.

        Reintenta cuando:
            - Hay timeout o ConnectionError (problema de red).
            - Notion devuelve 429 (rate limit).
            - Notion devuelve 5xx (error de servidor).

        No reintenta cuando:
            - Notion devuelve 4xx que no sea 429 (problema del payload).

        Devuelve el objeto response si tuvo éxito, o None si falló
        después de agotar todos los reintentos.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=json_data,
                    timeout=REQUEST_TIMEOUT,
                )
                # Pausa siempre (incluso en error) para respetar rate limit
                time.sleep(RATE_LIMIT_SLEEP)

                # Caso éxito
                if resp.ok:
                    return resp

                # Rate limit explícito: Notion nos dice cuánto esperar
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    log.warning(
                        "Rate limit (429), esperando %ds (intento %d/%d)",
                        retry_after, attempt, MAX_RETRIES,
                    )
                    time.sleep(retry_after)
                    continue

                # Errores del servidor: backoff exponencial
                if resp.status_code >= 500:
                    wait = attempt * 3
                    log.warning(
                        "Server error %d, retry en %ds (intento %d/%d)",
                        resp.status_code, wait, attempt, MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue

                # Error del cliente (400, 401, 403, 404, etc): no reintenta
                log.error(
                    "Error %s a Notion: %d - %s",
                    method, resp.status_code, resp.text[:300],
                )
                return None

            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError) as e:
                wait = attempt * 3
                log.warning(
                    "Network error (%s), retry en %ds (intento %d/%d)",
                    type(e).__name__, wait, attempt, MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            except Exception as e:
                # Cualquier otra excepción inesperada: log y aborta este intento
                log.error("Excepción inesperada en request a Notion: %s", e)
                return None

        log.error("Notion request falló después de %d intentos", MAX_RETRIES)
        return None

    # -----------------------------------------------------------------
    # Lectura: traer URLs existentes para dedupear
    # -----------------------------------------------------------------
    def get_existing_urls(self) -> set:
        """
        Itera todas las páginas de la base y devuelve un set con las URLs
        presentes en la columna URL. Notion entrega en páginas de 100.
        """
        urls = set()
        cursor = None
        has_more = True

        while has_more:
            payload = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor

            resp = self._request_with_retry(
                "POST",
                f"{NOTION_API}/databases/{self.database_id}/query",
                json_data=payload,
            )

            # Si el query falla después de retries, abortamos: sin la lista
            # de URLs existentes, no podemos dedupear correctamente.
            if resp is None:
                raise RuntimeError(
                    "No se pudieron traer las URLs existentes de Notion "
                    "después de varios reintentos. Aborto."
                )

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

        log.info("Notion tiene %d URLs ya registradas", len(urls))
        return urls

    # -----------------------------------------------------------------
    # Escritura: insertar un item nuevo
    # -----------------------------------------------------------------
    def insert_item(self, item: dict) -> bool:
        """
        Crea una página nueva en la base. Devuelve True si tuvo éxito,
        False si falló después de los retries.

        El item debe traer estas llaves:
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
        if item.get("published"):
            properties["Fecha Publicación"] = {
                "date": {"start": item["published"]}
            }

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
        }

        resp = self._request_with_retry(
            "POST",
            f"{NOTION_API}/pages",
            json_data=payload,
        )

        if resp is None:
            log.error(
                "No se pudo insertar '%s' tras agotar retries",
                item["title"][:60],
            )
            return False

        return True
