"""
Sincronizacion diaria automatica con Integr@.

Ejecuta la sincronizacion completa:
1. Detecta documentos nuevos, modificados y eliminados en Integr@
2. Descarga documentos nuevos y actualiza modificados en SQLite
3. Regenera embeddings (Mistral/OpenAI)
4. Regenera resumenes ejecutivos
5. Reconstruye grafo de conocimiento

Uso manual:
    $env:INTEGRA_DB_SERVER="10.238.66.14"
    $env:MISTRAL_API_KEY="<tu_api_key>"
    python Codigo/sync_diario.py

Uso con Windows Task Scheduler (diario a las 2:00 AM):
    $action = New-ScheduledTaskAction -Execute "python" -Argument "Codigo/sync_diario.py" `
        -WorkingDirectory "C:\\Users\\1121871773\\OneDrive - agvco\\Documentos\\Agente Calidad Codigo"
    $trigger = New-ScheduledTaskTrigger -Daily -At 2am
    Register-ScheduledTask -TaskName "SyncIntegra" -Action $action -Trigger $trigger

Salida: log en Codigo/sync_diario.log
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ─── Cargar variables de entorno desde .env si existe ───
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    print(f"[sync_diario] Variables cargadas desde {ENV_PATH.name}")

# Configurar variables de entorno por defecto si no estan seteadas
os.environ.setdefault("INTEGRA_DB_SERVER", "10.238.66.14")

# Configurar logging
LOG_PATH = Path(__file__).parent / "sync_diario.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("sync_diario")


def main():
    log.info("=" * 60)
    log.info("  SINCRONIZACION DIARIA CON INTEGR@")
    log.info("  Fecha: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 60)

    # Verificar API key
    api_key = os.environ.get("MISTRAL_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.warning("No hay MISTRAL_API_KEY ni OPENAI_API_KEY. "
                    "Solo se sincronizaran documentos (sin embeddings/resumenes).")

    # Verificar servidor
    server = os.environ.get("INTEGRA_DB_SERVER")
    if not server:
        log.error("Falta INTEGRA_DB_SERVER. Define la variable de entorno.")
        sys.exit(1)
    log.info("Servidor Integr@: %s", server)

    # Importar y ejecutar sincronizacion
    sys.path.insert(0, str(Path(__file__).parent))

    try:
        from sync_incremental import sync_completo_con_embeddings
    except ImportError as e:
        log.error("No se pudo importar sync_incremental: %e", e)
        sys.exit(1)

    try:
        reporte = sync_completo_con_embeddings()

        if "error" in reporte:
            log.error("Error de sincronizacion: %s", reporte["error"])
            sys.exit(1)

        # Resumen final
        log.info("=" * 60)
        log.info("  RESUMEN DE SINCRONIZACION")
        log.info("=" * 60)
        log.info("  Documentos en Integr@: %s", reporte.get("total_integra", 0))
        log.info("  Documentos locales:    %s", reporte.get("total_local", 0))
        log.info("  Nuevos:                %s", len(reporte.get("nuevos", [])))
        log.info("  Modificados:           %s", len(reporte.get("modificados", [])))
        log.info("  Eliminados:            %s", len(reporte.get("eliminados", [])))
        log.info("  Sin cambios:           %s", reporte.get("sin_cambios", 0))
        log.info("  Tiempo:                %.1fs", reporte.get("tiempo_segundos", 0))

        if reporte.get("embeddings_regenerados"):
            log.info("  Embeddings:            Regenerados")
        elif reporte.get("embeddings_error"):
            log.warning("  Embeddings:            Error - %s", reporte["embeddings_error"])

        if reporte.get("resumenes_regenerados"):
            log.info("  Resumenes:             Regenerados")
        elif reporte.get("resumenes_error"):
            log.warning("  Resumenes:             Error - %s", reporte["resumenes_error"])

        if reporte.get("grafo_reconstruido"):
            log.info("  Grafo:                 Reconstruido")
        elif reporte.get("grafo_error"):
            log.warning("  Grafo:                 Error - %s", reporte["grafo_error"])

        log.info("=" * 60)
        log.info("  SINCRONIZACION DIARIA COMPLETADA")
        log.info("=" * 60)

    except Exception as e:
        log.error("Error fatal: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
