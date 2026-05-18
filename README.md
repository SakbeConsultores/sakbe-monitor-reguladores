# Monitor de Reguladores Financieros

Pipeline de ingesta automatizada de comunicados oficiales de reguladores financieros internacionales hacia una base de Notion. Corre en GitHub Actions, sin costo. Hecho por Sakbé Consultores.

## Cómo funciona

Cada hora, GitHub Actions ejecuta `src/ingest.py`. El script lee la lista de fuentes en `config/feeds.yaml`, procesa cada feed (RSS estándar o scraping HTML según corresponda), deduplica contra lo que ya hay en Notion (comparando por URL), e inserta los items nuevos en la base "Monitor de Reguladores Financieros".

## Estructura del repositorio

```
sakbe-monitor-reguladores/
├── .github/workflows/ingest.yml    Cron de GitHub Actions
├── config/feeds.yaml               Lista de fuentes (EDITAR PARA AGREGAR)
├── src/
│   ├── ingest.py                   Script principal
│   ├── rss_parser.py               Lector de feeds RSS
│   ├── notion_client.py            Cliente HTTP de Notion
│   └── scrapers/                   Parsers HTML por sitio
├── requirements.txt                Dependencias Python
├── .env.template                   Plantilla para credenciales locales
└── .gitignore                      Bloquea .env y archivos temporales
```

## Agregar un regulador nuevo

Editar `config/feeds.yaml` y agregar un bloque con los campos `regulator`, `country`, `type`, `url`, y `source` (`rss` o `scraper`). Si es scraper, también `scraper_module` con el nombre del módulo en `src/scrapers/`. Hacer commit y push. El próximo run lo recogerá automáticamente.

## Variables de entorno

El script lee dos variables que en GitHub Actions vienen de Secrets:

- `NOTION_TOKEN`: Access token de la conexión "Sakbé Monitor Ingesta".
- `NOTION_DATABASE_ID`: ID de la base "Monitor de Reguladores Financieros".

Para correr local, duplicar `.env.template` como `.env` y rellenar los valores.

## Disparar una corrida manual

En GitHub, pestaña **Actions**, seleccionar el workflow "Ingest Reguladores Financieros" y click en **Run workflow**. Útil para validar cambios y para forzar una corrida fuera del cron horario.
