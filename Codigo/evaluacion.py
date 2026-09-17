"""
Evaluacion automatica del agente: LLM-as-judge, RAGAS metrics y Active Learning.

Este modulo evalua cada respuesta del agente en tiempo real usando un LLM
como juez y calcula metricas estandar RAGAS.
"""
import os
import json
import sqlite3
import time
import hashlib
from pathlib import Path
from typing import Optional
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parent.parent / "indice_procedimientos.db"


# ──────────────────────────────────────────────
# 1. LLM-as-Judge
# ──────────────────────────────────────────────

JUDGE_PROMPT = """Eres un evaluador experto en calidad HSEQ. Evalua la siguiente respuesta del agente.

Pregunta del usuario: {question}
Respuesta del agente: {answer}
Documentos recuperados (contexto):
{context}

Evalua en estas dimensiones (0-10 cada una):

1. **Faithfulness** (fidelidad): La respuesta esta fundamentada en los documentos? No inventa informacion?
2. **Answer Relevancy** (relevancia): La respuesta responde directamente a la pregunta?
3. **Context Precision** (precision): Los documentos recuperados son relevantes para la pregunta?
4. **Context Recall** (cobertura): Los documentos contienen toda la informacion necesaria?
5. **Completeness** (completitud): La respuesta es completa o falta informacion importante?
6. **Clarity** (claridad): La respuesta es clara y bien estructurada?
7. **Citation Quality** (citas): Las citas a documentos son correctas y verificables?

Responde SOLO en formato JSON:
{{
    "faithfulness": 0-10,
    "answer_relevancy": 0-10,
    "context_precision": 0-10,
    "context_recall": 0-10,
    "completeness": 0-10,
    "clarity": 0-10,
    "citation_quality": 0-10,
    "overall": 0-10,
    "issues": ["problema1", "problema2"],
    "suggestions": ["sugerencia1", "sugerencia2"]
}}"""


def llm_as_judge(question: str, answer: str, context: str,
                 llm_client=None) -> dict:
    """Evalua la respuesta usando un LLM como juez."""
    result = {
        "faithfulness": 0,
        "answer_relevancy": 0,
        "context_precision": 0,
        "context_recall": 0,
        "completeness": 0,
        "clarity": 0,
        "citation_quality": 0,
        "overall": 0,
        "issues": [],
        "suggestions": [],
        "method": "heuristic",
    }

    # 1. Evaluacion heuristica (siempre disponible)
    result.update(_heuristic_eval(question, answer, context))

    # 2. Evaluacion con LLM (si esta disponible)
    if llm_client:
        try:
            prompt = JUDGE_PROMPT.format(
                question=question[:500],
                answer=answer[:1000],
                context=context[:2000],
            )
            resp = llm_client.chat.completions.create(
                model=os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=500,
            )
            content = resp.choices[0].message.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            llm_scores = json.loads(content)
            # Sobrescribir con scores del LLM
            for key in ["faithfulness", "answer_relevancy", "context_precision",
                        "context_recall", "completeness", "clarity",
                        "citation_quality", "overall"]:
                if key in llm_scores:
                    result[key] = float(llm_scores[key])
            if "issues" in llm_scores:
                result["issues"] = llm_scores["issues"]
            if "suggestions" in llm_scores:
                result["suggestions"] = llm_scores["suggestions"]
            result["method"] = "llm"
        except Exception as e:
            result["method"] = "heuristic"
            result["llm_error"] = str(e)

    return result


def _heuristic_eval(question: str, answer: str, context: str) -> dict:
    """Evaluacion heuristica sin LLM (fallback)."""
    scores = {}

    # Faithfulness: % de palabras de la respuesta que estan en el contexto
    answer_words = set(answer.lower().split())
    context_words = set(context.lower().split())
    if answer_words:
        overlap = len(answer_words & context_words) / len(answer_words)
        scores["faithfulness"] = round(overlap * 10, 1)
    else:
        scores["faithfulness"] = 0

    # Answer relevancy: % de palabras de la pregunta en la respuesta
    question_words = set(question.lower().split())
    if question_words:
        q_overlap = len(question_words & answer_words) / len(question_words)
        scores["answer_relevancy"] = round(q_overlap * 10, 1)
    else:
        scores["answer_relevancy"] = 0

    # Context precision: longitud del contexto (mas corto = mas preciso)
    if context:
        context_len = len(context)
        if context_len < 500:
            scores["context_precision"] = 8
        elif context_len < 2000:
            scores["context_precision"] = 6
        else:
            scores["context_precision"] = 4
    else:
        scores["context_precision"] = 0

    # Context recall: si el contexto contiene palabras clave de la pregunta
    if context and question_words:
        c_words = set(context.lower().split())
        c_overlap = len(question_words & c_words) / len(question_words)
        scores["context_recall"] = round(c_overlap * 10, 1)
    else:
        scores["context_recall"] = 0

    # Completeness: longitud de la respuesta
    if len(answer) < 50:
        scores["completeness"] = 3
    elif len(answer) < 200:
        scores["completeness"] = 6
    elif len(answer) < 500:
        scores["completeness"] = 8
    else:
        scores["completeness"] = 9

    # Clarity: estructura (parrafos, listas)
    clarity = 5
    if "\n\n" in answer:
        clarity += 2  # tiene parrafos
    if "- " in answer or "1. " in answer:
        clarity += 2  # tiene listas
    if "?" in answer:
        clarity += 1  # hace preguntas aclaratorias
    scores["clarity"] = min(clarity, 10)

    # Citation quality: numero de citas
    import re
    citations = re.findall(r'\b[A-Z]{2,5}[-_]?\d{1,3}[-_]?\d{1,3}\b', answer)
    if len(citations) >= 2:
        scores["citation_quality"] = 9
    elif len(citations) == 1:
        scores["citation_quality"] = 7
    elif context:
        scores["citation_quality"] = 3  # tiene contexto pero no cita
    else:
        scores["citation_quality"] = 0

    # Overall: promedio
    scores["overall"] = round(
        sum(scores.values()) / len(scores), 1
    )

    return scores


# ──────────────────────────────────────────────
# 2. RAGAS Metrics (simplificadas)
# ──────────────────────────────────────────────

def faithfulness_score(answer: str, context: str, llm_client=None) -> float:
    """RAGAS faithfulness: que fraccion de la respuesta esta soportada por el contexto.
    Retorna 0.0-1.0."""
    # Dividir respuesta en afirmaciones (oraciones)
    sentences = [s.strip() for s in answer.split(".") if len(s.strip()) > 20]

    if not sentences:
        return 0.0

    supported = 0
    context_lower = context.lower()

    for sent in sentences:
        # Verificar si la afirmacion tiene soporte en el contexto
        sent_words = set(sent.lower().split())
        context_words = set(context_lower.split())
        overlap = len(sent_words & context_words) / max(len(sent_words), 1)
        if overlap > 0.3:
            supported += 1

    return supported / len(sentences)


def answer_relevancy_score(question: str, answer: str, llm_client=None) -> float:
    """RAGAS answer relevancy: que tan relevante es la respuesta a la pregunta.
    Retorna 0.0-1.0."""
    question_words = set(question.lower().split())
    answer_words = set(answer.lower().split())

    if not question_words:
        return 0.0

    # Palabras de la pregunta que aparecen en la respuesta
    relevant = len(question_words & answer_words) / len(question_words)

    # Penalizar respuestas muy cortas o muy largas
    if len(answer) < 50:
        relevant *= 0.5
    elif len(answer) > 2000:
        relevant *= 0.8

    return min(relevant, 1.0)


def context_precision_score(question: str, retrieved_docs: list[dict]) -> float:
    """RAGAS context precision: que fraccion de los documentos recuperados son relevantes.
    Retorna 0.0-1.0."""
    if not retrieved_docs:
        return 0.0

    question_words = set(question.lower().split())
    relevant_count = 0

    for doc in retrieved_docs:
        doc_text = (doc.get("texto", "") or doc.get("nombre", "")).lower()
        doc_words = set(doc_text.split())
        overlap = len(question_words & doc_words) / max(len(question_words), 1)
        if overlap > 0.1:
            relevant_count += 1

    return relevant_count / len(retrieved_docs)


def context_recall_score(question: str, answer: str, retrieved_docs: list[dict]) -> float:
    """RAGAS context recall: el contexto contiene la informacion necesaria para responder.
    Retorna 0.0-1.0."""
    answer_words = set(answer.lower().split())
    context_text = " ".join([
        doc.get("texto", "") or doc.get("nombre", "")
        for doc in retrieved_docs
    ]).lower()
    context_words = set(context_text.split())

    if not answer_words:
        return 0.0

    # Palabras de la respuesta que estan en el contexto
    covered = len(answer_words & context_words) / len(answer_words)
    return covered


def calculate_ragas(question: str, answer: str, retrieved_docs: list[dict],
                    llm_client=None) -> dict:
    """Calcula todas las metricas RAGAS."""
    context = " ".join([
        doc.get("texto", "") or doc.get("nombre", "")
        for doc in retrieved_docs
    ])

    return {
        "faithfulness": round(faithfulness_score(answer, context, llm_client), 3),
        "answer_relevancy": round(answer_relevancy_score(question, answer, llm_client), 3),
        "context_precision": round(context_precision_score(question, retrieved_docs), 3),
        "context_recall": round(context_recall_score(question, answer, retrieved_docs), 3),
    }


# ──────────────────────────────────────────────
# 3. Active Learning
# ──────────────────────────────────────────────

def identify_low_quality_interactions(conn: sqlite3.Connection,
                                        threshold: float = 5.0,
                                        limit: int = 50) -> list[dict]:
    """Identifica interacciones con baja calidad para priorizar mejora."""
    # Buscar en audit_trail o tabla de evaluaciones
    rows = conn.execute("""
        SELECT session_id, pregunta, respuesta, score, timestamp
        FROM evaluaciones_respuestas
        WHERE score < ? AND score > 0
        ORDER BY score ASC
        LIMIT ?
    """, (threshold, limit)).fetchall()

    return [
        {
            "session_id": r[0],
            "pregunta": r[1],
            "respuesta": r[2],
            "score": r[3],
            "timestamp": r[4],
        }
        for r in rows
    ]


def cluster_similar_questions(conn: sqlite3.Connection) -> dict:
    """Agrupa preguntas similares para identificar patrones de fallo."""
    rows = conn.execute("""
        SELECT pregunta, score FROM evaluaciones_respuestas
        WHERE score < 6
        ORDER BY score ASC
        LIMIT 100
    """).fetchall()

    if not rows:
        return {"clusters": 0, "total": 0}

    # Agrupar por palabras clave
    clusters = defaultdict(list)
    for pregunta, score in rows:
        # Extraer palabras clave (sustantivos comunes)
        words = set(pregunta.lower().split())
        # Usar las 2 palabras mas largas como key
        sorted_words = sorted(words, key=len, reverse=True)[:2]
        key = " ".join(sorted(sorted_words))
        clusters[key].append({"pregunta": pregunta, "score": score})

    # Filtrar clusters con mas de 1 elemento
    significant = {k: v for k, v in clusters.items() if len(v) > 1}

    return {
        "clusters": len(significant),
        "total_low_quality": len(rows),
        "top_clusters": dict(list(significant.items())[:5]),
    }


def suggest_improvements(conn: sqlite3.Connection) -> list[dict]:
    """Sugiere mejoras especificas basadas en patrones de fallo."""
    suggestions = []

    # 1. Preguntas frecuentes con baja calidad
    clusters = cluster_similar_questions(conn)
    if clusters["clusters"] > 0:
        suggestions.append({
            "type": "frequent_low_quality",
            "description": f"Se detectaron {clusters['clusters']} grupos de preguntas frecuentes con baja calidad",
            "priority": "high",
            "action": "Revisar y mejorar el system prompt o agregar documentos",
        })

    # 2. Citas faltantes
    try:
        missing_citations = conn.execute("""
            SELECT COUNT(*) FROM citation_verifications
            WHERE all_valid = 0
        """).fetchone()[0]
        if missing_citations > 0:
            suggestions.append({
                "type": "missing_citations",
                "description": f"{missing_citations} respuestas con citas no verificables",
                "priority": "high",
                "action": "Verificar que los codigos citados existan en la BD",
            })
    except Exception:
        pass

    # 3. Alucinaciones detectadas
    try:
        hallucinations = conn.execute("""
            SELECT COUNT(*) FROM hallucination_checks
            WHERE grounded = 0
        """).fetchone()[0]
        if hallucinations > 0:
            suggestions.append({
                "type": "hallucinations",
                "description": f"{hallucinations} respuestas con posible alucinacion",
                "priority": "critical",
                "action": "Revisar retrieval y agregar mas contexto",
            })
    except Exception:
        pass

    # 4. Feedback negativo
    try:
        negative = conn.execute("""
            SELECT COUNT(*) FROM traces WHERE feedback = 'negativo'
        """).fetchone()[0]
        if negative > 0:
            suggestions.append({
                "type": "negative_feedback",
                "description": f"{negative} respuestas con feedback negativo",
                "priority": "medium",
                "action": "Analizar patrones y mejorar respuestas",
            })
    except Exception:
        pass

    return suggestions


# ──────────────────────────────────────────────
# Tabla SQLite para evaluaciones
# ──────────────────────────────────────────────

def init_eval_tables(conn: sqlite3.Connection):
    """Crea tablas para almacenar evaluaciones."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evaluaciones_respuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            pregunta TEXT,
            respuesta TEXT,
            score REAL,
            faithfulness REAL,
            answer_relevancy REAL,
            context_precision REAL,
            context_recall REAL,
            completeness REAL,
            clarity REAL,
            citation_quality REAL,
            method TEXT,
            issues TEXT,
            suggestions TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ragas_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            pregunta TEXT,
            faithfulness REAL,
            answer_relevancy REAL,
            context_precision REAL,
            context_recall REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS active_learning_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            pregunta TEXT,
            score REAL,
            priority TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()


def save_evaluation(conn: sqlite3.Connection, session_id: str,
                    pregunta: str, respuesta: str, eval_result: dict):
    """Guarda evaluacion de respuesta."""
    conn.execute("""
        INSERT INTO evaluaciones_respuestas
        (session_id, pregunta, respuesta, score, faithfulness, answer_relevancy,
         context_precision, context_recall, completeness, clarity, citation_quality,
         method, issues, suggestions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, pregunta, respuesta,
        eval_result.get("overall", 0),
        eval_result.get("faithfulness", 0),
        eval_result.get("answer_relevancy", 0),
        eval_result.get("context_precision", 0),
        eval_result.get("context_recall", 0),
        eval_result.get("completeness", 0),
        eval_result.get("clarity", 0),
        eval_result.get("citation_quality", 0),
        eval_result.get("method", "heuristic"),
        json.dumps(eval_result.get("issues", []), ensure_ascii=False),
        json.dumps(eval_result.get("suggestions", []), ensure_ascii=False),
    ))
    conn.commit()

    # Si el score es bajo, agregar a cola de active learning
    if eval_result.get("overall", 10) < 5:
        priority = "critical" if eval_result.get("overall", 10) < 3 else "high"
        conn.execute("""
            INSERT INTO active_learning_queue (pregunta, score, priority)
            VALUES (?, ?, ?)
        """, (pregunta, eval_result.get("overall", 0), priority))
        conn.commit()


def save_ragas(conn: sqlite3.Connection, session_id: str,
               pregunta: str, ragas: dict):
    """Guarda metricas RAGAS."""
    conn.execute("""
        INSERT INTO ragas_metrics
        (session_id, pregunta, faithfulness, answer_relevancy,
         context_precision, context_recall)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session_id, pregunta,
        ragas["faithfulness"], ragas["answer_relevancy"],
        ragas["context_precision"], ragas["context_recall"],
    ))
    conn.commit()


def get_quality_stats(conn: sqlite3.Connection) -> dict:
    """Obtiene estadisticas de calidad agregadas."""
    stats = {}

    # Promedios de evaluacion
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                AVG(score) as avg_score,
                AVG(faithfulness) as avg_faithfulness,
                AVG(answer_relevancy) as avg_relevancy,
                AVG(context_precision) as avg_precision,
                AVG(context_recall) as avg_recall,
                AVG(completeness) as avg_completeness,
                AVG(clarity) as avg_clarity,
                AVG(citation_quality) as avg_citation
            FROM evaluaciones_respuestas
        """).fetchone()
        if row and row[0] > 0:
            stats["evaluations"] = {
                "total": row[0],
                "avg_score": round(row[1], 2),
                "avg_faithfulness": round(row[2], 2),
                "avg_relevancy": round(row[3], 2),
                "avg_precision": round(row[4], 2),
                "avg_recall": round(row[5], 2),
                "avg_completeness": round(row[6], 2),
                "avg_clarity": round(row[7], 2),
                "avg_citation": round(row[8], 2),
            }
    except Exception:
        stats["evaluations"] = {"total": 0}

    # Promedios RAGAS
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                AVG(faithfulness) as avg_f,
                AVG(answer_relevancy) as avg_ar,
                AVG(context_precision) as avg_cp,
                AVG(context_recall) as avg_cr
            FROM ragas_metrics
        """).fetchone()
        if row and row[0] > 0:
            stats["ragas"] = {
                "total": row[0],
                "avg_faithfulness": round(row[1], 3),
                "avg_relevancy": round(row[2], 3),
                "avg_precision": round(row[3], 3),
                "avg_recall": round(row[4], 3),
            }
    except Exception:
        stats["ragas"] = {"total": 0}

    # Cola de active learning
    try:
        row = conn.execute("""
            SELECT COUNT(*), priority FROM active_learning_queue
            WHERE status = 'pending'
            GROUP BY priority
        """).fetchall()
        stats["active_learning"] = {
            p: c for c, p in row
        }
    except Exception:
        stats["active_learning"] = {}

    # Sugerencias
    stats["suggestions"] = suggest_improvements(conn)

    return stats


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB_PATH))
    init_eval_tables(conn)

    # Test LLM-as-judge
    test_q = "¿Cual es la temperatura de almacenamiento?"
    test_a = "Segun PGC-16-15, la temperatura debe ser 2-8°C para cadena de frio."
    test_ctx = "PGC-16-15: Almacenamiento cadena de frio. Temperatura 2-8 grados Celsius."

    result = llm_as_judge(test_q, test_a, test_ctx)
    print("LLM-as-Judge:", json.dumps(result, indent=2, ensure_ascii=False))

    # Test RAGAS
    ragas = calculate_ragas(test_q, test_a, [{"codigo": "PGC-16-15", "texto": test_ctx}])
    print("\nRAGAS:", json.dumps(ragas, indent=2, ensure_ascii=False))

    # Test stats
    stats = get_quality_stats(conn)
    print("\nStats:", json.dumps(stats, indent=2, ensure_ascii=False))

    conn.close()
