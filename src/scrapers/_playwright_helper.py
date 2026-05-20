"""
Helper compartido para scrapers que necesitan renderizar JavaScript.

Muchos sitios modernos cargan los items dinámicamente: el HTML inicial
viene vacío y un script en el navegador trae el contenido después.
Para esos casos, `requests + BeautifulSoup` no sirve porque solo ve la
cáscara vacía.

Este módulo abre un Chromium headless con Playwright, deja que la página
ejecute su JavaScript, y devuelve el HTML ya renderizado. Después cada
scraper lo parsea normal con BeautifulSoup.

Uso típico desde un scraper:

    from . import _playwright_helper

    html = _playwright_helper.render_page(
        url,
        wait_for_selector="div.list-news__item__body",
        timeout_ms=30000,
    )
    if not html:
        return []
    # ... parsear con BeautifulSoup
"""

import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

# User-Agent que se parece a un navegador real. Algunos sitios bloquean
# user-agents obvios de bots o headless. Este es Chrome estable en Linux.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def render_page(url, wait_for_selector=None, timeout_ms=30000, sleep_after_load_ms=0):
    """
    Abre una URL con Chromium headless y devuelve el HTML completamente
    renderizado (después de ejecutar JavaScript).

    Args:
        url: URL a renderizar.
        wait_for_selector: Selector CSS que debe aparecer en el DOM antes
            de capturar el HTML. Si se pasa, garantiza que la lista de
            items ya está poblada. Si no se pasa, esperamos a que la red
            quede en idle (sin requests pendientes).
        timeout_ms: Timeout máximo de cada paso (carga inicial y espera
            del selector), en milisegundos. Default 30 segundos.
        sleep_after_load_ms: Si se pasa un valor > 0 y no hay
            wait_for_selector, espera el evento "load" y luego duerme
            este número de ms para que el JS renderice el contenido.
            Útil para sitios con analytics en background que nunca
            alcanzan networkidle (ej. IMF).

    Returns:
        str con el HTML renderizado, o None si hubo cualquier error
        (timeout, fallo de red, sitio caído, etc.). El scraper que llame
        a esta función debe manejar el None devolviendo [] y loggeando.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            # Carga inicial. wait_until="domcontentloaded" significa
            # que esperamos a que el HTML esté parseado, pero no
            # necesariamente a que todos los recursos hayan cargado.
            # Es más rápido que "load" y suficiente para nuestro caso.
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            if wait_for_selector:
                # Espera explícita: el selector debe aparecer en el DOM.
                # Es la garantía más fuerte de que el contenido ya cargó.
                page.wait_for_selector(wait_for_selector, timeout=timeout_ms)
            elif sleep_after_load_ms > 0:
                # Para sitios que nunca alcanzan networkidle (analytics
                # en background). Esperamos el evento "load" y luego
                # dormimos un tiempo fijo para que el JS renderice.
                page.wait_for_load_state("load", timeout=timeout_ms)
                page.wait_for_timeout(sleep_after_load_ms)
            else:
                # Sin selector específico: esperamos a que la red quede
                # en idle (~500 ms sin requests). Fallback razonable.
                page.wait_for_load_state("networkidle", timeout=timeout_ms)

            html = page.content()
            browser.close()
            return html

    except PlaywrightTimeout as e:
        logger.error(f"Playwright timeout en {url}: {e}")
        return None
    except Exception as e:
        # Capturamos cualquier otro error (red, browser crashed, etc.)
        # para que un sitio caído no rompa toda la ingesta.
        logger.error(f"Playwright error en {url}: {e}")
        return None
