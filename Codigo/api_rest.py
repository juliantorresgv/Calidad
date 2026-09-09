"""
API REST del Agente de Calidad Integr@.
Expone el agente Graph RAG como una API HTTP para integrarlo con
Power Apps, Teams, web apps u otros sistemas.

Endpoints:
    POST /ask          - Hacer una pregunta al agente
    GET  /search       - Búsqueda de documentos (sin LLM)
    GET  /stats        - Estadísticas del grafo
    GET  /jerarquia    - Tabla jerárquica
    GET  /vencidos     - Documentos vencidos
    GET  /resumen/{cod}- Resumen ejecutivo de un documento
    GET  /glosario     - Buscar términos del glosario
    GET  /health       - Health check

Uso:
    $env:INTEGRA_DB_SERVER="10.238.66.14"
    $env:MISTRAL_API_KEY="<tu_api_key>"
    python Codigo/api_rest.py
    # API disponible en http://localhost:8000
    # Docs interactivas en http://localhost:8000/docs
"""
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Importar GraphRAG
sys.path.insert(0, str(Path(__file__).parent))
from graph_rag import GraphRAG

# ──────────────────────────────────────────────
# Modelos
# ──────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    use_reranking: bool = True
    include_context: bool = False

class AskResponse(BaseModel):
    answer: str
    documentos: list[dict]
    tiempo_total: float
    tiempo_recuperacion: float
    tiempo_llm: float

# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

app = FastAPI(
    title="Agente de Calidad Integr@",
    description="API REST del agente Graph RAG para consulta de documentos de Integr@ (Solistica)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cargar agente al iniciar
print("  Cargando Agente Graph RAG...")
rag = GraphRAG()
print(f"  Agente cargado: {len(rag.docs)} documentos, {rag.graph.number_of_nodes()} nodos")


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "documentos": len(rag.docs),
        "nodos_grafo": rag.graph.number_of_nodes(),
        "aristas_grafo": rag.graph.number_of_edges(),
    }


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    """Hacer una pregunta al agente de calidad."""
    t_start = time.time()

    # Recuperación
    t_rec = time.time()
    resultados = rag.retrieve(req.question, top_k=5, use_reranking=req.use_reranking)
    resultados = rag._filtrar_obsoletos(resultados)[:5]
    t_rec_end = time.time()

    # Respuesta LLM
    t_llm = time.time()
    answer, _ = rag.ask(req.question)
    t_llm_end = time.time()

    docs = []
    for r in resultados:
        doc = {
            "codigo": r["codigo"],
            "nombre": r["nombre"],
            "proceso": r.get("proceso", ""),
            "estado": r.get("estado", ""),
            "score": r.get("score_total", 0),
        }
        if req.include_context:
            doc["texto"] = r.get("texto", "")[:500]
        docs.append(doc)

    return AskResponse(
        answer=answer,
        documentos=docs,
        tiempo_total=time.time() - t_start,
        tiempo_recuperacion=t_rec_end - t_rec,
        tiempo_llm=t_llm_end - t_llm,
    )


@app.get("/search")
async def search(
    q: str = Query(..., description="Texto a buscar"),
    top_k: int = Query(5, ge=1, le=20),
    reranking: bool = Query(False, description="Usar reranking con Mistral"),
):
    """Búsqueda de documentos (sin generar respuesta LLM)."""
    resultados = rag.retrieve(q, top_k=top_k, use_reranking=reranking)
    resultados = rag._filtrar_obsoletos(resultados)
    return {
        "query": q,
        "total": len(resultados),
        "resultados": [
            {
                "codigo": r["codigo"],
                "nombre": r["nombre"],
                "proceso": r.get("proceso", ""),
                "estado": r.get("estado", ""),
                "score_total": r.get("score_total", 0),
                "score_semantico": r.get("score_semantico", 0),
                "score_lexical": r.get("score_lexical", 0),
                "score_grafo": r.get("score_grafo", 0),
            }
            for r in resultados
        ],
    }


@app.get("/stats")
async def stats():
    """Estadísticas del grafo de conocimiento."""
    return rag.grafo_stats()


@app.get("/jerarquia")
async def jerarquia(proceso: Optional[str] = None):
    """Tabla jerárquica de procesos y documentos."""
    return rag.tabla_jerarquica(proceso=proceso)


@app.get("/vencidos")
async def vencidos(solo_vencidos: bool = True):
    """Documentos vencidos o por vencer."""
    return rag.alertas_vencimiento(solo_vencidos=solo_vencidos)


@app.get("/resumen/{codigo}")
async def resumen(codigo: str):
    """Resumen ejecutivo de un documento."""
    r = rag.get_resumen(codigo)
    if not r:
        raise HTTPException(status_code=404, detail=f"No hay resumen para {codigo}")
    return r


@app.get("/glosario")
async def glosario(q: str = Query(..., description="Término a buscar")):
    """Buscar términos del glosario de calidad."""
    return rag.buscar_glosario(q)


@app.get("/temas")
async def temas():
    """Lista temas detectados por clustering."""
    from glosario import GLOSARIO
    # Retornar temas del grafo
    temas_nodes = [n for n in rag.graph.nodes if rag.graph.nodes[n].get("type") == "tema"]
    return {
        "total": len(temas_nodes),
        "temas": [
            {
                "id": t,
                "nombre": rag.graph.nodes[t].get("nombre", ""),
                "documentos": sum(
                    1 for nb in rag.graph.neighbors(t)
                    if rag.graph.nodes[nb].get("type") == "documento"
                ),
            }
            for t in sorted(temas_nodes)
        ],
    }


@app.get("/finops")
async def finops():
    """Dashboard de FinOps: tokens, costos, latencia."""
    return rag.obs.dashboard()


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("\n  Iniciando API REST en http://localhost:8000")
    print("  Docs interactivas en http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
