"""
Observabilidad y FinOps del Agente de Calidad.
Integra LangFuse para trazas + tracking de tokens, costos y latencia.

LangFuse puede funcionar:
1. Self-hosted (Docker) - recomendado para datos internos
2. LangFuse Cloud - si prefieres no mantener infraestructura

Configuración:
    $env:LANGFUSE_SECRET_KEY="<tu_secret_key>"
    $env:LANGFUSE_PUBLIC_KEY="<tu_public_key>"
    $env:LANGFUSE_HOST="http://localhost:3000"  # self-hosted

Si no hay keys de LangFuse, funciona en modo fallback con SQLite local.

Uso en graph_rag.py:
    from observabilidad import Observabilidad
    obs = Observabilidad()
    trace = obs.start_trace("pregunta_usuario")
    obs.track_llm_call(model, prompt_tokens, completion_tokens, latency)
    obs.track_retrieval(query, n_docs, latency)
    obs.end_trace(answer)
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"

# ──────────────────────────────────────────────
# Precios de Mistral (USD por 1M tokens) - actualizar si cambian
# ──────────────────────────────────────────────

MISTRAL_PRICING = {
    "mistral-small-latest": {"input": 0.10, "output": 0.10},
    "mistral-medium-latest": {"input": 0.40, "output": 0.40},
    "mistral-large-latest": {"input": 2.00, "output": 6.00},
    "mistral-embed": {"input": 0.10, "output": 0.0},
    "open-mistral-7b": {"input": 0.10, "output": 0.10},
    "open-mixtral-8x7b": {"input": 0.20, "output": 0.20},
    "open-mixtral-8x22b": {"input": 0.20, "output": 0.20},
}


def get_pricing(model: str) -> dict:
    """Obtiene el precio de un modelo."""
    if model in MISTRAL_PRICING:
        return MISTRAL_PRICING[model]
    # Fallback: precio de small
    return {"input": 0.10, "output": 0.10}


def calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calcula el costo en USD de una llamada."""
    pricing = get_pricing(model)
    cost = (prompt_tokens / 1_000_000 * pricing["input"]) + \
           (completion_tokens / 1_000_000 * pricing["output"])
    return round(cost, 6)


# ──────────────────────────────────────────────
# Observabilidad
# ──────────────────────────────────────────────

class Observabilidad:
    """Integra LangFuse + tracking FinOps en SQLite."""

    def __init__(self):
        self.langfuse = None
        self.enabled = False
        self.current_trace = None
        self.trace_data = {}

        # Intentar inicializar LangFuse
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        host = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")

        if secret_key and public_key:
            try:
                from langfuse import Langfuse
                self.langfuse = Langfuse(
                    secret_key=secret_key,
                    public_key=public_key,
                    host=host,
                )
                self.enabled = True
                print("  [Observabilidad] LangFuse activado")
            except Exception as e:
                print(f"  [Observabilidad] LangFuse no disponible: {e}")
                print(f"  [Observabilidad] Usando tracking local (SQLite)")
        else:
            print(f"  [Observabilidad] Sin LANGFUSE keys, usando tracking local (SQLite)")

        # Crear tablas de FinOps en SQLite
        self._init_db()

    def _init_db(self):
        """Crea tablas de FinOps en SQLite."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS finops_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT,
                session_id TEXT,
                timestamp TEXT,
                pregunta TEXT,
                respuesta TEXT,
                modelo TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                costo_usd REAL,
                latencia_total REAL,
                latencia_recuperacion REAL,
                latencia_reranking REAL,
                latencia_llm REAL,
                documentos_recuperados INTEGER,
                skills_activados TEXT,
                obsoletos_filtrados INTEGER,
                metadata TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS finops_llm_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT,
                timestamp TEXT,
                modelo TEXT,
                tipo_llamada TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                costo_usd REAL,
                latencia REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS finops_daily_summary (
                fecha TEXT PRIMARY KEY,
                total_traces INTEGER,
                total_tokens INTEGER,
                total_costo_usd REAL,
                avg_latencia REAL,
                total_preguntas INTEGER
            )
        """)
        conn.commit()
        conn.close()

    # ─── Traces ───

    def start_trace(self, pregunta: str, session_id: str = None) -> str:
        """Inicia una traza para una pregunta del usuario."""
        trace_id = f"trace_{int(time.time() * 1000)}"
        self.trace_data = {
            "trace_id": trace_id,
            "session_id": session_id or "default",
            "timestamp": datetime.now().isoformat(),
            "pregunta": pregunta,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "costo_usd": 0.0,
            "latencia_total_start": time.time(),
            "latencia_recuperacion": 0,
            "latencia_reranking": 0,
            "latencia_llm": 0,
            "documentos_recuperados": 0,
            "skills_activados": [],
            "obsoletos_filtrados": 0,
        }

        # LangFuse trace
        if self.enabled and self.langfuse:
            try:
                self.current_trace = self.langfuse.trace(
                    id=trace_id,
                    name="agente_calidad",
                    input=pregunta,
                    session_id=session_id,
                )
            except Exception:
                self.current_trace = None

        return trace_id

    def track_retrieval(self, trace_id: str, query: str, n_docs: int,
                        n_obsoletos: int, latency: float):
        """Registra la fase de recuperación."""
        if trace_id == self.trace_data.get("trace_id"):
            self.trace_data["latencia_recuperacion"] = latency
            self.trace_data["documentos_recuperados"] = n_docs
            self.trace_data["obsoletos_filtrados"] = n_obsoletos

        if self.enabled and self.current_trace:
            try:
                self.current_trace.span(
                    name="retrieval",
                    input=query,
                    output=f"{n_docs} documentos",
                    metadata={"obsoletos_filtrados": n_obsoletos},
                )
            except Exception:
                pass

    def track_reranking(self, trace_id: str, n_candidates: int, latency: float):
        """Registra la fase de reranking."""
        if trace_id == self.trace_data.get("trace_id"):
            self.trace_data["latencia_reranking"] = latency

    def track_skills(self, trace_id: str, skills: list[str]):
        """Registra los skills activados."""
        if trace_id == self.trace_data.get("trace_id"):
            self.trace_data["skills_activados"] = skills

    def track_llm_call(self, trace_id: str, model: str, call_type: str,
                       prompt_tokens: int, completion_tokens: int, latency: float):
        """Registra una llamada al LLM con tokens y costo."""
        total_tokens = prompt_tokens + completion_tokens
        costo = calc_cost(model, prompt_tokens, completion_tokens)

        # Acumular en trace
        if trace_id == self.trace_data.get("trace_id"):
            self.trace_data["prompt_tokens"] += prompt_tokens
            self.trace_data["completion_tokens"] += completion_tokens
            self.trace_data["total_tokens"] += total_tokens
            self.trace_data["costo_usd"] += costo
            self.trace_data["latencia_llm"] += latency

        # Guardar en SQLite
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            INSERT INTO finops_llm_calls
            (trace_id, timestamp, modelo, tipo_llamada,
             prompt_tokens, completion_tokens, total_tokens, costo_usd, latencia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trace_id, datetime.now().isoformat(), model, call_type,
            prompt_tokens, completion_tokens, total_tokens, costo, latency
        ))
        conn.commit()
        conn.close()

        # LangFuse
        if self.enabled and self.current_trace:
            try:
                self.current_trace.generation(
                    name=call_type,
                    model=model,
                    usage={
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                    metadata={"cost_usd": costo, "latency_s": latency},
                )
            except Exception:
                pass

    def end_trace(self, trace_id: str, respuesta: str):
        """Finaliza la traza y guarda en SQLite."""
        if trace_id != self.trace_data.get("trace_id"):
            return

        latency_total = time.time() - self.trace_data["latencia_total_start"]

        # Guardar en SQLite
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            INSERT INTO finops_traces
            (trace_id, session_id, timestamp, pregunta, respuesta,
             modelo, prompt_tokens, completion_tokens, total_tokens,
             costo_usd, latencia_total, latencia_recuperacion,
             latencia_reranking, latencia_llm, documentos_recuperados,
             skills_activados, obsoletos_filtrados, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trace_id,
            self.trace_data["session_id"],
            self.trace_data["timestamp"],
            self.trace_data["pregunta"],
            respuesta[:500],
            os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
            self.trace_data["prompt_tokens"],
            self.trace_data["completion_tokens"],
            self.trace_data["total_tokens"],
            self.trace_data["costo_usd"],
            latency_total,
            self.trace_data["latencia_recuperacion"],
            self.trace_data["latencia_reranking"],
            self.trace_data["latencia_llm"],
            self.trace_data["documentos_recuperados"],
            json.dumps(self.trace_data["skills_activados"], ensure_ascii=False),
            self.trace_data["obsoletos_filtrados"],
            json.dumps({}, ensure_ascii=False),
        ))
        conn.commit()
        conn.close()

        # Actualizar resumen diario
        self._update_daily_summary()

        # LangFuse
        if self.enabled and self.current_trace:
            try:
                self.current_trace.update(output=respuesta[:500])
            except Exception:
                pass

        # Imprimir resumen
        print(f"  [FinOps] tokens={self.trace_data['total_tokens']} "
              f"costo=${self.trace_data['costo_usd']:.4f} "
              f"latencia={latency_total:.2f}s")

    def _update_daily_summary(self):
        """Actualiza el resumen diario de FinOps."""
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(str(DB_PATH))

        # Calcular totales del día
        row = conn.execute("""
            SELECT COUNT(*), SUM(total_tokens), SUM(costo_usd), AVG(latencia_total)
            FROM finops_traces
            WHERE date(timestamp) = ?
        """, (today,)).fetchone()

        total_traces = row[0] or 0
        total_tokens = row[1] or 0
        total_costo = row[2] or 0.0
        avg_latencia = row[3] or 0.0

        conn.execute("""
            INSERT OR REPLACE INTO finops_daily_summary
            (fecha, total_traces, total_tokens, total_costo_usd, avg_latencia, total_preguntas)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (today, total_traces, total_tokens, total_costo, avg_latencia, total_traces))
        conn.commit()
        conn.close()

    # ─── Dashboard FinOps ───

    def dashboard(self) -> dict:
        """Genera un dashboard de FinOps."""
        conn = sqlite3.connect(str(DB_PATH))

        # Totales globales
        total = conn.execute("""
            SELECT COUNT(*), SUM(total_tokens), SUM(costo_usd), AVG(latencia_total)
            FROM finops_traces
        """).fetchone()

        # Por día (últimos 7)
        daily = conn.execute("""
            SELECT fecha, total_traces, total_tokens, total_costo_usd, avg_latencia
            FROM finops_daily_summary
            ORDER BY fecha DESC
            LIMIT 7
        """).fetchall()

        # Por modelo
        por_modelo = conn.execute("""
            SELECT modelo, COUNT(*), SUM(total_tokens), SUM(costo_usd)
            FROM finops_llm_calls
            GROUP BY modelo
            ORDER BY SUM(costo_usd) DESC
        """).fetchall()

        # Por tipo de llamada
        por_tipo = conn.execute("""
            SELECT tipo_llamada, COUNT(*), SUM(total_tokens), SUM(costo_usd), AVG(latencia)
            FROM finops_llm_calls
            GROUP BY tipo_llamada
            ORDER BY SUM(costo_usd) DESC
        """).fetchall()

        conn.close()

        return {
            "total_traces": total[0] or 0,
            "total_tokens": total[1] or 0,
            "total_costo_usd": round(total[2] or 0.0, 4),
            "avg_latencia": round(total[3] or 0.0, 2),
            "daily": [
                {"fecha": d[0], "traces": d[1], "tokens": d[2],
                 "costo": round(d[3] or 0, 4), "avg_latencia": round(d[4] or 0, 2)}
                for d in daily
            ],
            "por_modelo": [
                {"modelo": m[0], "llamadas": m[1], "tokens": m[2], "costo": round(m[3] or 0, 4)}
                for m in por_modelo
            ],
            "por_tipo": [
                {"tipo": t[0], "llamadas": t[1], "tokens": t[2],
                 "costo": round(t[3] or 0, 4), "avg_latencia": round(t[4] or 0, 2)}
                for t in por_tipo
            ],
        }

    def print_dashboard(self):
        """Imprime el dashboard de FinOps en consola."""
        d = self.dashboard()
        print(f"\n{'='*60}")
        print(f"  DASHBOARD FINOPS")
        print(f"{'='*60}")
        print(f"  Total traces:     {d['total_traces']}")
        print(f"  Total tokens:     {d['total_tokens']:,}")
        print(f"  Total costo USD:  ${d['total_costo_usd']:.4f}")
        print(f"  Latencia prom:    {d['avg_latencia']:.2f}s")

        if d["daily"]:
            print(f"\n  📊 Últimos 7 días:")
            for day in d["daily"]:
                print(f"    {day['fecha']}: {day['traces']} traces, "
                      f"{day['tokens']:,} tokens, ${day['costo']:.4f}, "
                      f"{day['avg_latencia']:.2f}s")

        if d["por_modelo"]:
            print(f"\n  📊 Por modelo:")
            for m in d["por_modelo"]:
                print(f"    {m['modelo']}: {m['llamadas']} llamadas, "
                      f"{m['tokens']:,} tokens, ${m['costo']:.4f}")

        if d["por_tipo"]:
            print(f"\n  📊 Por tipo de llamada:")
            for t in d["por_tipo"]:
                print(f"    {t['tipo']}: {t['llamadas']} llamadas, "
                      f"{t['tokens']:,} tokens, ${t['costo']:.4f}, "
                      f"{t['avg_latencia']:.2f}s")


if __name__ == "__main__":
    obs = Observabilidad()
    obs.print_dashboard()
