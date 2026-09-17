"""
Observabilidad avanzada: OpenTelemetry, Sentry error tracking,
quality dashboards, cost alerts y latency percentiles.

Extiende el modulo observabilidad.py existente con capacidades enterprise.
"""
import os
import json
import sqlite3
import time
import math
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parent.parent / "indice_procedimientos.db"


# ──────────────────────────────────────────────
# 1. OpenTelemetry (distributed tracing)
# ──────────────────────────────────────────────

# Intentar importar OpenTelemetry (opcional)
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.trace import Status, StatusCode
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False
    trace = None


class TelemetryManager:
    """Gestiona distributed tracing con OpenTelemetry o fallback a SQLite."""

    def __init__(self, service_name: str = "agente-calidad-integra"):
        self.service_name = service_name
        self.tracer = None
        self._spans: list[dict] = []  # fallback en memoria

        if _HAS_OTEL:
            try:
                resource = Resource.create({
                    "service.name": service_name,
                    "service.version": "1.0",
                })
                provider = TracerProvider(resource=resource)

                # Exporter OTLP (si esta configurado)
                otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
                if otlp_endpoint:
                    exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                    provider.add_span_processor(BatchSpanProcessor(exporter))

                trace.set_tracer_provider(provider)
                self.tracer = trace.get_tracer(service_name)
                print(f"  [Telemetry] OpenTelemetry activo (service: {service_name})")
            except Exception as e:
                print(f"  [Telemetry] OpenTelemetry no disponible: {e}")
                self.tracer = None
        else:
            print(f"  [Telemetry] Usando fallback SQLite (instalar opentelemetry-sdk para OTLP)")

    def start_span(self, name: str, attributes: dict = None):
        """Inicia un span de tracing."""
        if self.tracer:
            span = self.tracer.start_span(name, attributes=attributes or {})
            return span
        # Fallback: span en memoria
        span_data = {
            "name": name,
            "start_time": time.time(),
            "attributes": attributes or {},
            "events": [],
        }
        return _FallbackSpan(span_data)

    def end_span(self, span, status: str = "OK", attributes: dict = None):
        """Finaliza un span."""
        if hasattr(span, "__enter__"):
            # Es un span real de OTel
            if status == "ERROR":
                span.set_status(Status(StatusCode.ERROR))
            else:
                span.set_status(Status(StatusCode.OK))
            if attributes:
                span.set_attributes(attributes)
            span.end()
        elif isinstance(span, _FallbackSpan):
            span.data["end_time"] = time.time()
            span.data["duration_ms"] = (span.data["end_time"] - span.data["start_time"]) * 1000
            span.data["status"] = status
            if attributes:
                span.data["attributes"].update(attributes)
            self._spans.append(span.data)
            self._save_span_to_db(span.data)

    def _save_span_to_db(self, span_data: dict):
        """Guarda span en SQLite (fallback)."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_spans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    name TEXT,
                    duration_ms REAL,
                    status TEXT,
                    attributes TEXT
                )
            """)
            conn.execute("""
                INSERT INTO telemetry_spans (name, duration_ms, status, attributes)
                VALUES (?, ?, ?, ?)
            """, (
                span_data["name"],
                span_data.get("duration_ms", 0),
                span_data.get("status", "OK"),
                json.dumps(span_data.get("attributes", {}), ensure_ascii=False),
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass


class _FallbackSpan:
    """Span de fallback cuando OpenTelemetry no esta disponible."""
    def __init__(self, data: dict):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key, value):
        self.data["attributes"][key] = value

    def add_event(self, name, attributes=None):
        self.data["events"].append({"name": name, "attributes": attributes or {}})

    def end(self):
        self.data["end_time"] = time.time()
        self.data["duration_ms"] = (self.data["end_time"] - self.data["start_time"]) * 1000


# Instancia global
_telemetry: Optional[TelemetryManager] = None


def get_telemetry() -> TelemetryManager:
    """Obtiene instancia singleton del telemetry manager."""
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetryManager()
    return _telemetry


def trace_operation(name: str):
    """Decorador para tracing automatico de funciones."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            telemetry = get_telemetry()
            span = telemetry.start_span(name, {
                "function": func.__name__,
                "module": func.__module__,
            })
            try:
                result = func(*args, **kwargs)
                telemetry.end_span(span, "OK")
                return result
            except Exception as e:
                telemetry.end_span(span, "ERROR", {"error": str(e)})
                raise
        return wrapper
    return decorator


# ──────────────────────────────────────────────
# 2. Sentry Error Tracking
# ──────────────────────────────────────────────

try:
    import sentry_sdk
    _HAS_SENTRY = True
except ImportError:
    _HAS_SENTRY = False


def init_sentry(dsn: str = None, environment: str = "production"):
    """Inicializa Sentry para captura automatica de errores."""
    if not _HAS_SENTRY:
        print("  [Sentry] No disponible (pip install sentry-sdk)")
        return False

    dsn = dsn or os.environ.get("SENTRY_DSN")
    if not dsn:
        print("  [Sentry] No configurado (falta SENTRY_DSN)")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
            send_default_pii=False,  # No enviar PII
            before_send=_sentry_scrub_pii,
        )
        print(f"  [Sentry] Activo (env: {environment})")
        return True
    except Exception as e:
        print(f"  [Sentry] Error: {e}")
        return False


def _sentry_scrub_pii(event: dict, hint: dict) -> dict:
    """Scrub PII antes de enviar a Sentry."""
    from calidad_seguridad import redact_pii_in_log

    # Scrub message
    if "message" in event:
        event["message"] = redact_pii_in_log(str(event["message"]))

    # Scrub exception values
    if "exception" in event:
        for exc in event["exception"].get("values", []):
            if "value" in exc:
                exc["value"] = redact_pii_in_log(str(exc["value"]))

    # Scrub request body
    if "request" in event:
        if "data" in event["request"]:
            event["request"]["data"] = redact_pii_in_log(str(event["request"]["data"]))

    return event


def capture_exception(exc: Exception, context: dict = None):
    """Captura una excepcion en Sentry o fallback a SQLite."""
    if _HAS_SENTRY and sentry_sdk.Hub.current.client:
        if context:
            for key, value in context.items():
                sentry_sdk.set_tag(key, str(value))
        sentry_sdk.capture_exception(exc)
    else:
        # Fallback: guardar en SQLite
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    error_type TEXT,
                    error_message TEXT,
                    traceback TEXT,
                    context TEXT
                )
            """)
            import traceback
            conn.execute("""
                INSERT INTO error_log (error_type, error_message, traceback, context)
                VALUES (?, ?, ?, ?)
            """, (
                type(exc).__name__,
                str(exc),
                traceback.format_exc(),
                json.dumps(context or {}, ensure_ascii=False),
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass


# ──────────────────────────────────────────────
# 3. Latency Percentiles (P50, P95, P99)
# ──────────────────────────────────────────────

def record_latency(operation: str, duration_ms: float, conn: sqlite3.Connection = None):
    """Registra latencia de una operacion."""
    own_conn = False
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH))
        own_conn = True

    conn.execute("""
        CREATE TABLE IF NOT EXISTS latency_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            operation TEXT NOT NULL,
            duration_ms REAL NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO latency_metrics (operation, duration_ms) VALUES (?, ?)
    """, (operation, duration_ms))
    conn.commit()

    if own_conn:
        conn.close()


def get_latency_percentiles(conn: sqlite3.Connection, operation: str = None,
                             hours: int = 24) -> dict:
    """Calcula percentiles de latencia (P50, P95, P99)."""
    since = (datetime.now() - timedelta(hours=hours)).isoformat()

    if operation:
        rows = conn.execute("""
            SELECT duration_ms FROM latency_metrics
            WHERE operation = ? AND timestamp > ?
            ORDER BY duration_ms
        """, (operation, since)).fetchall()
    else:
        rows = conn.execute("""
            SELECT duration_ms FROM latency_metrics
            WHERE timestamp > ?
            ORDER BY duration_ms
        """, (since,)).fetchall()

    if not rows:
        return {"p50": 0, "p95": 0, "p99": 0, "count": 0}

    durations = [r[0] for r in rows]
    n = len(durations)

    return {
        "p50": round(durations[int(n * 0.50)], 2),
        "p95": round(durations[int(n * 0.95)], 2),
        "p99": round(durations[int(n * 0.99)], 2),
        "min": round(min(durations), 2),
        "max": round(max(durations), 2),
        "avg": round(sum(durations) / n, 2),
        "count": n,
    }


def get_latency_by_operation(conn: sqlite3.Connection, hours: int = 24) -> dict:
    """Obtiene latencia por tipo de operacion."""
    since = (datetime.now() - timedelta(hours=hours)).isoformat()

    rows = conn.execute("""
        SELECT operation, COUNT(*), AVG(duration_ms), MIN(duration_ms), MAX(duration_ms)
        FROM latency_metrics
        WHERE timestamp > ?
        GROUP BY operation
        ORDER BY AVG(duration_ms) DESC
    """, (since,)).fetchall()

    return {
        r[0]: {"count": r[1], "avg_ms": round(r[2], 2),
               "min_ms": round(r[3], 2), "max_ms": round(r[4], 2)}
        for r in rows
    }


# ──────────────────────────────────────────────
# 4. Cost Alerts
# ──────────────────────────────────────────────

# Umbrales de costo por defecto (USD)
DEFAULT_COST_THRESHOLDS = {
    "daily": 10.0,      # alertar si gasta mas de $10/dia
    "weekly": 50.0,     # alertar si gasta mas de $50/semana
    "monthly": 200.0,   # alertar si gasta mas de $200/mes
    "per_query": 0.50,  # alertar si una query cuesta mas de $0.50
}


def check_cost_alerts(conn: sqlite3.Connection,
                      thresholds: dict = None) -> list[dict]:
    """Verifica si los costos superan los umbrales configurados."""
    thresholds = thresholds or DEFAULT_COST_THRESHOLDS
    alerts = []

    now = datetime.now()

    # Costo diario
    today = now.strftime("%Y-%m-%d")
    try:
        daily_cost = conn.execute("""
            SELECT SUM(costo_usd) FROM traces
            WHERE date(timestamp) = ?
        """, (today,)).fetchone()[0] or 0
        if daily_cost > thresholds["daily"]:
            alerts.append({
                "type": "daily_cost_exceeded",
                "threshold": thresholds["daily"],
                "actual": round(daily_cost, 4),
                "message": f"Costo diario ${daily_cost:.2f} excede umbral ${thresholds['daily']:.2f}",
                "severity": "warning",
            })
    except Exception:
        pass

    # Costo semanal
    week_ago = (now - timedelta(days=7)).isoformat()
    try:
        weekly_cost = conn.execute("""
            SELECT SUM(costo_usd) FROM traces
            WHERE timestamp > ?
        """, (week_ago,)).fetchone()[0] or 0
        if weekly_cost > thresholds["weekly"]:
            alerts.append({
                "type": "weekly_cost_exceeded",
                "threshold": thresholds["weekly"],
                "actual": round(weekly_cost, 4),
                "message": f"Costo semanal ${weekly_cost:.2f} excede umbral ${thresholds['weekly']:.2f}",
                "severity": "warning",
            })
    except Exception:
        pass

    # Costo mensual
    month_ago = (now - timedelta(days=30)).isoformat()
    try:
        monthly_cost = conn.execute("""
            SELECT SUM(costo_usd) FROM traces
            WHERE timestamp > ?
        """, (month_ago,)).fetchone()[0] or 0
        if monthly_cost > thresholds["monthly"]:
            alerts.append({
                "type": "monthly_cost_exceeded",
                "threshold": thresholds["monthly"],
                "actual": round(monthly_cost, 4),
                "message": f"Costo mensual ${monthly_cost:.2f} excede umbral ${thresholds['monthly']:.2f}",
                "severity": "critical",
            })
    except Exception:
        pass

    # Query individual costosa
    try:
        expensive = conn.execute("""
            SELECT timestamp, costo_usd, modelo FROM traces
            WHERE costo_usd > ?
            ORDER BY costo_usd DESC LIMIT 5
        """, (thresholds["per_query"],)).fetchall()
        for ts, cost, model in expensive:
            alerts.append({
                "type": "expensive_query",
                "threshold": thresholds["per_query"],
                "actual": round(cost, 4),
                "model": model,
                "timestamp": ts,
                "message": f"Query costosa: ${cost:.4f} con {model}",
                "severity": "info",
            })
    except Exception:
        pass

    return alerts


def get_cost_summary(conn: sqlite3.Connection, days: int = 30) -> dict:
    """Resumen de costos por periodo."""
    since = (datetime.now() - timedelta(days=days)).isoformat()

    try:
        # Costo total (lee de finops_traces, la tabla que usa rag.obs)
        total = conn.execute("""
            SELECT SUM(costo_usd) FROM finops_traces WHERE fecha > ?
        """, (since,)).fetchone()[0] or 0

        # Costo por modelo
        by_model = conn.execute("""
            SELECT modelo, SUM(costo_usd), COUNT(*), AVG(costo_usd)
            FROM finops_traces WHERE fecha > ?
            GROUP BY modelo ORDER BY SUM(costo_usd) DESC
        """, (since,)).fetchall()

        # Costo por dia
        by_day = conn.execute("""
            SELECT date(fecha) as dia, SUM(costo_usd), COUNT(*)
            FROM finops_traces WHERE fecha > ?
            GROUP BY date(fecha) ORDER BY dia
        """, (since,)).fetchall()

        # Costo de hoy
        today = datetime.now().date().isoformat()
        today_cost = conn.execute("""
            SELECT SUM(costo_usd) FROM finops_traces WHERE date(fecha) = ?
        """, (today,)).fetchone()[0] or 0

        # Promedio diario
        n_days = len(by_day) if by_day else 1
        avg_daily = total / n_days if total else 0

        return {
            "total_cost": round(total, 4),
            "today_cost": round(today_cost, 4),
            "avg_daily": round(avg_daily, 4),
            "total_queries": sum(r[2] for r in by_model),
            "by_model": [
                {"model": r[0], "cost": round(r[1], 4),
                 "queries": r[2], "avg_cost": round(r[3], 6)}
                for r in by_model
            ],
            "by_day": [
                {"date": r[0], "cost": round(r[1], 4), "queries": r[2]}
                for r in by_day
            ],
        }
    except Exception as e:
        return {"total_cost": 0, "today_cost": 0, "avg_daily": 0, "error": str(e)}


# ──────────────────────────────────────────────
# 5. Quality Dashboards
# ──────────────────────────────────────────────

def get_quality_dashboard(conn: sqlite3.Connection) -> dict:
    """Obtiene datos para el dashboard de calidad."""
    dashboard = {}

    # 1. Metricas de evaluacion
    try:
        from evaluacion import get_quality_stats
        dashboard["evaluations"] = get_quality_stats(conn)
    except Exception:
        dashboard["evaluations"] = {"error": "modulo evaluacion no disponible"}

    # 2. Latency percentiles
    dashboard["latency"] = {
        "overall": get_latency_percentiles(conn),
        "by_operation": get_latency_by_operation(conn),
    }

    # 3. Costos
    dashboard["costs"] = get_cost_summary(conn, days=30)

    # 4. Errores
    try:
        errors = conn.execute("""
            SELECT error_type, COUNT(*), MAX(timestamp)
            FROM error_log
            WHERE timestamp > ?
            GROUP BY error_type ORDER BY COUNT(*) DESC LIMIT 10
        """, ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchall()
        dashboard["errors"] = [
            {"type": r[0], "count": r[1], "last_seen": r[2]}
            for r in errors
        ]
    except Exception:
        dashboard["errors"] = []

    # 5. Hallucinations
    try:
        hall_stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN grounded = 0 THEN 1 ELSE 0 END) as hallucinations,
                AVG(hallucination_score) as avg_score
            FROM hallucination_checks
            WHERE timestamp > ?
        """, ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchone()
        dashboard["hallucinations"] = {
            "total": hall_stats[0] or 0,
            "count": hall_stats[1] or 0,
            "avg_score": round(hall_stats[2], 3) if hall_stats[2] else 0,
        }
    except Exception:
        dashboard["hallucinations"] = {"total": 0, "count": 0}

    # 6. DLP
    try:
        dlp_stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN bloqueado = 1 THEN 1 ELSE 0 END) as blocked
            FROM dlp_checks
            WHERE timestamp > ?
        """, ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchone()
        dashboard["dlp"] = {
            "total_checks": dlp_stats[0] or 0,
            "blocked": dlp_stats[1] or 0,
        }
    except Exception:
        dashboard["dlp"] = {"total_checks": 0, "blocked": 0}

    # 7. Citations
    try:
        cit_stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN all_valid = 0 THEN 1 ELSE 0 END) as invalid
            FROM citation_verifications
            WHERE timestamp > ?
        """, ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchone()
        dashboard["citations"] = {
            "total": cit_stats[0] or 0,
            "invalid": cit_stats[1] or 0,
            "valid_rate": round((cit_stats[0] - cit_stats[1]) / max(cit_stats[0], 1) * 100, 1),
        }
    except Exception:
        dashboard["citations"] = {"total": 0, "invalid": 0}

    return dashboard


def init_observability_tables(conn: sqlite3.Connection):
    """Crea todas las tablas de observabilidad."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_spans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            name TEXT,
            duration_ms REAL,
            status TEXT,
            attributes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            error_type TEXT,
            error_message TEXT,
            traceback TEXT,
            context TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS latency_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            operation TEXT NOT NULL,
            duration_ms REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cost_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            alert_type TEXT,
            threshold REAL,
            actual REAL,
            severity TEXT,
            message TEXT
        )
    """)
    conn.commit()


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB_PATH))
    init_observability_tables(conn)

    # Test latency
    record_latency("test_op", 123.45, conn)
    record_latency("test_op", 456.78, conn)
    record_latency("test_op", 89.01, conn)

    percentiles = get_latency_percentiles(conn, "test_op")
    print("Latency percentiles:", json.dumps(percentiles, indent=2))

    # Test cost alerts
    alerts = check_cost_alerts(conn)
    print("\nCost alerts:", json.dumps(alerts, indent=2, ensure_ascii=False))

    # Test quality dashboard
    dashboard = get_quality_dashboard(conn)
    print("\nDashboard keys:", list(dashboard.keys()))

    conn.close()
