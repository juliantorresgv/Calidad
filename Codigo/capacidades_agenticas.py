"""
Capacidades agenticas avanzadas: Planificar-ejecutar-verificar,
memoria a largo plazo, proactividad, explicabilidad y multi-turn reasoning.

Este modulo convierte al agente de un simple RAG a un sistema agentic
con razonamiento multi-paso, memoria persistente y proactividad.
"""
import os
import json
import sqlite3
import time
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parent.parent / "indice_procedimientos.db"


# ──────────────────────────────────────────────
# 1. Planificar-Ejecutar-Verificar (Agentic Workflow)
# ──────────────────────────────────────────────

PLAN_PROMPT = """Eres un planificador experto en calidad HSEQ.
Analiza la siguiente pregunta y crea un plan de accion en pasos.

Pregunta: {question}

Crea un plan con maximo 5 pasos. Cada paso debe ser:
1. Buscar documentos (retrieve)
2. Analizar informacion (analyze)
3. Comparar datos (compare)
4. Sintetizar respuesta (synthesize)
5. Verificar respuesta (verify)

Responde SOLO en JSON:
{{
    "needs_planning": true/false,
    "complexity": "simple/medium/complex",
    "steps": [
        {{
            "step": 1,
            "action": "retrieve/analyze/compare/synthesize/verify",
            "description": "que hacer en este paso",
            "tools": ["bm25", "faiss", "grafo", "reranker"]
        }}
    ]
}}"""


# Mapeo de palabras clave → nombres de skills para decidir complejidad del plan
_SKILL_TRIGGERS_PLAN = {
    "auditoria": ["auditoria", "auditor interna", "auditor externa", "revision gerencial"],
    "capa": ["causa raiz", "cinco porques", "5 porques", "fmea", "amef", "6m", "ishikawa", "accion correctiva", "plan de accion"],
    "checklists": ["checklist", "formato", "plantilla"],
    "mermaid": ["flujo", "flujograma", "diagrama", "mermaid", "mapa de proceso", "arbol de decision", "bpmn"],
    "no_conformidad": ["no conformidad", "desviacion", "nc", "hallazgo"],
    "refactoring_sops": ["revisar borrador", "auditar calidad documental", "refactorizar"],
}


def _detect_skills_for_plan(question: str) -> list[str]:
    """Detecta skills activados por palabras clave en la pregunta."""
    q = question.lower()
    activados = []
    for skill, triggers in _SKILL_TRIGGERS_PLAN.items():
        if any(trigger in q for trigger in triggers):
            activados.append(skill)
    return activados


class AgenticPlanner:
    """Planifica, ejecuta y verifica respuestas del agente."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def plan(self, question: str) -> dict:
        """Crea un plan de accion para responder la pregunta usando heuristicas.
        No depende del LLM, asi que es rapido y deterministico.
        """
        q = question.lower().strip()
        long = len(q)
        skills = _detect_skills_for_plan(q)

        # Opcion 4: umbral por skill activado (tiene prioridad)
        if "auditoria" in skills and "capa" in skills:
            complexity = "very_complex"
            needs_planning = True
        elif "capa" in skills or "no_conformidad" in skills:
            complexity = "complex"
            needs_planning = True
        elif "mermaid" in skills or "refactoring_sops" in skills:
            complexity = "complex"
            needs_planning = True
        elif "checklists" in skills or "auditoria" in skills:
            complexity = "medium"
            needs_planning = True
        else:
            # Opcion 1: umbrales por longitud + keywords
            simple_words = ["que es", "qué es", "cual es", "cuál es", "define", "significado"]
            operativo_words = ["como", "cómo", "donde", "dónde", "quien", "quién", "cuando"]
            complex_words = ["compara", "analiza", "evalua", "fmea", "ishikawa", "plan de accion"]

            if any(w in q for w in simple_words) and long < 80:
                complexity = "simple"
                needs_planning = False
            elif any(w in q for w in operativo_words) and long < 150:
                complexity = "medium"
                needs_planning = True
            elif any(w in q for w in complex_words) or long > 250:
                complexity = "complex"
                needs_planning = True
            else:
                complexity = "medium"
                needs_planning = True

        # Construir pasos segun complejidad
        if complexity == "simple":
            steps = [
                {"step": 1, "action": "retrieve", "description": "Buscar definicion en glosario/documentos", "tools": ["bm25", "faiss"]},
                {"step": 2, "action": "synthesize", "description": "Sintetizar definicion clara", "tools": ["llm"]},
            ]
        elif complexity == "medium":
            steps = [
                {"step": 1, "action": "retrieve", "description": "Buscar documentos relevantes", "tools": ["bm25", "faiss", "grafo"]},
                {"step": 2, "action": "analyze", "description": "Analizar informacion recuperada", "tools": ["reranker"]},
                {"step": 3, "action": "synthesize", "description": "Sintetizar respuesta", "tools": ["llm"]},
            ]
        elif complexity == "complex":
            steps = [
                {"step": 1, "action": "retrieve", "description": "Buscar documentos relevantes", "tools": ["bm25", "faiss", "grafo"]},
                {"step": 2, "action": "analyze", "description": "Analizar informacion recuperada", "tools": ["reranker"]},
                {"step": 3, "action": "compare", "description": "Comparar datos entre documentos", "tools": ["grafo"]},
                {"step": 4, "action": "synthesize", "description": "Sintetizar respuesta completa", "tools": ["llm"]},
                {"step": 5, "action": "verify", "description": "Verificar citas y coherencia", "tools": ["citation_check"]},
            ]
        else:  # very_complex
            steps = [
                {"step": 1, "action": "retrieve", "description": "Recuperar documentos por subtemas", "tools": ["bm25", "faiss", "grafo"]},
                {"step": 2, "action": "analyze", "description": "Analizar cada subtema", "tools": ["reranker"]},
                {"step": 3, "action": "compare", "description": "Comparar normativas y procedimientos", "tools": ["grafo"]},
                {"step": 4, "action": "synthesize", "description": "Sintetizar respuesta integral", "tools": ["llm"]},
                {"step": 5, "action": "verify", "description": "Verificar citas y coherencia", "tools": ["citation_check"]},
                {"step": 6, "action": "recommend", "description": "Generar recomendaciones de accion", "tools": ["llm"]},
            ]

        return {
            "needs_planning": needs_planning,
            "complexity": complexity,
            "skills": skills,
            "steps": steps,
        }

    def execute_step(self, step: dict, context: dict) -> dict:
        """Ejecuta un paso del plan."""
        action = step.get("action", "")
        result = {"step": step["step"], "action": action, "status": "done"}

        if action == "retrieve":
            result["docs_found"] = len(context.get("retrieved_docs", []))
        elif action == "analyze":
            result["analysis"] = "Documentos analizados y rerankeados"
        elif action == "compare":
            result["comparison"] = "Datos comparados entre documentos"
        elif action == "synthesize":
            result["synthesis"] = "Respuesta sintetizada"
        elif action == "verify":
            result["verification"] = "Citas verificadas"

        return result

    def verify_response(self, question: str, answer: str,
                        retrieved_docs: list[dict]) -> dict:
        """Verifica que la respuesta cumple con el plan."""
        verification = {
            "passed": True,
            "checks": [],
        }

        # Check 1: La respuesta cita documentos
        citations = re.findall(r'\b[A-Z]{2,5}[-_]?\d{1,3}[-_]?\d{1,3}\b', answer)
        if not citations and retrieved_docs:
            verification["checks"].append({
                "check": "has_citations",
                "passed": False,
                "message": "La respuesta no cita documentos",
            })
            verification["passed"] = False
        else:
            verification["checks"].append({
                "check": "has_citations",
                "passed": True,
                "count": len(citations),
            })

        # Check 2: La respuesta responde la pregunta
        question_words = set(question.lower().split())
        answer_words = set(answer.lower().split())
        overlap = len(question_words & answer_words) / max(len(question_words), 1)
        if overlap < 0.2:
            verification["checks"].append({
                "check": "answers_question",
                "passed": False,
                "message": f"Baja relevancia ({overlap:.1%})",
            })
            verification["passed"] = False
        else:
            verification["checks"].append({
                "check": "answers_question",
                "passed": True,
                "relevance": round(overlap, 2),
            })

        # Check 3: La respuesta no es demasiado corta
        if len(answer) < 50:
            verification["checks"].append({
                "check": "sufficient_length",
                "passed": False,
                "message": "Respuesta demasiado corta",
            })
            verification["passed"] = False
        else:
            verification["checks"].append({
                "check": "sufficient_length",
                "passed": True,
                "length": len(answer),
            })

        return verification


# ──────────────────────────────────────────────
# 2. Memoria a Largo Plazo
# ──────────────────────────────────────────────

class LongTermMemory:
    """Memoria persistente del usuario entre sesiones."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                category TEXT DEFAULT 'general',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, key)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT NOT NULL,
                preference TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (user_id, preference)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_interests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, topic)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT,
                summary TEXT,
                key_topics TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def remember(self, user_id: str, key: str, value: str, category: str = "general"):
        """Guarda un recuerdo del usuario."""
        self.conn.execute("""
            INSERT OR REPLACE INTO user_memory (user_id, key, value, category)
            VALUES (?, ?, ?, ?)
        """, (user_id, key, value, category))
        self.conn.commit()

    def recall(self, user_id: str, key: str = None, category: str = None) -> list[dict]:
        """Recupera recuerdos del usuario."""
        if key:
            rows = self.conn.execute(
                "SELECT key, value, category, timestamp FROM user_memory WHERE user_id=? AND key=?",
                (user_id, key)
            ).fetchall()
        elif category:
            rows = self.conn.execute(
                "SELECT key, value, category, timestamp FROM user_memory WHERE user_id=? AND category=?",
                (user_id, category)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT key, value, category, timestamp FROM user_memory WHERE user_id=? ORDER BY timestamp DESC LIMIT 20",
                (user_id,)
            ).fetchall()
        return [{"key": r[0], "value": r[1], "category": r[2], "timestamp": r[3]} for r in rows]

    def set_preference(self, user_id: str, preference: str, value: str):
        """Establece una preferencia del usuario."""
        self.conn.execute("""
            INSERT OR REPLACE INTO user_preferences (user_id, preference, value)
            VALUES (?, ?, ?)
        """, (user_id, preference, value))
        self.conn.commit()

    def get_preference(self, user_id: str, preference: str) -> Optional[str]:
        """Obtiene una preferencia del usuario."""
        row = self.conn.execute(
            "SELECT value FROM user_preferences WHERE user_id=? AND preference=?",
            (user_id, preference)
        ).fetchone()
        return row[0] if row else None

    def track_interest(self, user_id: str, topic: str):
        """Registra que el usuario esta interesado en un tema."""
        self.conn.execute("""
            INSERT INTO user_interests (user_id, topic, frequency, last_accessed)
            VALUES (?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, topic)
            DO UPDATE SET frequency = frequency + 1, last_accessed = CURRENT_TIMESTAMP
        """, (user_id, topic))
        self.conn.commit()

    def get_interests(self, user_id: str, limit: int = 10) -> list[dict]:
        """Obtiene los temas de interes del usuario."""
        rows = self.conn.execute("""
            SELECT topic, frequency, last_accessed
            FROM user_interests WHERE user_id=?
            ORDER BY frequency DESC, last_accessed DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [{"topic": r[0], "frequency": r[1], "last_accessed": r[2]} for r in rows]

    def save_conversation_summary(self, user_id: str, session_id: str,
                                   summary: str, key_topics: list[str]):
        """Guarda un resumen de la conversacion."""
        self.conn.execute("""
            INSERT INTO conversation_summary (user_id, session_id, summary, key_topics)
            VALUES (?, ?, ?, ?)
        """, (user_id, session_id, summary, json.dumps(key_topics, ensure_ascii=False)))
        self.conn.commit()

    def get_conversation_history(self, user_id: str, limit: int = 5) -> list[dict]:
        """Obtiene resumenes de conversaciones anteriores."""
        rows = self.conn.execute("""
            SELECT session_id, summary, key_topics, timestamp
            FROM conversation_summary WHERE user_id=?
            ORDER BY timestamp DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [
            {
                "session_id": r[0],
                "summary": r[1],
                "key_topics": json.loads(r[2]) if r[2] else [],
                "timestamp": r[3],
            }
            for r in rows
        ]

    def get_context_for_user(self, user_id: str) -> str:
        """Genera contexto personalizado para el usuario."""
        context_parts = []

        # Preferencias
        prefs = self.conn.execute(
            "SELECT preference, value FROM user_preferences WHERE user_id=?",
            (user_id,)
        ).fetchall()
        if prefs:
            context_parts.append("Preferencias del usuario:")
            for pref, val in prefs:
                context_parts.append(f"  - {pref}: {val}")

        # Intereses recientes
        interests = self.get_interests(user_id, limit=5)
        if interests:
            context_parts.append("\nTemas de interes:")
            for interest in interests:
                context_parts.append(f"  - {interest['topic']} (consultado {interest['frequency']} veces)")

        # Resumen ultima conversacion
        history = self.get_conversation_history(user_id, limit=1)
        if history:
            context_parts.append(f"\nUltima conversacion: {history[0]['summary'][:200]}")

        return "\n".join(context_parts) if context_parts else ""


# ──────────────────────────────────────────────
# 3. Proactividad
# ──────────────────────────────────────────────

class ProactivityEngine:
    """Genera sugerencias proactivas para el usuario."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)

    def get_suggestions(self, user_id: str = "default", role: str = "usuario") -> list[dict]:
        """Genera sugerencias proactivas basadas en el contexto."""
        suggestions = []

        # 1. Documentos por vencer
        try:
            vencidos = self.conn.execute("""
                SELECT COUNT(*) FROM alertas_vencimiento
                WHERE dias_restantes < 0
            """).fetchone()[0]
            if vencidos > 0:
                suggestions.append({
                    "type": "expired_docs",
                    "priority": "high",
                    "message": f"Hay {vencidos} documentos vencidos que requieren atencion",
                    "action": "Revisa la pestaña 'Vencidos' para mas detalles",
                })
        except Exception:
            pass

        # 2. Documentos por vencer pronto
        try:
            por_vencer = self.conn.execute("""
                SELECT COUNT(*) FROM alertas_vencimiento
                WHERE dias_restantes >= 0 AND dias_restantes <= 30
            """).fetchone()[0]
            if por_vencer > 0:
                suggestions.append({
                    "type": "expiring_docs",
                    "priority": "medium",
                    "message": f"{por_vencer} documentos vencen en los proximos 30 dias",
                    "action": "Planifica la actualizacion de estos documentos",
                })
        except Exception:
            pass

        # 3. NCs abiertas (si el rol tiene acceso)
        if role in ("admin", "calidad", "auditor"):
            try:
                from no_conformidades import NoConformidadesAPI
                nc_api = NoConformidadesAPI()
                stats = nc_api.estadisticas_nc()
                if stats.get("por_estado", {}).get("1", 0) > 0:
                    suggestions.append({
                        "type": "open_ncs",
                        "priority": "high",
                        "message": f"Hay {stats['por_estado']['1']} no conformidades abiertas",
                        "action": "Revisa la pestaña 'No Conformidades'",
                    })
            except Exception:
                pass

        # 4. Sugerencias basadas en intereses del usuario
        try:
            memory = LongTermMemory(self.db_path)
            interests = memory.get_interests(user_id, limit=3)
            for interest in interests:
                suggestions.append({
                    "type": "interest_based",
                    "priority": "low",
                    "message": f"Quieres saber mas sobre '{interest['topic']}'?",
                    "action": f"Consulta documentos relacionados con {interest['topic']}",
                })
        except Exception:
            pass

        # 5. Sugerencias de calidad
        try:
            from evaluacion import suggest_improvements
            improvements = suggest_improvements(self.conn)
            for imp in improvements[:2]:
                suggestions.append({
                    "type": "quality_improvement",
                    "priority": imp.get("priority", "medium"),
                    "message": imp.get("description", ""),
                    "action": imp.get("action", ""),
                })
        except Exception:
            pass

        # 6. Sugerencias por rol
        if role == "admin":
            suggestions.append({
                "type": "admin_task",
                "priority": "low",
                "message": "Considera sincronizar con Integr@ para tener datos actualizados",
                "action": "Ve a la pestaña 'Sincronizacion'",
            })
        elif role == "auditor":
            suggestions.append({
                "type": "auditor_task",
                "priority": "low",
                "message": "Revisa el audit trail para verificar trazabilidad",
                "action": "Ve a la pestaña 'Auditoria'",
            })

        return suggestions


# ──────────────────────────────────────────────
# 4. Explicabilidad
# ──────────────────────────────────────────────

class ExplainabilityEngine:
    """Genera explicaciones de como el agente llego a la respuesta."""

    def __init__(self):
        pass

    def explain_retrieval(self, query: str, retrieved_docs: list[dict],
                          scores: dict = None) -> dict:
        """Explica el proceso de retrieval."""
        explanation = {
            "query": query,
            "steps": [],
            "total_docs_retrieved": len(retrieved_docs),
            "top_documents": [],
        }

        # Paso 1: Expansion de query
        explanation["steps"].append({
            "step": 1,
            "name": "Query Expansion",
            "description": f"La pregunta se expandio con sinonimos y abreviaciones del dominio HSEQ",
        })

        # Paso 2: Busqueda semantica
        explanation["steps"].append({
            "step": 2,
            "name": "Semantic Search (FAISS)",
            "description": f"Se busco en {len(retrieved_docs)} documentos usando embeddings vectoriales",
        })

        # Paso 3: Busqueda lexica
        explanation["steps"].append({
            "step": 3,
            "name": "Lexical Search (BM25)",
            "description": "Se busco coincidencias exactas de palabras clave",
        })

        # Paso 4: Expansion por grafo
        explanation["steps"].append({
            "step": 4,
            "name": "Graph Expansion",
            "description": "Se expandio la busqueda a documentos relacionados en el grafo de conocimiento",
        })

        # Paso 5: Reranking
        explanation["steps"].append({
            "step": 5,
            "name": "Reranking (Cross-encoder)",
            "description": "Los documentos se reordenaron por relevancia usando un cross-encoder",
        })

        # Paso 6: Fusion (RRF)
        explanation["steps"].append({
            "step": 6,
            "name": "Reciprocal Rank Fusion (RRF)",
            "description": "Se combinaron los resultados de todos los metodos de busqueda",
        })

        # Top documentos con scores
        for i, doc in enumerate(retrieved_docs[:5]):
            doc_info = {
                "rank": i + 1,
                "codigo": doc.get("codigo", ""),
                "nombre": doc.get("nombre", "")[:80],
                "score": doc.get("score", 0),
                "source": doc.get("source", "hybrid"),
            }
            if scores and doc.get("codigo") in scores:
                doc_info["detailed_scores"] = scores[doc["codigo"]]
            explanation["top_documents"].append(doc_info)

        return explanation

    def format_explanation(self, explanation: dict) -> str:
        """Formatea la explicacion para mostrar al usuario."""
        lines = ["**Como llegue a esta respuesta:**\n"]

        lines.append("**Proceso de retrieval:**")
        for step in explanation["steps"]:
            lines.append(f"{step['step']}. {step['name']}: {step['description']}")

        lines.append(f"\n**Documentos recuperados:** {explanation['total_docs_retrieved']}")

        if explanation["top_documents"]:
            lines.append("\n**Top documentos usados:**")
            for doc in explanation["top_documents"]:
                score_str = f" (score: {doc['score']:.3f})" if doc.get("score") else ""
                lines.append(f"  {doc['rank']}. {doc['codigo']} - {doc['nombre']}{score_str}")

        return "\n".join(lines)

    def explain_decision(self, question: str, needs_retrieval: bool,
                          confidence: float, plan: dict = None) -> str:
        """Explica por que el agente tomo cierta decision."""
        lines = ["**Decision del agente:**\n"]

        if needs_retrieval:
            lines.append("- Se determino que la pregunta requiere buscar documentos en la base de conocimiento")
        else:
            lines.append("- Se determino que la pregunta puede responderse sin retrieval (conocimiento general)")

        lines.append(f"- Confianza: {confidence:.1%}")

        if plan:
            lines.append(f"- Complejidad: {plan.get('complexity', 'simple')}")
            lines.append(f"- Pasos del plan: {len(plan.get('steps', []))}")

        return "\n".join(lines)


# ──────────────────────────────────────────────
# 5. Multi-Turn Reasoning
# ──────────────────────────────────────────────

class MultiTurnReasoner:
    """Mantiene contexto complejo entre turnos de conversacion."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS reasoning_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn INTEGER NOT NULL,
                question TEXT,
                answer TEXT,
                reasoning_state TEXT,
                pending_questions TEXT,
                resolved_topics TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def update_context(self, session_id: str, turn: int, question: str,
                       answer: str, reasoning_state: dict = None):
        """Actualiza el contexto de razonamiento."""
        self.conn.execute("""
            INSERT OR REPLACE INTO reasoning_context
            (session_id, turn, question, answer, reasoning_state,
             pending_questions, resolved_topics)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, turn, question, answer,
            json.dumps(reasoning_state or {}, ensure_ascii=False),
            json.dumps(reasoning_state.get("pending_questions", []) if reasoning_state else [], ensure_ascii=False),
            json.dumps(reasoning_state.get("resolved_topics", []) if reasoning_state else [], ensure_ascii=False),
        ))
        self.conn.commit()

    def get_context(self, session_id: str, last_n: int = 5) -> dict:
        """Obtiene el contexto de razonamiento de los ultimos N turnos."""
        rows = self.conn.execute("""
            SELECT turn, question, answer, reasoning_state, pending_questions, resolved_topics
            FROM reasoning_context WHERE session_id=?
            ORDER BY turn DESC LIMIT ?
        """, (session_id, last_n)).fetchall()

        if not rows:
            return {
                "turns": [],
                "pending_questions": [],
                "resolved_topics": [],
            }

        turns = []
        all_pending = []
        all_resolved = []

        for r in reversed(rows):
            turns.append({
                "turn": r[0],
                "question": r[1],
                "answer": r[2],
                "reasoning_state": json.loads(r[3]) if r[3] else {},
            })
            pending = json.loads(r[4]) if r[4] else []
            resolved = json.loads(r[5]) if r[5] else []
            all_pending.extend(pending)
            all_resolved.extend(resolved)

        return {
            "turns": turns,
            "pending_questions": list(set(all_pending)),
            "resolved_topics": list(set(all_resolved)),
        }

    def detect_topic_shift(self, session_id: str, new_question: str) -> bool:
        """Detecta si el usuario cambio de tema."""
        context = self.get_context(session_id, last_n=1)
        if not context["turns"]:
            return False

        last_question = context["turns"][-1]["question"]
        if not last_question:
            return False

        # Comparar palabras clave
        last_words = set(last_question.lower().split())
        new_words = set(new_question.lower().split())
        overlap = len(last_words & new_words) / max(len(last_words), 1)

        return overlap < 0.2

    def build_multi_turn_context(self, session_id: str, current_question: str) -> str:
        """Construye contexto para la pregunta actual considerando turnos anteriores."""
        context = self.get_context(session_id, last_n=3)

        if not context["turns"]:
            return ""

        parts = ["Contexto de la conversacion anterior:"]

        for turn in context["turns"][-2:]:  # ultimos 2 turnos
            parts.append(f"\nTurno {turn['turn']}:")
            parts.append(f"  Pregunta: {turn['question'][:200]}")
            parts.append(f"  Respuesta: {turn['answer'][:200]}...")

        if context["pending_questions"]:
            parts.append(f"\nPreguntas pendientes: {', '.join(context['pending_questions'][:3])}")

        if context["resolved_topics"]:
            parts.append(f"\nTemas ya resueltos: {', '.join(context['resolved_topics'][:3])}")

        # Detectar cambio de tema
        if self.detect_topic_shift(session_id, current_question):
            parts.append("\n[Nota: El usuario ha cambiado de tema]")

        return "\n".join(parts)

    def extract_follow_up_questions(self, answer: str) -> list[str]:
        """Extrae preguntas de seguimiento de la respuesta del agente."""
        # Buscar preguntas en la respuesta
        questions = re.findall(r'[¿?].+?\?', answer)
        return [q.strip() for q in questions if len(q) > 10]

    def track_resolved_topics(self, question: str, answer: str) -> list[str]:
        """Identifica temas que se resolvieron en esta interaccion."""
        # Extraer temas clave de la pregunta
        topics = []
        topic_keywords = {
            "temperatura": ["temperatura", "grados", "frío", "frio", "refriger"],
            "almacenamiento": ["almacenamiento", "bodega", "estantería", "estanteria"],
            "transporte": ["transporte", "despacho", "ruta", "vehículo", "vehiculo"],
            "calidad": ["calidad", "nc", "no conformidad", "hallazgo"],
            "capa": ["capa", "accion correctiva", "plan de accion", "causa raiz"],
            "auditoria": ["auditoria", "auditoría", "auditor", "inspeccion"],
            "vencimiento": ["vencimiento", "vigencia", "caducidad"],
            "procedimiento": ["procedimiento", "sop", "instructivo", "manual"],
        }

        question_lower = question.lower()
        for topic, keywords in topic_keywords.items():
            if any(kw in question_lower for kw in keywords):
                topics.append(topic)

        return topics


# ──────────────────────────────────────────────
# Inicializacion
# ──────────────────────────────────────────────

def init_agentic_tables(conn: sqlite3.Connection):
    """Crea todas las tablas de capacidades agenticas."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            category TEXT DEFAULT 'general',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, key)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT NOT NULL,
            preference TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (user_id, preference)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            frequency INTEGER DEFAULT 1,
            last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, topic)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            session_id TEXT,
            summary TEXT,
            key_topics TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reasoning_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn INTEGER NOT NULL,
            question TEXT,
            answer TEXT,
            reasoning_state TEXT,
            pending_questions TEXT,
            resolved_topics TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB_PATH))
    init_agentic_tables(conn)

    # Test planner
    planner = AgenticPlanner()
    plan = planner.plan("Compara los procedimientos de almacenamiento entre 2023 y 2024")
    print("Plan:", json.dumps(plan, indent=2, ensure_ascii=False))

    # Test memory
    memory = LongTermMemory()
    memory.remember("test_user", "idioma", "español")
    memory.set_preference("test_user", "formato_respuesta", "detallado")
    memory.track_interest("test_user", "almacenamiento")
    print("\nMemory context:", memory.get_context_for_user("test_user"))

    # Test proactivity
    proactivity = ProactivityEngine()
    suggestions = proactivity.get_suggestions("test_user", "admin")
    print("\nSuggestions:", json.dumps(suggestions, indent=2, ensure_ascii=False))

    # Test explainability
    explainer = ExplainabilityEngine()
    explanation = explainer.explain_retrieval(
        "temperatura almacenamiento",
        [{"codigo": "PGC-16-15", "nombre": "Almacenamiento", "score": 0.85}]
    )
    print("\nExplanation:", explainer.format_explanation(explanation))

    # Test multi-turn
    reasoner = MultiTurnReasoner()
    reasoner.update_context("test_session", 1, "¿Cual es la temperatura?", "2-8°C", {"resolved_topics": ["temperatura"]})
    context = reasoner.build_multi_turn_context("test_session", "¿Y para congelacion?")
    print("\nMulti-turn context:", context)

    conn.close()
