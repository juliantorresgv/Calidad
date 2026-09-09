"""
Memoria persistente, cache, knowledge store, sesiones y checkpoints
para el Agente de Calidad Integr@.

Implementa:
- Cache de respuestas (LRU con TTL) para evitar llamadas repetidas al LLM
- Knowledge Store: almacenamiento estructurado de hechos aprendidos
- Sesiones persistentes: historial de conversación por usuario
- Checkpoints: guardado de estado para reanudar tareas largas
- Estado de tareas: seguimiento de tareas multi-paso

Uso:
    from memoria import Memoria

    mem = Memoria()

    # Cache de respuestas
    cached = mem.cache_get("¿Qué es el procedimiento PEOP-MA01?")
    if cached:
        return cached
    respuesta = llm_chat(...)
    mem.cache_set("¿Qué es el procedimiento PEOP-MA01?", respuesta, ttl=3600)

    # Sesión persistente
    session = mem.create_session(user_id="user123")
    mem.add_message(session.id, "user", "¿Cuál es el procedimiento de caja menor?")
    mem.add_message(session.id, "assistant", "El procedimiento es PAFA-03-06...")
    historial = mem.get_session_history(session.id)

    # Knowledge store
    mem.store_fact("PAFA-03-06", "vence", "2026-05-24", source="alertas_vencimiento")
    hecho = mem.get_fact("PAFA-03-06", "vence")

    # Checkpoint de tarea larga
    cp = mem.save_checkpoint("generar_resumenes", {"procesados": 1088, "total": 2805})
    estado = mem.load_checkpoint("generar_resumenes")

    # Estado de tareas
    mem.start_task("user123", "auditoria_proceso", {"proceso": "GESTION DE CALIDAD"})
    mem.update_task("user123", "auditoria_proceso", "en_progreso", {"paso": 3})
    mem.complete_task("user123", "auditoria_proceso", {"resultado": "OK"})
"""
import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"


class Memoria:
    """Sistema de memoria persistente, cache, sesiones y checkpoints."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Crea todas las tablas de memoria si no existen."""
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript("""
            -- Cache de respuestas
            CREATE TABLE IF NOT EXISTS cache_respuestas (
                cache_key TEXT PRIMARY KEY,
                query_hash TEXT NOT NULL,
                respuesta TEXT NOT NULL,
                modelo TEXT,
                tokens_input INTEGER,
                tokens_output INTEGER,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                hit_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache_respuestas(query_hash);
            CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_respuestas(expires_at);

            -- Sesiones de conversación
            CREATE TABLE IF NOT EXISTS sesiones (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                status TEXT DEFAULT 'activa',
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sesiones_user ON sesiones(user_id);
            CREATE INDEX IF NOT EXISTS idx_sesiones_status ON sesiones(status);

            -- Mensajes de conversación
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                tokens INTEGER,
                model TEXT,
                tool_used TEXT,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES sesiones(id)
            );
            CREATE INDEX IF NOT EXISTS idx_mensajes_session ON mensajes(session_id);

            -- Knowledge store (hechos estructurados)
            CREATE TABLE IF NOT EXISTS knowledge_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity TEXT NOT NULL,
                attribute TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(entity, attribute)
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_entity ON knowledge_facts(entity);

            -- Checkpoints de tareas largas
            CREATE TABLE IF NOT EXISTS checkpoints (
                task_name TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            -- Estado de tareas multi-paso
            CREATE TABLE IF NOT EXISTS task_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                task_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                current_step INTEGER DEFAULT 0,
                total_steps INTEGER,
                params TEXT,
                result TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                UNIQUE(user_id, task_name)
            );
            CREATE INDEX IF NOT EXISTS idx_task_user ON task_state(user_id);
            CREATE INDEX IF NOT EXISTS idx_task_status ON task_state(status);
        """)
        conn.commit()
        conn.close()

    # ──────────────────────────────────────────────
    # CACHE DE RESPUESTAS
    # ──────────────────────────────────────────────

    @staticmethod
    def _hash_query(query: str) -> str:
        """Hash normalizado de la consulta para comparación."""
        normalized = " ".join(query.lower().strip().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def cache_get(self, query: str) -> Optional[dict]:
        """Busca una respuesta en cache. Retorna dict o None."""
        qhash = self._hash_query(query)
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute("""
            SELECT respuesta, modelo, tokens_input, tokens_output, created_at
            FROM cache_respuestas
            WHERE query_hash = ? AND (expires_at IS NULL OR expires_at > ?)
        """, (qhash, datetime.now().isoformat())).fetchone()

        if row:
            # Incrementar hit count
            conn.execute(
                "UPDATE cache_respuestas SET hit_count = hit_count + 1 WHERE query_hash = ?",
                (qhash,)
            )
            conn.commit()
            conn.close()
            return {
                "respuesta": row[0],
                "modelo": row[1],
                "tokens_input": row[2],
                "tokens_output": row[3],
                "cached_at": row[4],
                "from_cache": True,
            }
        conn.close()
        return None

    def cache_set(
        self,
        query: str,
        respuesta: str,
        modelo: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        ttl: int = 3600,
        cache_type: str = "general",
    ):
        """Guarda una respuesta en cache con TTL en segundos.

        Args:
            cache_type: Tipo de cache para invalidacion selectiva.
                - "general": consultas generales (TTL 1h)
                - "procedimiento": info de procedimientos (TTL 24h)
                - "alertas": alertas de vencimiento (TTL 1h)
                - "estatico": datos que no cambian (TTL 7 dias)
        """
        qhash = self._hash_query(query)
        cache_key = f"cache_{qhash}_{int(time.time())}"

        # TTL por tipo
        ttl_by_type = {
            "general": 3600,        # 1 hora
            "procedimiento": 86400,  # 24 horas
            "alertas": 3600,         # 1 hora
            "estatico": 604800,      # 7 dias
        }
        actual_ttl = ttl_by_type.get(cache_type, ttl)
        expires = (datetime.now() + timedelta(seconds=actual_ttl)).isoformat() if actual_ttl > 0 else None

        conn = sqlite3.connect(str(self.db_path))
        # Upsert: si existe para este hash, reemplazar
        conn.execute("""
            INSERT OR REPLACE INTO cache_respuestas
                (cache_key, query_hash, respuesta, modelo, tokens_input, tokens_output,
                 created_at, expires_at, hit_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            cache_key, qhash, respuesta, modelo, tokens_input, tokens_output,
            datetime.now().isoformat(), expires
        ))
        conn.commit()
        conn.close()

    def cache_invalidate_type(self, cache_type: str):
        """Invalida todas las entradas de cache de un tipo especifico."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM cache_respuestas WHERE expires_at < ?", (datetime.now().isoformat(),))
        conn.commit()
        conn.close()

    def cache_invalidate_query(self, query: str):
        """Invalida una consulta especifica del cache."""
        qhash = self._hash_query(query)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM cache_respuestas WHERE query_hash = ?", (qhash,))
        conn.commit()
        conn.close()

    def cache_semantic_lookup(self, query: str, threshold: float = 0.85) -> Optional[dict]:
        """Busca respuestas similares en cache usando similitud de keywords.

        Si no hay match exacto, busca consultas cacheadas que compartan
        suficientes keywords con la consulta actual.
        """
        # Primero intentar match exacto
        exact = self.cache_get(query)
        if exact:
            exact["match_type"] = "exact"
            return exact

        # Match semantico por keywords
        import re as _re
        query_keywords = set(_re.findall(r"[a-záéíóúñ]{4,}", query.lower()))
        if not query_keywords:
            return None

        conn = sqlite3.connect(str(self.db_path))
        # Obtener consultas cacheadas recientes (no expiradas)
        rows = conn.execute("""
            SELECT respuesta, modelo, tokens_input, tokens_output, created_at, query_hash
            FROM cache_respuestas
            WHERE expires_at IS NULL OR expires_at > ?
            ORDER BY created_at DESC LIMIT 100
        """, (datetime.now().isoformat(),)).fetchall()
        conn.close()

        best_match = None
        best_score = 0

        for row in rows:
            # No podemos recuperar la query original del hash, pero podemos
            # comparar keywords de la respuesta cacheada
            cached_text = row[0].lower()
            cached_keywords = set(_re.findall(r"[a-záéíóúñ]{4,}", cached_text))
            if not cached_keywords:
                continue

            overlap = len(query_keywords & cached_keywords) / len(query_keywords)
            if overlap > best_score:
                best_score = overlap
                best_match = row

        if best_match and best_score >= threshold:
            return {
                "respuesta": best_match[0],
                "modelo": best_match[1],
                "tokens_input": best_match[2],
                "tokens_output": best_match[3],
                "cached_at": best_match[4],
                "from_cache": True,
                "match_type": "semantic",
                "similarity": round(best_score, 2),
            }

        return None

    def cache_cleanup(self):
        """Elimina entradas de cache expiradas."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM cache_respuestas WHERE expires_at < ?", (datetime.now().isoformat(),))
        conn.commit()
        conn.close()

    def cache_stats(self) -> dict:
        """Estadísticas del cache."""
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute("""
            SELECT COUNT(*), SUM(hit_count), AVG(hit_count)
            FROM cache_respuestas
            WHERE expires_at IS NULL OR expires_at > ?
        """, (datetime.now().isoformat(),)).fetchone()
        conn.close()
        return {
            "entradas_activas": row[0] or 0,
            "total_hits": row[1] or 0,
            "hit_promedio": round(row[2] or 0, 1),
        }

    # ──────────────────────────────────────────────
    # SESIONES PERSISTENTES
    # ──────────────────────────────────────────────

    def create_session(self, user_id: str, metadata: dict | None = None) -> dict:
        """Crea una nueva sesión de conversación."""
        import uuid
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO sesiones (id, user_id, created_at, last_activity, status, metadata)
            VALUES (?, ?, ?, ?, 'activa', ?)
        """, (session_id, user_id, now, now, json.dumps(metadata) if metadata else None))
        conn.commit()
        conn.close()

        return {"id": session_id, "user_id": user_id, "created_at": now, "status": "activa"}

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens: int = 0,
        model: str = "",
        tool_used: str = "",
        metadata: dict | None = None,
    ):
        """Añade un mensaje a una sesión."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO mensajes (session_id, role, content, timestamp, tokens, model, tool_used, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, role, content, now, tokens, model, tool_used,
              json.dumps(metadata) if metadata else None))
        conn.execute("UPDATE sesiones SET last_activity = ? WHERE id = ?", (now, session_id))
        conn.commit()
        conn.close()

    def get_session_history(self, session_id: str, limit: int = 20) -> list[dict]:
        """Obtiene el historial de mensajes de una sesión."""
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("""
            SELECT role, content, timestamp, tokens, model, tool_used
            FROM mensajes
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (session_id, limit)).fetchall()
        conn.close()
        return [
            {
                "role": r[0],
                "content": r[1],
                "timestamp": r[2],
                "tokens": r[3],
                "model": r[4],
                "tool_used": r[5],
            }
            for r in reversed(rows)
        ]

    def get_active_sessions(self, user_id: str | None = None) -> list[dict]:
        """Obtiene sesiones activas, opcionalmente filtradas por usuario."""
        conn = sqlite3.connect(str(self.db_path))
        if user_id:
            rows = conn.execute("""
                SELECT id, user_id, created_at, last_activity, status
                FROM sesiones WHERE user_id = ? AND status = 'activa'
                ORDER BY last_activity DESC
            """, (user_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, user_id, created_at, last_activity, status
                FROM sesiones WHERE status = 'activa'
                ORDER BY last_activity DESC
            """).fetchall()
        conn.close()
        return [
            {"id": r[0], "user_id": r[1], "created_at": r[2],
             "last_activity": r[3], "status": r[4]}
            for r in rows
        ]

    def close_session(self, session_id: str):
        """Cierra una sesión."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("UPDATE sesiones SET status = 'cerrada' WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()

    def get_context_for_llm(self, session_id: str, max_messages: int = 10) -> list[dict]:
        """Obtiene el historial formateado para enviar al LLM."""
        history = self.get_session_history(session_id, limit=max_messages)
        return [{"role": m["role"], "content": m["content"]} for m in history]

    # ──────────────────────────────────────────────
    # KNOWLEDGE STORE
    # ──────────────────────────────────────────────

    def store_fact(
        self,
        entity: str,
        attribute: str,
        value: str,
        source: str = "",
        confidence: float = 1.0,
    ):
        """Almacena o actualiza un hecho en el knowledge store."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO knowledge_facts (entity, attribute, value, source, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity, attribute) DO UPDATE SET
                value = excluded.value,
                source = excluded.source,
                confidence = excluded.confidence,
                updated_at = excluded.updated_at
        """, (entity, attribute, value, source, confidence, now, now))
        conn.commit()
        conn.close()

    def get_fact(self, entity: str, attribute: str) -> Optional[dict]:
        """Obtiene un hecho del knowledge store."""
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute("""
            SELECT value, source, confidence, updated_at
            FROM knowledge_facts WHERE entity = ? AND attribute = ?
        """, (entity, attribute)).fetchone()
        conn.close()
        if row:
            return {"value": row[0], "source": row[1], "confidence": row[2], "updated_at": row[3]}
        return None

    def get_entity_facts(self, entity: str) -> list[dict]:
        """Obtiene todos los hechos de una entidad."""
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("""
            SELECT attribute, value, source, confidence, updated_at
            FROM knowledge_facts WHERE entity = ?
            ORDER BY attribute
        """, (entity,)).fetchall()
        conn.close()
        return [
            {"attribute": r[0], "value": r[1], "source": r[2],
             "confidence": r[3], "updated_at": r[4]}
            for r in rows
        ]

    def search_facts(self, query: str, limit: int = 10) -> list[dict]:
        """Busca hechos que contengan el texto de la consulta."""
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("""
            SELECT entity, attribute, value, source, confidence
            FROM knowledge_facts
            WHERE entity LIKE ? OR value LIKE ? OR attribute LIKE ?
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()
        conn.close()
        return [
            {"entity": r[0], "attribute": r[1], "value": r[2],
             "source": r[3], "confidence": r[4]}
            for r in rows
        ]

    # ──────────────────────────────────────────────
    # CHECKPOINTS
    # ──────────────────────────────────────────────

    def save_checkpoint(self, task_name: str, state: dict):
        """Guarda el estado de una tarea larga para reanudarla después."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO checkpoints (task_name, state, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(task_name) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at
        """, (task_name, json.dumps(state), now, now))
        conn.commit()
        conn.close()

    def load_checkpoint(self, task_name: str) -> Optional[dict]:
        """Carga el estado guardado de una tarea."""
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT state, updated_at FROM checkpoints WHERE task_name = ?",
            (task_name,)
        ).fetchone()
        conn.close()
        if row:
            return {"state": json.loads(row[0]), "updated_at": row[1]}
        return None

    def delete_checkpoint(self, task_name: str):
        """Elimina un checkpoint."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM checkpoints WHERE task_name = ?", (task_name,))
        conn.commit()
        conn.close()

    # ──────────────────────────────────────────────
    # ESTADO DE TAREAS MULTI-PASO
    # ──────────────────────────────────────────────

    def start_task(self, user_id: str, task_name: str, params: dict | None = None, total_steps: int = 0):
        """Inicia una tarea multi-paso."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO task_state (user_id, task_name, status, current_step, total_steps, params, created_at, updated_at)
            VALUES (?, ?, 'en_progreso', 0, ?, ?, ?, ?)
            ON CONFLICT(user_id, task_name) DO UPDATE SET
                status = 'en_progreso', current_step = 0,
                params = excluded.params, updated_at = excluded.updated_at, completed_at = NULL
        """, (user_id, task_name, total_steps, json.dumps(params) if params else None, now, now))
        conn.commit()
        conn.close()

    def update_task(
        self,
        user_id: str,
        task_name: str,
        status: str = "en_progreso",
        current_step: int | None = None,
        result: dict | None = None,
    ):
        """Actualiza el estado de una tarea."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(str(self.db_path))
        if current_step is not None:
            conn.execute("""
                UPDATE task_state SET status = ?, current_step = ?, updated_at = ?
                WHERE user_id = ? AND task_name = ?
            """, (status, current_step, now, user_id, task_name))
        else:
            conn.execute("""
                UPDATE task_state SET status = ?, updated_at = ?
                WHERE user_id = ? AND task_name = ?
            """, (status, now, user_id, task_name))
        if result:
            conn.execute("""
                UPDATE task_state SET result = ? WHERE user_id = ? AND task_name = ?
            """, (json.dumps(result), user_id, task_name))
        conn.commit()
        conn.close()

    def complete_task(self, user_id: str, task_name: str, result: dict | None = None):
        """Marca una tarea como completada."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            UPDATE task_state SET status = 'completada', updated_at = ?, completed_at = ?
            WHERE user_id = ? AND task_name = ?
        """, (now, now, user_id, task_name))
        if result:
            conn.execute("""
                UPDATE task_state SET result = ? WHERE user_id = ? AND task_name = ?
            """, (json.dumps(result), user_id, task_name))
        conn.commit()
        conn.close()

    def get_task(self, user_id: str, task_name: str) -> Optional[dict]:
        """Obtiene el estado de una tarea."""
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute("""
            SELECT status, current_step, total_steps, params, result, created_at, updated_at, completed_at
            FROM task_state WHERE user_id = ? AND task_name = ?
        """, (user_id, task_name)).fetchone()
        conn.close()
        if row:
            return {
                "status": row[0],
                "current_step": row[1],
                "total_steps": row[2],
                "params": json.loads(row[3]) if row[3] else None,
                "result": json.loads(row[4]) if row[4] else None,
                "created_at": row[5],
                "updated_at": row[6],
                "completed_at": row[7],
            }
        return None

    def get_active_tasks(self, user_id: str) -> list[dict]:
        """Obtiene tareas en progreso de un usuario."""
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("""
            SELECT task_name, status, current_step, total_steps, updated_at
            FROM task_state WHERE user_id = ? AND status = 'en_progreso'
            ORDER BY updated_at DESC
        """, (user_id,)).fetchall()
        conn.close()
        return [
            {"task_name": r[0], "status": r[1], "current_step": r[2],
             "total_steps": r[3], "updated_at": r[4]}
            for r in rows
        ]

    # ──────────────────────────────────────────────
    # RESUMEN DE MEMORIA
    # ──────────────────────────────────────────────

    def get_memory_summary(self, session_id: str | None = None) -> dict:
        """Retorna un resumen del estado de memoria para el contexto del LLM."""
        summary = {
            "cache": self.cache_stats(),
        }

        conn = sqlite3.connect(str(self.db_path))

        # Sesiones activas
        row = conn.execute("SELECT COUNT(*) FROM sesiones WHERE status = 'activa'").fetchone()
        summary["sesiones_activas"] = row[0]

        # Hechos en knowledge store
        row = conn.execute("SELECT COUNT(*) FROM knowledge_facts").fetchone()
        summary["hechos_conocidos"] = row[0]

        # Checkpoints
        row = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()
        summary["checkpoints"] = row[0]

        # Tareas en progreso
        row = conn.execute("SELECT COUNT(*) FROM task_state WHERE status = 'en_progreso'").fetchone()
        summary["tareas_en_progreso"] = row[0]

        if session_id:
            # Historial de la sesión
            row = conn.execute("SELECT COUNT(*) FROM mensajes WHERE session_id = ?", (session_id,)).fetchone()
            summary["mensajes_sesion_actual"] = row[0]

        conn.close()
        return summary
