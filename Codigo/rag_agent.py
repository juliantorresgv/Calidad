"""
Paso 4: Agente RAG que combina búsqueda semántica (embeddings) + Mistral
para responder preguntas sobre los procedimientos de Integra.

Uso:
    $env:INTEGRA_DB_SERVER="10.238.66.14"
    $env:MISTRAL_API_KEY="<tu_api_key>"
    python Codigo/rag_agent.py
"""
import json
import os
import pickle
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
from openai import OpenAI
from sklearn.metrics.pairwise import cosine_similarity

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
CHAT_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
EMBED_MODEL = "mistral-embed"
TOP_K = 5  # documentos a recuperar


class RAGIndex:
    """Índice de búsqueda semántica sobre los procedimientos."""

    def __init__(self, db_path: Path = DB_PATH):
        self.conn = sqlite3.connect(str(db_path))
        self._load_index()

    def _load_index(self):
        rows = self.conn.execute("""
            SELECT e.codigo, e.embedding, p.nombre, p.proceso_nom,
                   p.tipo_documento, p.estado, p.estado_desc,
                   p.contenido_texto, p.fecha_publicacion
            FROM embeddings e
            JOIN procedimientos p ON e.codigo = p.codigo
            WHERE p.texto_length > 100
        """).fetchall()

        if not rows:
            raise RuntimeError("No hay embeddings. Ejecuta generate_embeddings.py primero.")

        self.codigos = [r[0] for r in rows]
        self.embeddings = np.array([pickle.loads(r[1]) for r in rows])
        self.nombres = [r[2] for r in rows]
        self.procesos = [r[3] for r in rows]
        self.tipos = [r[4] for r in rows]
        self.estados = [r[5] for r in rows]
        self.estados_desc = [r[6] for r in rows]
        self.textos = [r[7] or "" for r in rows]
        self.fechas_pub = [r[8] for r in rows]
        print(f"  Índice cargado: {len(self.codigos)} documentos")

    def search(self, query_embedding: np.ndarray, top_k: int = TOP_K) -> list[dict]:
        """Busca los documentos más similares al embedding de la consulta."""
        sims = cosine_similarity(query_embedding.reshape(1, -1), self.embeddings)[0]
        top_idx = sims.argsort()[-top_k:][::-1]

        resultados = []
        for idx in top_idx:
            resultados.append({
                "codigo": self.codigos[idx],
                "nombre": self.nombres[idx],
                "proceso": self.procesos[idx],
                "tipo": self.tipos[idx],
                "estado": self.estados[idx],
                "estado_desc": self.estados_desc[idx],
                "fecha_publicacion": self.fechas_pub[idx],
                "similitud": float(sims[idx]),
                "texto": self.textos[idx][:3000],  # contexto para Mistral
            })
        return resultados

    def get_temas(self) -> list[dict]:
        """Devuelve los temas agrupados."""
        rows = self.conn.execute("""
            SELECT tema_id, nombre, descripcion, num_docs, palabras_clave
            FROM temas ORDER BY num_docs DESC
        """).fetchall()
        return [
            {
                "id": r[0],
                "nombre": r[1],
                "descripcion": r[2],
                "num_docs": r[3],
                "palabras_clave": json.loads(r[4]) if r[4] else [],
            }
            for r in rows
        ]

    def get_docs_by_tema(self, tema_id: int, limit: int = 10) -> list[dict]:
        """Devuelve los documentos de un tema."""
        rows = self.conn.execute("""
            SELECT dt.codigo, p.nombre, p.proceso_nom, p.estado_desc, dt.similitud
            FROM documento_tema dt
            JOIN procedimientos p ON dt.codigo = p.codigo
            WHERE dt.tema_id = ?
            ORDER BY dt.similitud DESC
            LIMIT ?
        """, (tema_id, limit)).fetchall()
        return [
            {"codigo": r[0], "nombre": r[1], "proceso": r[2],
             "estado": r[3], "similitud": r[4]}
            for r in rows
        ]


class RAGAgent:
    """Agente RAG: busca documentos relevantes y responde con Mistral."""

    def __init__(self):
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise SystemExit("Falta MISTRAL_API_KEY")

        self.client = OpenAI(base_url=MISTRAL_BASE_URL, api_key=api_key)
        print("  Cargando índice RAG...")
        self.index = RAGIndex()
        self.history: list[dict] = []

    def _embed(self, text: str) -> np.ndarray:
        """Genera embedding de la consulta."""
        resp = self.client.embeddings.create(
            model=EMBED_MODEL,
            input=[text[:8000]],
        )
        return np.array(resp.data[0].embedding)

    def ask(self, question: str) -> str:
        """Responde una pregunta usando RAG."""
        # 1. Generar embedding de la pregunta
        print(f"\n  [RAG] Buscando documentos relevantes...")
        query_emb = self._embed(question)

        # 2. Buscar documentos más similares
        resultados = self.index.search(query_emb, top_k=TOP_K)

        print(f"  [RAG] {len(resultados)} documentos encontrados:")
        for i, r in enumerate(resultados):
            print(f"    {i+1}. {r['codigo']} (sim={r['similitud']:.3f}) - {r['nombre'][:60]}")

        # 3. Construir contexto para Mistral
        contexto_parts = []
        for i, r in enumerate(resultados):
            contexto_parts.append(
                f"--- Documento {i+1}: {r['codigo']} ---\n"
                f"Nombre: {r['nombre']}\n"
                f"Proceso: {r['proceso']}\n"
                f"Tipo: {r['tipo']}\n"
                f"Estado: {r['estado_desc']}\n"
                f"Contenido:\n{r['texto'][:2000]}\n"
            )
        contexto = "\n".join(contexto_parts)

        # 4. Enviar a Mistral con el contexto
        system_prompt = (
            "Eres un agente experto en la plataforma Integr@ de Solistica. "
            "Tienes acceso a documentos reales extraídos de la base de datos de Integra. "
            "Responde en español, de forma clara y concisa. "
            "Cita el código del documento del que extraes la información. "
            "Si la información no está en los documentos proporcionados, dilo claramente."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Contexto:\n{contexto}\n\nPregunta: {question}"},
        ]

        # Incluir historial reciente
        if self.history:
            messages = [messages[0]] + self.history[-4:] + [messages[1]]

        print(f"  [RAG] Consultando a Mistral...")
        response = self.client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=0.2,
        )
        answer = response.choices[0].message.content

        # Guardar en historial
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})

        return answer

    def listar_temas(self):
        """Muestra los temas agrupados."""
        temas = self.index.get_temas()
        print(f"\n  Temas detectados ({len(temas)}):")
        for t in temas:
            print(f"    {t['id']}. {t['nombre']} ({t['num_docs']} docs)")
            print(f"       Palabras: {', '.join(t['palabras_clave'][:5])}")

    def documentos_por_tema(self, tema_id: int):
        """Muestra documentos de un tema."""
        docs = self.index.get_docs_by_tema(tema_id)
        print(f"\n  Documentos del tema {tema_id} ({len(docs)}):")
        for d in docs:
            print(f"    {d['codigo']} - {d['nombre'][:50]} (sim={d['similitud']:.3f})")


def main():
    print("=" * 60)
    print("  AGENTE RAG - INTEGRA + MISTRAL")
    print("=" * 60)

    agent = RAGAgent()

    print("\n  Comandos especiales:")
    print("    /temas         - Lista los temas agrupados")
    print("    /tema <id>     - Muestra documentos de un tema")
    print("    salir          - Termina\n")

    while True:
        try:
            user = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user:
            continue
        if user.lower() in ("salir", "exit", "quit"):
            break

        if user == "/temas":
            agent.listar_temas()
            continue

        if user.startswith("/tema "):
            try:
                tema_id = int(user.split(" ", 1)[1])
                agent.documentos_por_tema(tema_id)
            except (ValueError, IndexError):
                print("  Uso: /tema <id>")
            continue

        try:
            answer = agent.ask(user)
            print(f"\nAgente: {answer}\n")
        except Exception as e:
            print(f"\n  Error: {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    main()
