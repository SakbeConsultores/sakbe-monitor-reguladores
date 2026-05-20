"""
Scraper para SuperFin Colombia - Comunicados de prensa.

URL: https://www.superfinanciera.gov.co/publicaciones/10102692/sala-de-prensacomunicados-de-prensa-comunicados-de-prensa-10102692/
Regulador: SuperFin (Superintendencia Financiera de Colombia)

El sitio es server-rendered: el HTML inicial ya viene con todo el
contenido, no necesita JavaScript. Por eso usamos requests + BeautifulSoup
directamente, sin Playwright. Es más rápido y más simple que el de SBS Perú.

Estructura HTML observada (mayo 2026):
    <h1>Comunicados de prensa 2026</h1>     <!-- el año está aquí -->
    <table>
        <thead><tr><th>Fecha</th><th>Tema</th><th>Información ...</th></tr></thead>
        <tbody>
            <tr>
                <td>Abril 09</td>
                <td><a href="https://www.superfinanciera.gov.co/10116081">
                    Finanzas abiertas obligatorias impulsarán...
                </a></td>
                <td></td>
            </tr>
            ...
        </tbody>
    </table>

NOTA IMPORTANTE sobre el año: La URL apunta a la página del año en curso
(2026). Cuando llegue 2027, la SFC va a publicar otra página con otro ID
para los comunicados del año nuevo. En ese momento hay que actualizar
config/feeds.yaml con la URL nueva. El scraper extrae el año del título
de la página, así que si se queda apuntando a 2026 en 2027, va a seguir
trayendo solo los comunicados viejos (no rompe, pero no trae lo nuevo).
"""

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.superfinanciera.gov.co"

# User-Agent que se parece a un navegador real. Algunos sitios gov.co
# rechazan user-agents obvios de bots (curl, python-requests).
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Mapa de meses en español (lowercase) a número de mes.
# El sitio publica fechas tipo "Abril 09" con primera letra mayúscula.
# Pasamos a lowercase antes de buscar para tolerar ambas variantes.
MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}


def parse(url):
    """
    Punto de entrada del scraper. Llamado por src/ingest.py vía el campo
    `scraper_module: superfin_news` en config/feeds.yaml.

    Args:
        url: URL de la página listada de comunicados de prensa del año.

    Returns:
        list[dict] con items, cada uno con keys:
            - title (str): título del comunicado, sin truncar.
            - url (str): URL absoluta del comunicado.
            - published (str | None): fecha 'YYYY-MM-DD'. Es string, no
              datetime, porque el pipeline (src/ingest.py) hace strptime
              sobre este campo.
            - summary (str): vacío. La tabla del sitio no incluye resumen.
    """
    logger.info(f"--- SuperFin Colombia - Comunicados de prensa")
    logger.info(f"SuperFin News: fetching {url}")

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        # Un sitio caído o un timeout no debe romper toda la ingesta.
        # Devolvemos lista vacía y dejamos que el pipeline siga.
        logger.error(f"SuperFin News: error fetching {url}: {e}")
        return []

    items = _parse_html(resp.text)
    logger.info(f"SuperFin News: {len(items)} items extraídos de {url}")
    return items


def _parse_html(html):
    """
    Parsea el HTML completo de la página y devuelve la lista de items.

    Función separada de parse() para poder testearla con HTML sintético
    sin necesidad de hacer requests HTTP reales en los tests.
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Año actual: lo sacamos del h1 de la página, ej. "Comunicados de
    # prensa 2026". Si no lo encontramos, los items se van a quedar
    # sin published (que el pipeline trata como item sin fecha).
    year = _extract_year(soup)
    if year:
        logger.info(f"SuperFin News: año detectado en el título = {year}")
    else:
        logger.warning(
            "SuperFin News: no se pudo extraer el año del título de la "
            "página. Los items se van a quedar sin fecha."
        )

    # La página tiene varias tablas (la del menú, etc.). Buscamos la
    # tabla que contiene comunicados: tiene una columna 'Fecha'.
    table = _find_news_table(soup)
    if not table:
        logger.warning(
            "SuperFin News: no se encontró la tabla de comunicados en la "
            "página. ¿Cambió la estructura del sitio?"
        )
        return []

    items = []
    for row in table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 2:
            # Header row (con th en lugar de td) o row vacía.
            continue

        try:
            item = _parse_row(cells, year)
            if item:
                items.append(item)
        except Exception as e:
            # Un row malo no debe romper toda la corrida.
            logger.warning(f"SuperFin News: error parseando row: {e}")
            continue

    return items


def _extract_year(soup):
    """
    Extrae el año de la página buscando el patrón 'Comunicados de prensa YYYY'
    en cualquier parte del texto del HTML.

    Antes el código buscaba solo en el primer <h1>, pero en el sitio real
    de SuperFin el primer <h1> es 'Superintendencia Financiera de Colombia'
    (el nombre del sitio), y el título 'Comunicados de prensa 2026' está
    en otro elemento (h2, breadcrumb o similar). Por eso ahora buscamos
    el patrón completo en todo el texto.

    Buscar el patrón contextualizado ('Comunicados de prensa YYYY') es más
    robusto que buscar cualquier '20XX' suelto, porque en una página gov.co
    aparecen muchos años por razones distintas (años de normativa, fechas
    de pie de página, etc.) que no son el año del listado.

    Returns:
        int o None si no se encuentra el patrón.
    """
    # get_text() con separator concatena todo el texto del HTML, incluyendo
    # lo que está dentro de h1, h2, divs, breadcrumbs, title, etc.
    text = soup.get_text(separator=' ')
    # IGNORECASE para tolerar 'Comunicados', 'COMUNICADOS', etc.
    match = re.search(
        r'comunicados\s+de\s+prensa\s+(20\d{2})',
        text,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    return None


def _find_news_table(soup):
    """
    Busca la tabla de comunicados.

    La página tiene varias tablas. La nuestra es la que tiene una
    cabecera con 'Fecha' como primera columna. Esto la distingue de
    tablas de menú, navegación, etc.

    Returns:
        bs4.Tag de la tabla, o None si no se encuentra.
    """
    for table in soup.find_all('table'):
        # Revisamos los headers de la tabla
        headers = table.find_all('th')
        if not headers:
            continue
        first_header = headers[0].get_text(strip=True).lower()
        if 'fecha' in first_header:
            return table
    return None


def _parse_row(cells, year):
    """
    Parsea una fila de la tabla. cells es la lista de <td>.

    Estructura esperada:
        cells[0] = fecha, ej. "Abril 09"
        cells[1] = link al comunicado, con el título como texto del <a>
        cells[2] = (opcional) "Información relacionada", ignorable

    Returns:
        dict con el item, o None si falta data crítica (título o URL).
    """
    date_str = cells[0].get_text(strip=True)

    link = cells[1].find('a')
    if not link:
        return None

    title = link.get_text(strip=True)
    href = (link.get('href') or '').strip()
    if not title or not href:
        return None

    # En el HTML que vimos las URLs ya son absolutas, pero por si acaso
    # alguna viene relativa, urljoin la resuelve correctamente.
    full_url = urljoin(BASE_URL, href)

    published = _parse_date(date_str, year)

    return {
        'title': title,
        'url': full_url,
        'published': published,
        'summary': '',
    }


def _parse_date(date_str, year):
    """
    Parsea fecha del sitio en formato 'Mes DD' combinado con el año
    que vino del título de la página.

    Ej: ('Abril 09', 2026) -> '2026-04-09'.

    Returns:
        str en formato ISO 'YYYY-MM-DD', o None si no se puede parsear.
    """
    if not date_str or not year:
        return None

    parts = date_str.strip().lower().split()
    if len(parts) != 2:
        return None

    try:
        month = MESES.get(parts[0])
        day = int(parts[1])
        if not month:
            return None
        # Validamos que la fecha es real (atrapa cosas como 'Febrero 30').
        datetime(year, month, day)
        return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, KeyError):
        return None
