# Paquete de scrapers HTML para reguladores sin RSS oficial.
#
# Convención de cada módulo:
#   - Debe exponer una función `parse(url: str) -> list[dict]`.
#   - Cada item devuelto es un diccionario con las llaves:
#       title     str  título del comunicado
#       url       str  URL al comunicado original
#       published str  fecha ISO YYYY-MM-DD (vacío si no se pudo extraer)
#       summary   str  resumen, vacío si el listing no lo entrega
#
# El nombre del módulo se referencia desde config/feeds.yaml en el campo
# `scraper_module` de cada feed con `source: scraper`.
