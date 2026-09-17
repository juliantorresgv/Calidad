"""
[DESHABILITADO] Webhook de Integr@ para sincronizacion en tiempo real.

NOTA: Este modulo esta deshabilitado por defecto. No se ejecuta automaticamente.
Se mantiene como codigo disponible para el futuro, si el equipo de Integr@
configura notificaciones HTTP hacia este servidor.

Para sincronizacion, usar:
    - sync_diario.py (Task Scheduler diario a las 2:00 AM)
    - Tab "Sincronizacion" en Streamlit (boton on-demand)

Expone un endpoint HTTP que Integr@ puede llamar cuando un documento cambia.
Esto permite sincronizar inmediatamente sin esperar a la sync diaria.

Endpoint:
    POST /webhook/integra
    Body: {"evento": "create|update|delete", "codigo": "PGC-16-15", "timestamp": "..."}

Integracion con Integr@:
    Configurar en Integr@ un webhook que llame a este endpoint cuando:
    - Se publica un nuevo documento (evento=create)
    - Se modifica un documento existente (evento=update)
    - Se obsoleta/elimina un documento (evento=delete)

Uso:
    python Codigo/webhook_server.py
    # Webhook disponible en http://localhost:8080/webhook/integra
"""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Cargar .env si existe
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
    print(f"[webhook] Variables cargadas desde {ENV_PATH.name}")

LOG_PATH = Path(__file__).parent / "webhook.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("webhook")

# Token de autenticacion del webhook (configurar en .env)
WEBHOOK_TOKEN = os.environ.get("INTEGRA_WEBHOOK_TOKEN", "cambia-este-token")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8080"))


class WebhookHandler(BaseHTTPRequestHandler):
    """Handler del webhook de Integr@."""

    def do_POST(self):
        """Procesa notificaciones de Integr@."""
        if self.path != "/webhook/integra":
            self.send_response(404)
            self.end_headers()
            return

        # Verificar token
        auth_header = self.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "") if auth_header else ""
        if token != WEBHOOK_TOKEN:
            log.warning("Webhook: token invalido")
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "token invalido"}')
            return

        # Leer body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "JSON invalido"}')
            return

        evento = data.get("evento", "")
        codigo = data.get("codigo", "")
        timestamp = data.get("timestamp", datetime.now().isoformat())

        log.info(f"Webhook recibido: evento={evento} codigo={codigo} ts={timestamp}")

        # Procesar evento en background
        if evento and codigo:
            thread = threading.Thread(
                target=self._process_event,
                args=(evento, codigo, timestamp),
                daemon=True,
            )
            thread.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "mensaje": f"Evento {evento} para {codigo} en proceso",
                "timestamp": datetime.now().isoformat(),
            }).encode())
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "faltan evento o codigo"}')

    def do_GET(self):
        """Health check."""
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "service": "webhook-integra",
                "timestamp": datetime.now().isoformat(),
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def _process_event(self, evento: str, codigo: str, timestamp: str):
        """Procesa el evento en background (no bloquea la respuesta HTTP)."""
        try:
            log.info(f"Procesando evento {evento} para {codigo}...")

            if evento in ("create", "update"):
                # Sincronizar el documento especifico
                from sync_incremental import sync_incremental
                reporte = sync_incremental(solo_reporte=False, codigos_especificos=[codigo])
                log.info(f"Sync de {codigo}: {len(reporte.get('nuevos', []))} nuevos, "
                         f"{len(reporte.get('modificados', []))} modificados")

                # Regenerar embeddings y resumenes del documento
                try:
                    from generate_embeddings import main as gen_embeddings
                    gen_embeddings()
                    log.info(f"Embeddings regenerados para {codigo}")
                except Exception as e:
                    log.warning(f"Error regenerando embeddings: {e}")

                try:
                    from generar_resumenes import main as gen_resumenes
                    gen_resumenes()
                    log.info(f"Resumenes regenerados para {codigo}")
                except Exception as e:
                    log.warning(f"Error regenerando resumenes: {e}")

            elif evento == "delete":
                # Marcar documento como eliminado en SQLite
                import sqlite3
                db_path = Path(__file__).parent.parent / "indice_procedimientos.db"
                conn = sqlite3.connect(str(db_path))
                conn.execute(
                    "UPDATE procedimientos SET estado = 'ELIMINADO' WHERE codigo = ?",
                    (codigo,)
                )
                conn.commit()
                conn.close()
                log.info(f"Documento {codigo} marcado como ELIMINADO")

            else:
                log.warning(f"Evento desconocido: {evento}")

        except Exception as e:
            log.error(f"Error procesando evento {evento} para {codigo}: {e}", exc_info=True)

    def log_message(self, format, *args):
        """Redirige logs al logger."""
        log.info(format % args)


def main():
    log.info("=" * 60)
    log.info("  WEBHOOK SERVER DE INTEGR@")
    log.info(f"  Puerto: {WEBHOOK_PORT}")
    log.info(f"  Endpoint: POST http://localhost:{WEBHOOK_PORT}/webhook/integra")
    log.info(f"  Health: GET http://localhost:{WEBHOOK_PORT}/health")
    log.info(f"  Token: {WEBHOOK_TOKEN[:8]}...")
    log.info("=" * 60)

    server = HTTPServer(("0.0.0.0", WEBHOOK_PORT), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Webhook server detenido")
        server.shutdown()


if __name__ == "__main__":
    main()
