"""
Context Management para el Agente de Calidad Integr@.

Gestiona el contexto de conversacion del LLM con:
- Ventana deslizante (sliding window) con prioridad de mensajes
- Resumen automatico de historial largo (compresion)
- Presupuesto de tokens por componente (system, history, query, response)
- Seleccion inteligente de mensajes relevantes
- Deteccion de cambio de tema para resetear contexto
- Compresion de tools results extensos
"""
import json
import re
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

TOKEN_BUDGET = {
    "system": 1500,
    "tools": 2000,
    "history": 4000,
    "summary": 800,
    "user_query": 2000,
    "response": 2000,
    "total": 12000,
}

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    if not text:
        return ""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


class ContextManager:
    """Gestiona el contexto de conversacion del LLM de forma inteligente."""

    def __init__(self, memoria=None, llm_client=None, model: str = "mistral-small-latest", db_path: Path = DB_PATH):
        self.memoria = memoria
        self.llm_client = llm_client
        self.model = model
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS context_summaries (
                session_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                messages_summarized INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topic_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                message_index INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_topic_session ON topic_history(session_id);
        """)
        conn.commit()
        conn.close()

    def build_context(self, session_id: str, system_prompt: str, new_user_message: str, tools: list[dict] | None = None, max_history_messages: int = 20) -> list[dict]:
        """Construye la lista de mensajes optimizada para el LLM."""
        messages: list[dict] = []

        # 1. System prompt
        if estimate_tokens(system_prompt) > TOKEN_BUDGET["system"]:
            system_prompt = truncate_to_tokens(system_prompt, TOKEN_BUDGET["system"])
        messages.append({"role": "system", "content": system_prompt})

        # 2. Resumen de historial anterior
        summary = self._get_or_create_summary(session_id)
        if summary:
            messages.append({"role": "system", "content": f"Resumen de la conversacion anterior:\n{summary}"})

        # 3. Historial reciente
        if self.memoria:
            history = self.memoria.get_session_history(session_id, limit=max_history_messages)
            history = self._select_relevant_history(history, new_user_message)
            history = self._compress_tool_results(history)
            history = self._fit_to_budget(history, TOKEN_BUDGET["history"])
            messages.extend(history)

        # 4. Mensaje del usuario actual
        if estimate_tokens(new_user_message) > TOKEN_BUDGET["user_query"]:
            new_user_message = truncate_to_tokens(new_user_message, TOKEN_BUDGET["user_query"])
        messages.append({"role": "user", "content": new_user_message})

        return messages

    def _select_relevant_history(self, history: list[dict], current_query: str, min_messages: int = 4) -> list[dict]:
        """Selecciona mensajes relevantes del historial basado en la consulta actual."""
        if len(history) <= min_messages:
            return history

        query_keywords = set(re.findall(r"[a-záéíóúñ]{4,}", current_query.lower()))
        scored = []
        for i, msg in enumerate(history):
            score = 0
            content = msg.get("content", "").lower()
            recency_score = i / len(history)
            score += recency_score * 0.3
            msg_keywords = set(re.findall(r"[a-záéíóúñ]{4,}", content))
            overlap = len(query_keywords & msg_keywords)
            score += overlap * 0.4
            if msg.get("tool_used"):
                score += 0.3
            scored.append((score, i, msg))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected_indices = set()
        for score, i, msg in scored:
            if len(selected_indices) >= max(min_messages * 2, len(history) // 2):
                break
            selected_indices.add(i)

        for i in range(max(0, len(history) - min_messages), len(history)):
            selected_indices.add(i)

        return [history[i] for i in sorted(selected_indices)]

    def _compress_tool_results(self, history: list[dict]) -> list[dict]:
        """Comprime resultados de tools muy largos en el historial."""
        compressed = []
        for msg in history:
            content = msg.get("content", "")
            if len(content) > 500 and msg.get("tool_used"):
                compressed_content = content[:200] + "\n[...resultado comprimido...]\n" + content[-200:]
                msg = {**msg, "content": compressed_content}
            compressed.append(msg)
        return compressed

    def _fit_to_budget(self, history: list[dict], max_tokens: int) -> list[dict]:
        """Recorta el historial para que quepa en el presupuesto de tokens."""
        total_tokens = sum(estimate_tokens(m.get("content", "")) for m in history)
        if total_tokens <= max_tokens:
            return history

        while len(history) > 4 and total_tokens > max_tokens:
            removed = history.pop(0)
            total_tokens -= estimate_tokens(removed.get("content", ""))

        if total_tokens > max_tokens:
            for i, msg in enumerate(history):
                msg_tokens = estimate_tokens(msg.get("content", ""))
                if msg_tokens > max_tokens // len(history):
                    history[i] = {**msg, "content": truncate_to_tokens(msg.get("content", ""), max_tokens // len(history))}

        return history

    def _get_or_create_summary(self, session_id: str) -> Optional[str]:
        """Obtiene el resumen existente o crea uno nuevo."""
        if not self.memoria:
            return None

        existing = self._load_summary(session_id)
        if existing:
            return existing["summary"]

        history = self.memoria.get_session_history(session_id, limit=50)
        if len(history) < 10:
            return None

        summary = self._summarize_history(session_id, history[:len(history) - 6])
        if summary:
            self._save_summary(session_id, summary, len(history) - 6)
            return summary

        return None

    def _summarize_history(self, session_id: str, history: list[dict]) -> Optional[str]:
        """Genera un resumen del historial usando el LLM."""
        if not self.llm_client or not history:
            return None

        formatted = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:300]
            formatted.append(f"{role}: {content}")

        history_text = "\n".join(formatted)
        prompt = f"""Resume la siguiente conversacion en maximo 5 puntos clave.
Mantén: codigos de procedimientos, decisiones, datos importantes.
Omite: saludos, redundancias, detalles tecnicos innecesarios.

Conversacion:
{history_text}

Resumen (5 puntos maximo):"""

        try:
            resp = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Eres un asistente que resume conversaciones de calidad HSEQ en español."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return None

    def _load_summary(self, session_id: str) -> Optional[dict]:
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute("SELECT summary, messages_summarized, updated_at FROM context_summaries WHERE session_id = ?", (session_id,)).fetchone()
        conn.close()
        if row:
            return {"summary": row[0], "messages_summarized": row[1], "updated_at": row[2]}
        return None

    def _save_summary(self, session_id: str, summary: str, messages_count: int):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO context_summaries (session_id, summary, messages_summarized, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                summary = excluded.summary,
                messages_summarized = excluded.messages_summarized,
                updated_at = excluded.updated_at
        """, (session_id, summary, messages_count, now, now))
        conn.commit()
        conn.close()

    def detect_topic_change(self, session_id: str, current_message: str, threshold: float = 0.3) -> bool:
        """Detecta si el usuario cambio de tema en la conversacion."""
        if not self.memoria:
            return False

        history = self.memoria.get_session_history(session_id, limit=2)
        if len(history) < 1:
            return False

        last_msg = history[-1].get("content", "")
        current_keywords = set(re.findall(r"[a-záéíóúñ]{4,}", current_message.lower()))
        last_keywords = set(re.findall(r"[a-záéíóúñ]{4,}", last_msg.lower()))

        if not current_keywords or not last_keywords:
            return True

        overlap = len(current_keywords & last_keywords) / len(current_keywords | last_keywords)
        return overlap < threshold

    def record_topic(self, session_id: str, topic: str, message_index: int = 0):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("INSERT INTO topic_history (session_id, topic, detected_at, message_index) VALUES (?, ?, ?, ?)", (session_id, topic, now, message_index))
        conn.commit()
        conn.close()

    def get_topics(self, session_id: str) -> list[dict]:
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT topic, detected_at, message_index FROM topic_history WHERE session_id = ? ORDER BY detected_at", (session_id,)).fetchall()
        conn.close()
        return [{"topic": r[0], "detected_at": r[1], "message_index": r[2]} for r in rows]

    def get_context_stats(self, messages: list[dict]) -> dict:
        """Calcula estadisticas de tokens del contexto construido."""
        total_tokens = 0
        by_role = {}
        for msg in messages:
            role = msg.get("role", "unknown")
            tokens = estimate_tokens(msg.get("content", ""))
            total_tokens += tokens
            by_role[role] = by_role.get(role, 0) + tokens

        return {
            "total_tokens": total_tokens,
            "total_messages": len(messages),
            "by_role": by_role,
            "budget_used_pct": round(total_tokens / TOKEN_BUDGET["total"] * 100, 1),
            "within_budget": total_tokens <= TOKEN_BUDGET["total"],
        }

    def invalidate_summary(self, session_id: str):
        """Invalida el resumen de una sesion."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM context_summaries WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
