"""
Evaluación automática de la calidad de recuperación del Graph RAG.
Ejecuta un set de preguntas de prueba y mide precisión, recall y MRR.

Uso:
    $env:MISTRAL_API_KEY="<tu_api_key>"
    python Codigo/evaluar_rag.py
"""
import os
import sys
import time
import sqlite3
from pathlib import Path
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ──────────────────────────────────────────────
# Set de preguntas de prueba con documentos esperados
# ──────────────────────────────────────────────

PREGUNTAS_PRUEBA = [
    {
        "pregunta": "¿cuál es el procedimiento de control de temperatura en cuartos fríos?",
        "esperados": ["WH"],  # proceso esperado
        "tipo": "proceso",
    },
    {
        "pregunta": "¿cómo se gestiona una no conformidad?",
        "esperados": ["GC"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿qué procedimientos existen para recepción de mercancía?",
        "esperados": ["WH"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿cuál es el procedimiento de calificación de equipos IQ OQ PQ?",
        "esperados": ["GC", "WH"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿cómo se realiza el despacho de productos?",
        "esperados": ["WH"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿qué procedimientos hay de seguridad y salud en el trabajo?",
        "esperados": ["ST", "SR"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿cómo se manejan las devoluciones?",
        "esperados": ["WH"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿qué procedimientos existen para maquila y empaque?",
        "esperados": ["MQ"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿cómo se realiza la capacitación del personal?",
        "esperados": ["RH", "GC"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿qué procedimientos hay de gestión de riesgo?",
        "esperados": ["SR"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿cómo se controla la cadena de frío?",
        "esperados": ["WH"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿qué procedimientos existen para auditorías internas?",
        "esperados": ["GC"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿cómo se gestionan los formatos de calidad?",
        "esperados": ["GC"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿qué procedimientos hay de trazabilidad?",
        "esperados": ["WH", "GC"],
        "tipo": "proceso",
    },
    {
        "pregunta": "¿cómo se manejan los productos bloqueados?",
        "esperados": ["WH", "GC"],
        "tipo": "proceso",
    },
]


def evaluar_recuperacion(rag):
    """Evalúa la calidad de recuperación con el set de preguntas."""
    print("=" * 60)
    print("  EVALUACIÓN AUTOMÁTICA DE RECUPERACIÓN")
    print("=" * 60)

    resultados = []
    start_time = time.time()

    for i, prueba in enumerate(PREGUNTAS_PRUEBA):
        pregunta = prueba["pregunta"]
        esperados = prueba["esperados"]

        print(f"\n  [{i+1}/{len(PREGUNTAS_PRUEBA)}] {pregunta[:60]}...")

        try:
            # Solo recuperación (sin reranking para evaluar base)
            resultados_raw = rag.retrieve(pregunta, top_k=5, use_reranking=False)

            # Evaluar
            procesos_recuperados = set()
            for r in resultados_raw:
                proc = (r.get("proceso") or "").upper()
                if proc:
                    procesos_recuperados.add(proc)

            # Precision: de los recuperados, cuántos son esperados
            relevantes = sum(1 for p in procesos_recuperados if any(e in p for e in esperados))
            precision = relevantes / len(procesos_recuperados) if procesos_recuperados else 0

            # Recall: de los esperados, cuántos fueron recuperados
            recall = sum(1 for e in esperados if any(e in p for p in procesos_recuperados)) / len(esperados)

            # MRR: posición del primer documento relevante
            mrr = 0
            for idx, r in enumerate(resultados_raw):
                proc = (r.get("proceso") or "").upper()
                if any(e in proc for e in esperados):
                    mrr = 1 / (idx + 1)
                    break

            resultados.append({
                "pregunta": pregunta,
                "esperados": esperados,
                "recuperados": list(procesos_recuperados),
                "precision": precision,
                "recall": recall,
                "mrr": mrr,
                "top_resultados": [(r["codigo"], r["proceso"], r["score_total"]) for r in resultados_raw[:3]],
            })

            status = "✅" if precision > 0 and recall > 0 else "❌"
            print(f"    {status} precision={precision:.2f} recall={recall:.2f} mrr={mrr:.2f}")
            print(f"    Recuperados: {procesos_recuperados}")
            print(f"    Top 3: {[(r['codigo'], r['proceso']) for r in resultados_raw[:3]]}")

        except Exception as e:
            print(f"    ❌ Error: {e}")
            resultados.append({
                "pregunta": pregunta,
                "esperados": esperados,
                "recuperados": [],
                "precision": 0,
                "recall": 0,
                "mrr": 0,
                "error": str(e),
            })

    # ─── Métricas globales ───
    elapsed = time.time() - start_time
    avg_precision = sum(r["precision"] for r in resultados) / len(resultados)
    avg_recall = sum(r["recall"] for r in resultados) / len(resultados)
    avg_mrr = sum(r["mrr"] for r in resultados) / len(resultados)
    f1 = 2 * avg_precision * avg_recall / (avg_precision + avg_recall) if (avg_precision + avg_recall) > 0 else 0

    print(f"\n{'='*60}")
    print(f"  MÉTRICAS GLOBALES")
    print(f"{'='*60}")
    print(f"  Preguntas evaluadas: {len(resultados)}")
    print(f"  Tiempo total: {elapsed:.1f}s")
    print(f"  Tiempo promedio por pregunta: {elapsed/len(resultados):.1f}s")
    print(f"")
    print(f"  📊 Precision@5: {avg_precision:.3f} ({avg_precision*100:.1f}%)")
    print(f"  📊 Recall:      {avg_recall:.3f} ({avg_recall*100:.1f}%)")
    print(f"  📊 F1-Score:    {f1:.3f} ({f1*100:.1f}%)")
    print(f"  📊 MRR:         {avg_mrr:.3f}")

    # Clasificación de calidad
    if avg_precision >= 0.8 and avg_recall >= 0.8:
        calidad = "🟢 EXCELENTE"
    elif avg_precision >= 0.6 and avg_recall >= 0.6:
        calidad = "🟡 BUENA"
    elif avg_precision >= 0.4:
        calidad = "🟠 REGULAR"
    else:
        calidad = "🔴 DEFICIENTE"

    print(f"\n  Calidad de recuperación: {calidad}")

    # Preguntas que fallaron
    fallidas = [r for r in resultados if r["precision"] == 0]
    if fallidas:
        print(f"\n  ❌ Preguntas que fallaron ({len(fallidas)}):")
        for r in fallidas:
            print(f"    - {r['pregunta'][:60]}")
            print(f"      Esperado: {r['esperados']}, Recuperado: {r['recuperados']}")

    # Guardar resultados
    import json
    report_path = Path(__file__).parent.parent / "evaluacion_rag_resultados.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "metricas": {
                "precision": avg_precision,
                "recall": avg_recall,
                "f1": f1,
                "mrr": avg_mrr,
                "total_preguntas": len(resultados),
                "tiempo_total": elapsed,
            },
            "resultados": resultados,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  Resultados guardados en: {report_path}")

    return {
        "precision": avg_precision,
        "recall": avg_recall,
        "f1": f1,
        "mrr": avg_mrr,
        "total_preguntas": len(resultados),
        "tiempo_total": elapsed,
        "resultados": resultados,
    }


def main():
    # Importar GraphRAG
    sys.path.insert(0, str(Path(__file__).parent))
    from graph_rag import GraphRAG

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("  ⚠ Sin MISTRAL_API_KEY. Ejecuta con: $env:MISTRAL_API_KEY=\"<tu_api_key>\"")
        return

    print("\n  Cargando Graph RAG...")
    rag = GraphRAG()
    print(f"  Documentos cargados: {len(rag.docs)}")
    print(f"  Nodos en grafo: {rag.graph.number_of_nodes()}")

    evaluar_recuperacion(rag)


def guardar_resultados_sqlite(conn, metricas, resultados):
    """Guarda resultados de evaluacion RAG en SQLite."""
    import sqlite3, json
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_eval (
            fecha TEXT PRIMARY KEY,
            precision REAL,
            recall REAL,
            f1 REAL,
            mrr REAL,
            total_preguntas INTEGER,
            tiempo_total REAL,
            fallidas INTEGER,
            detalle TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO pipeline_eval
        (fecha, precision, recall, f1, mrr, total_preguntas, tiempo_total, fallidas, detalle)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        metricas["precision"],
        metricas["recall"],
        metricas["f1"],
        metricas["mrr"],
        metricas["total_preguntas"],
        metricas["tiempo_total"],
        len([r for r in resultados if r.get("precision", 0) == 0]),
        json.dumps(resultados, ensure_ascii=False),
    ))
    conn.commit()


def main(db_path=None):
    # Importar GraphRAG
    sys.path.insert(0, str(Path(__file__).parent))
    from graph_rag import GraphRAG

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("  ⚠ Sin MISTRAL_API_KEY. Ejecuta con: $env:MISTRAL_API_KEY=\"<tu_api_key>\"")
        return

    print("\n  Cargando Graph RAG...")
    rag = GraphRAG()
    print(f"  Documentos cargados: {len(rag.docs)}")
    print(f"  Nodos en grafo: {rag.graph.number_of_nodes()}")

    metricas = evaluar_recuperacion(rag)
    if metricas:
        db_path = db_path or Path(__file__).parent.parent / "indice_procedimientos.db"
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        guardar_resultados_sqlite(conn, metricas, metricas.get("resultados", []))
        conn.close()
        print(f"  Resultados guardados en SQLite: {db_path}")


if __name__ == "__main__":
    main()
