"""
Graph RAG para Integra: combina grafo de conocimiento + BM25 + embeddings
para recuperación híbrida de documentos.

Arquitectura:
  1. Nodos: documentos, procesos, tipos, formatos, normas, usuarios, temas
  2. Aristas: relaciones entre entidades (pertenece a, usa formato, cumple norma, etc.)
  3. Recuperación:
     a) Seed: embeddings (semántico) + BM25 (lexical) → documentos iniciales
     b) Expand: traversar el grafo desde los seeds → documentos relacionados
     c) Rerank: cross-encoder local (mas rapido y mejor que LLM)
     d) Context: incluir entidades y relaciones del grafo en el prompt

Uso:
    from graph_rag import GraphRAG
    rag = GraphRAG()
    resultados = rag.retrieve("¿cómo se controla la temperatura?")
    answer = rag.ask("¿cómo se controla la temperatura?")
"""
import json
import os
import pickle
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import faiss
import networkx as nx
import numpy as np
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity, linear_kernel

# BM25 para mejor retrieval lexico que TF-IDF
try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False

# Cross-encoder para reranking local (mas rapido y mejor que LLM)
try:
    from sentence_transformers import CrossEncoder
    _HAS_CROSSENCODER = True
except ImportError:
    _HAS_CROSSENCODER = False

# Glosario de dominio
from glosario import glosario_para_contexto, buscar_termino, GLOSARIO

# Observabilidad (LangFuse + FinOps)
from observabilidad import Observabilidad

# Governance (guardrails: prompt injection, PII, SQL, tópicos, rate limit)
try:
    from governance import Governance
    _HAS_GOVERNANCE = True
except ImportError:
    _HAS_GOVERNANCE = False

# Content moderation (toxicidad, hate speech, acoso, spam)
try:
    from content_moderation import ContentModeration
    _HAS_MODERATION = True
except ImportError:
    _HAS_MODERATION = False

# Memoria (cache semantico, sesiones, knowledge store)
try:
    from memoria import Memoria
    _HAS_MEMORIA = True
except ImportError:
    _HAS_MEMORIA = False

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"
CHROMA_PATH = Path(__file__).parent.parent / "chroma_db"
FAISS_PATH = Path(__file__).parent.parent / "faiss_index.bin"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
CHAT_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
EMBED_MODEL = "mistral-embed"
EMBED_DIM = 1024

# Pesos para scoring híbrido
W_SEMANTIC = 0.4   # embeddings
W_LEXICAL = 0.3    # TF-IDF
W_GRAPH = 0.3      # grafo
TOP_K_SEED = 10    # seeds iniciales
TOP_K_FINAL = 5    # documentos finales para el LLM
MAX_GRAPH_HOPS = 2  # profundidad de traversa del grafo

# ──────────────────────────────────────────────
# System Prompt: se carga desde system_prompt.md
# ──────────────────────────────────────────────

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"
SKILLS_DIR = Path(__file__).parent / "skills"

# Mapeo de palabras clave → skill
SKILL_TRIGGERS = {
    "mermaid.md": ["flujo", "flujograma", "diagrama", "mermaid", "mapa de proceso",
                   "árbol de decisión", "ishikawa", "causa-efecto", "bpmn"],
    "capa.md": ["causa raíz", "5 porqués", "cinco porqués", "fmea", "amef", "6m",
                "capa", "acción correctiva", "acción preventiva",
                "npr", "severidad", "ocurrencia", "detección"],
    "no_conformidad.md": ["no conformidad", "no conforme", "hallazgo", "desviación",
                          "corrección", "plan de acción", "nc ", "n.c.",
                          "registrar nc", "gestionar nc", "reportar nc"],
    "auditoria.md": ["auditoría", "auditoria", "simular auditor", "roleplay",
                     "invima", "iso 9001", "iso 45001", "auditado", "auditor",
                     "lista de verificación", "hallazgo de auditoría"],
    "checklists.md": ["checklist", "formato", "matriz de captura", "wms",
                      "power apps", "lista de verificación", "campo obligatorio",
                      "foto obligatoria", "firma digital", "alerta condicional"],
    "refactoring_sops.md": ["revisar borrador", "auditar documento", "refactoring",
                            "mejorar sop", "calidad documental", "términos ambiguos",
                            "raci", "revisar procedimiento"],
    "busqueda_filtros.md": ["publicados en", "del proceso", "del año", "vigentes",
                            "obsoletos", "por estado", "filtrar", "por proceso",
                            "por tipo", "por fecha", "de 2024", "de 2023"],
    "comparador_versiones.md": ["comparar versiones", "qué cambió", "diferencias entre",
                                "versión anterior", "historial de cambios", "comparar documentos"],
    "detector_duplicados.md": ["duplicados", "documentos similares", "redundantes",
                               "posibles duplicados", "documentos idénticos"],
    "exportar.md": ["exportar", "descargar", "guardar pdf", "generar pdf", "generar word",
                    "exportar a excel", "guardar respuesta", "descargar respuesta"],
}


def _load_system_prompt() -> str:
    """Carga el system prompt desde el archivo .md."""
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "Eres un agente experto en la plataforma Integr@ de Solistica. "
        "Responde en español, de forma clara y concisa. "
        "Cita el código del documento del que extraes la información."
    )


def _load_relevant_skills(question: str) -> str:
    """Carga los skills relevantes a la pregunta del usuario."""
    question_lower = question.lower()
    loaded_skills = []

    for skill_file, triggers in SKILL_TRIGGERS.items():
        for trigger in triggers:
            if trigger in question_lower:
                skill_path = SKILLS_DIR / skill_file
                if skill_path.exists():
                    content = skill_path.read_text(encoding="utf-8")
                    loaded_skills.append(f"\n\n=== SKILL: {skill_file} ===\n{content}")
                break  # no cargar el mismo skill dos veces

    return "".join(loaded_skills)


SYSTEM_PROMPT_CALIDAD = _load_system_prompt()


class GraphRAG:
    """Motor de Graph RAG con recuperación híbrida."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)

        # Proveedores LLM con fallback automatico
        from llm_providers import LLMProviders
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise SystemExit("Falta MISTRAL_API_KEY")
        self.llm = LLMProviders(
            primary="openai",
            fallback_order=["openai", "mistral", "ollama", "groq", "gemini"],
        )
        self.client = self.llm.client  # compatibilidad hacia atras

        # Observabilidad (LangFuse + FinOps)
        self.obs = Observabilidad()

        # Governance (guardrails de entrada y salida)
        if _HAS_GOVERNANCE:
            self.governance = Governance()
            print(f"  [GraphRAG] Governance: guardrails activos (prompt injection, PII, SQL, rate limit)")
        else:
            self.governance = None

        # Content moderation
        if _HAS_MODERATION:
            self.moderation = ContentModeration()
            print(f"  [GraphRAG] Content moderation: activo (toxicidad, hate speech, acoso)")
        else:
            self.moderation = None

        # Memoria (cache semantico + sesiones)
        if _HAS_MEMORIA:
            self.memoria = Memoria()
            print(f"  [GraphRAG] Memoria: cache semantico + sesiones activo")
        else:
            self.memoria = None

        # Cache de embeddings de query (evita llamar Mistral en consultas repetidas)
        self._query_emb_cache: dict[str, list[float]] = {}

        # Cargar datos
        self._load_documents()
        self._load_embeddings()
        self._build_tfidf()
        self._build_graph()
        self.history: list[dict] = []

    # ──────────────────────────────────────────────
    # Carga de datos
    # ──────────────────────────────────────────────

    def _load_documents(self):
        """Carga todos los documentos con texto desde SQLite."""
        rows = self.conn.execute("""
            SELECT codigo, nombre, estado, estado_desc, proceso_cod, proceso_nom,
                   tipo_documento, contenido_texto, texto_length, fecha_publicacion,
                   elaborador, revisor_proceso, revisor_calidad, aprobador_gerencia
            FROM procedimientos
            WHERE texto_length > 100
            ORDER BY codigo
        """).fetchall()

        if not rows:
            raise RuntimeError("No hay documentos. Ejecuta build_document_index.py primero.")

        self.docs = {}
        self.codigos = []
        for r in rows:
            codigo = r[0]
            self.docs[codigo] = {
                "codigo": codigo,
                "nombre": r[1],
                "estado": r[2],
                "estado_desc": r[3],
                "proceso_cod": r[4],
                "proceso_nom": r[5],
                "tipo_documento": r[6],
                "texto": r[7] or "",
                "texto_length": r[8],
                "fecha_publicacion": r[9],
                "elaborador": r[10],
                "revisor_proceso": r[11],
                "revisor_calidad": r[12],
                "aprobador_gerencia": r[13],
            }
            self.codigos.append(codigo)

        print(f"  [GraphRAG] Documentos cargados: {len(self.codigos)}")

    def _load_embeddings(self):
        """Carga embeddings desde ChromaDB (primario) y construye índice FAISS."""
        import chromadb

        # ChromaDB
        chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        self.collection = chroma_client.get_or_create_collection("procedimientos")

        # Cargar todos los embeddings desde ChromaDB
        results = self.collection.get(include=["embeddings", "metadatas", "documents"])

        if not results["ids"]:
            # Fallback: cargar desde SQLite si ChromaDB está vacío
            print(f"  [GraphRAG] ChromaDB vacío, cargando desde SQLite...")
            rows = self.conn.execute("""
                SELECT e.codigo, e.embedding, p.nombre, p.proceso_nom,
                       p.tipo_documento, p.estado, p.estado_desc, p.contenido_texto
                FROM embeddings e
                JOIN procedimientos p ON e.codigo = p.codigo
            """).fetchall()
            if not rows:
                raise RuntimeError("No hay embeddings. Ejecuta generate_embeddings.py primero.")

            self.embeddings = {}
            self.embedding_matrix = []
            self.embedding_codigos = []
            for r in rows:
                codigo = r[0]
                if codigo in self.docs:
                    emb = pickle.loads(r[1])
                    self.embeddings[codigo] = np.array(emb)
                    self.embedding_matrix.append(emb)
                    self.embedding_codigos.append(codigo)
        else:
            self.embeddings = {}
            self.embedding_matrix = []
            self.embedding_codigos = []
            for i, codigo in enumerate(results["ids"]):
                if codigo in self.docs:
                    emb = np.array(results["embeddings"][i])
                    self.embeddings[codigo] = emb
                    self.embedding_matrix.append(emb)
                    self.embedding_codigos.append(codigo)

        self.embedding_matrix = np.array(self.embedding_matrix) if self.embedding_matrix else None

        # Construir índice FAISS para búsqueda ultra rápida
        if self.embedding_matrix is not None:
            self.faiss_index = faiss.IndexFlatIP(EMBED_DIM)
            vecs = self.embedding_matrix.astype(np.float32)
            faiss.normalize_L2(vecs)
            self.faiss_index.add(vecs)
        else:
            self.faiss_index = None

        print(f"  [GraphRAG] Embeddings cargados: {len(self.embedding_codigos)}")
        print(f"  [GraphRAG] Índice FAISS: {self.faiss_index.ntotal if self.faiss_index else 0} vectores")

    def _build_tfidf(self):
        """Construye índice léxico. Usa BM25 si disponible, sino TF-IDF."""
        if _HAS_BM25:
            print(f"  [GraphRAG] Construyendo índice BM25...")
            self._build_bm25()
        else:
            print(f"  [GraphRAG] Construyendo índice TF-IDF (BM25 no disponible)...")
            self._build_tfidf_fallback()

    def _build_bm25(self):
        """Construye índice BM25 sobre el texto de los documentos."""
        # Stop words en español
        stop_words = {
            "el", "la", "los", "las", "de", "del", "y", "o", "a", "en",
            "que", "es", "se", "para", "con", "por", "un", "una", "su",
            "al", "lo", "como", "mas", "menos", "si", "no", "este", "esta",
            "the", "of", "and", "to", "in", "for", "is", "are", "with",
            "this", "that", "it", "as", "be", "or", "on", "at", "by",
            "an", "from", "was", "were", "has", "have", "had", "not",
            "but", "what", "which", "when", "where", "who", "how",
            "todo", "toda", "todos", "todas", "cada", "alguna", "alguno",
            "entre", "sobre", "hasta", "desde", "sin", "tras", "durante",
            "mediante", "segun", "contra", "ante", "bajo", "cab", "cabe",
        }

        def tokenize(text):
            tokens = re.findall(r"[a-záéíóúñ]{3,}", text.lower())
            return [t for t in tokens if t not in stop_words]

        textos = [self.docs[c]["texto"] for c in self.embedding_codigos]
        self.bm25_corpus = [tokenize(t) for t in textos]
        self.bm25 = BM25Okapi(self.bm25_corpus)
        self.bm25_tokenize = tokenize
        print(f"  [GraphRAG] BM25: {len(self.bm25_corpus)} docs indexados")

    def _build_tfidf_fallback(self):
        """Fallback a TF-IDF si BM25 no esta disponible."""
        stop_words = [
            "el", "la", "los", "las", "de", "del", "y", "o", "a", "en",
            "que", "es", "se", "para", "con", "por", "un", "una", "su",
            "al", "lo", "como", "mas", "menos", "si", "no", "este", "esta",
            "the", "of", "and", "to", "in", "for", "is", "are", "with",
            "this", "that", "it", "as", "be", "or", "on", "at", "by",
            "an", "from", "was", "were", "has", "have", "had", "not",
            "but", "what", "which", "when", "where", "who", "how",
            "todo", "toda", "todos", "todas", "cada", "alguna", "alguno",
            "entre", "sobre", "hasta", "desde", "sin", "tras", "durante",
            "mediante", "segun", "contra", "ante", "bajo", "cab", "cabe",
        ]

        textos = [self.docs[c]["texto"] for c in self.embedding_codigos]

        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=8000,
            stop_words=stop_words,
            token_pattern=r"[a-záéíóúñ]{3,}",
            max_df=0.85,
            min_df=2,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(textos)
        self.tfidf_feature_names = self.tfidf_vectorizer.get_feature_names_out()
        print(f"  [GraphRAG] TF-IDF: {self.tfidf_matrix.shape[0]} docs × {self.tfidf_matrix.shape[1]} términos")

    # ──────────────────────────────────────────────
    # Construcción del grafo de conocimiento
    # ──────────────────────────────────────────────

    def _build_graph(self):
        """Construye el grafo de conocimiento:
        - Nodos: documentos, procesos, tipos, formatos, normas, temas
        - Aristas: relaciones entre entidades
        """
        print(f"  [GraphRAG] Construyendo grafo de conocimiento...")
        start = time.time()

        self.graph = nx.Graph()

        # 1. Nodos de documentos
        for codigo in self.embedding_codigos:
            doc = self.docs[codigo]
            self.graph.add_node(
                f"doc:{codigo}",
                type="documento",
                codigo=codigo,
                nombre=doc["nombre"],
                estado=doc["estado_desc"],
            )

        # 2. Nodos de procesos + aristas doc→proceso
        for codigo in self.embedding_codigos:
            doc = self.docs[codigo]
            if doc["proceso_cod"]:
                proc_node = f"proceso:{doc['proceso_cod']}"
                self.graph.add_node(
                    proc_node,
                    type="proceso",
                    nombre=doc["proceso_nom"],
                    codigo=doc["proceso_cod"],
                )
                self.graph.add_edge(f"doc:{codigo}", proc_node, relation="pertenece_a")

        # 3. Nodos de tipos de documento + aristas
        for codigo in self.embedding_codigos:
            doc = self.docs[codigo]
            if doc["tipo_documento"]:
                tipo_node = f"tipo:{doc['tipo_documento']}"
                self.graph.add_node(tipo_node, type="tipo_documento", nombre=doc["tipo_documento"])
                self.graph.add_edge(f"doc:{codigo}", tipo_node, relation="es_de_tipo")

        # 4. Nodos de usuarios + aristas
        for codigo in self.embedding_codigos:
            doc = self.docs[codigo]
            for role, user in [
                ("elaborador", doc["elaborador"]),
                ("revisor_proceso", doc["revisor_proceso"]),
                ("revisor_calidad", doc["revisor_calidad"]),
                ("aprobador_gerencia", doc["aprobador_gerencia"]),
            ]:
                if user and user.strip():
                    user_node = f"user:{user.strip()}"
                    self.graph.add_node(user_node, type="usuario", nombre=user.strip())
                    self.graph.add_edge(f"doc:{codigo}", user_node, relation=role)

        # 5. Aristas documento→documento por proceso compartido
        # (conexión entre docs del mismo proceso)
        proceso_docs = defaultdict(list)
        for codigo in self.embedding_codigos:
            proc = self.docs[codigo]["proceso_cod"]
            if proc:
                proceso_docs[proc].append(codigo)

        for proc, docs in proceso_docs.items():
            # Conectar documentos del mismo proceso (limitar para evitar explosión)
            if len(docs) <= 20:
                for i in range(len(docs)):
                    for j in range(i + 1, len(docs)):
                        self.graph.add_edge(
                            f"doc:{docs[i]}", f"doc:{docs[j]}",
                            relation="mismo_proceso",
                            proceso=proc,
                        )

        # 6. Nodos de temas (clusters) desde SQLite
        try:
            tema_rows = self.conn.execute(
                "SELECT tema_id, nombre, palabras_clave FROM temas"
            ).fetchall()
            for tema_id, nombre, palabras in tema_rows:
                tema_node = f"tema:{tema_id}"
                self.graph.add_node(
                    tema_node,
                    type="tema",
                    nombre=nombre,
                    palabras_clave=json.loads(palabras) if palabras else [],
                )

                # Conectar documentos a su tema
                doc_rows = self.conn.execute(
                    "SELECT codigo FROM documento_tema WHERE tema_id = ?", (tema_id,)
                ).fetchall()
                for (doc_codigo,) in doc_rows:
                    if f"doc:{doc_codigo}" in self.graph:
                        self.graph.add_edge(tema_node, f"doc:{doc_codigo}", relation="pertenece_a_tema")
        except sqlite3.OperationalError:
            pass  # tabla temas no existe aún

        elapsed = time.time() - start
        n_nodes = self.graph.number_of_nodes()
        n_edges = self.graph.number_of_edges()
        print(f"  [GraphRAG] Grafo: {n_nodes} nodos, {n_edges} aristas ({elapsed:.1f}s)")

        # Estadísticas por tipo
        tipos = defaultdict(int)
        for n in self.graph.nodes:
            tipos[self.graph.nodes[n].get("type", "?")] += 1
        for t, c in sorted(tipos.items()):
            print(f"           {t}: {c}")

    # ──────────────────────────────────────────────
    # Recuperación híbrida
    # ──────────────────────────────────────────────

    def _embed_query(self, query: str) -> np.ndarray:
        """Genera embedding de la consulta con cache y fallback automatico."""
        # Cache de embeddings de query
        cache_key = query[:200].lower().strip()
        if cache_key in self._query_emb_cache:
            return np.array(self._query_emb_cache[cache_key])

        try:
            emb, provider = self.llm.embeddings(query[:8000])
            if provider != "mistral":
                print(f"  [GraphRAG] Embedding query via {provider} fallback")
            vec = np.array(emb)
            # Guardar en cache (max 500 queries)
            if len(self._query_emb_cache) < 500:
                self._query_emb_cache[cache_key] = emb
            return vec
        except Exception as e:
            raise RuntimeError(f"No se pudo generar embedding: {e}")

    def _semantic_search(self, query_emb: np.ndarray, top_k: int = TOP_K_SEED) -> list[tuple[str, float]]:
        """Búsqueda por similitud semántica usando FAISS (ultra rápido)."""
        if self.faiss_index is None or self.faiss_index.ntotal == 0:
            return []
        vec = query_emb.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(vec)
        scores, indices = self.faiss_index.search(vec, min(top_k, self.faiss_index.ntotal))
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(self.embedding_codigos):
                results.append((self.embedding_codigos[idx], float(scores[0][i])))
        return results

    def _lexical_search(self, query: str, top_k: int = TOP_K_SEED) -> list[tuple[str, float]]:
        """Búsqueda léxica. Usa BM25 si disponible, sino TF-IDF."""
        if _HAS_BM25 and hasattr(self, "bm25"):
            return self._bm25_search(query, top_k)
        return self._tfidf_search(query, top_k)

    def _bm25_search(self, query: str, top_k: int = TOP_K_SEED) -> list[tuple[str, float]]:
        """Búsqueda por BM25 (mejor que TF-IDF para documentos de longitud variable)."""
        tokens = self.bm25_tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        top_idx = scores.argsort()[-top_k:][::-1]
        max_score = scores[top_idx[0]] if scores[top_idx[0]] > 0 else 1.0
        return [(self.embedding_codigos[i], float(scores[i] / max_score))
                for i in top_idx if scores[i] > 0]

    def _tfidf_search(self, query: str, top_k: int = TOP_K_SEED) -> list[tuple[str, float]]:
        """Búsqueda por TF-IDF (fallback)."""
        query_vec = self.tfidf_vectorizer.transform([query])
        scores = linear_kernel(query_vec, self.tfidf_matrix).flatten()
        top_idx = scores.argsort()[-top_k:][::-1]
        return [(self.embedding_codigos[i], float(scores[i])) for i in top_idx if scores[i] > 0]

    def _graph_expand(self, seed_codigos: list[str], max_hops: int = MAX_GRAPH_HOPS) -> dict[str, float]:
        """Expande desde los seeds usando el grafo. Retorna {codigo: score_grafo}."""
        graph_scores = defaultdict(float)

        for seed_codigo in seed_codigos:
            seed_node = f"doc:{seed_codigo}"
            if seed_node not in self.graph:
                continue

            # BFS desde el seed
            visited = {seed_node: 0}
            queue = [(seed_node, 0)]

            while queue:
                node, hops = queue.pop(0)
                if hops >= max_hops:
                    continue

                for neighbor in self.graph.neighbors(node):
                    if neighbor not in visited:
                        visited[neighbor] = hops + 1
                        queue.append((neighbor, hops + 1))

                        # Si el vecino es un documento, darle score
                        if neighbor.startswith("doc:"):
                            codigo = neighbor[4:]
                            # Score decrece con la distancia
                            edge_data = self.graph.get_edge_data(node, neighbor) or {}
                            relation = edge_data.get("relation", "")

                            # Ponderar por tipo de relación
                            rel_weight = {
                                "mismo_proceso": 0.6,
                                "pertenece_a_tema": 0.8,
                                "pertenece_a": 0.3,
                                "es_de_tipo": 0.2,
                            }.get(relation, 0.4)

                            score = rel_weight / (hops + 1)
                            graph_scores[codigo] = max(graph_scores[codigo], score)

        return dict(graph_scores)

    def _rerank_with_llm(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """Reordena los candidatos. Usa cross-encoder local si disponible, sino LLM."""
        if not candidates:
            return candidates[:top_k]

        # Cross-encoder local (mas rapido y mejor que LLM para reranking)
        if _HAS_CROSSENCODER:
            return self._rerank_cross_encoder(query, candidates, top_k)

        # Fallback: reranking con LLM
        return self._rerank_with_llm_fallback(query, candidates, top_k)

    def _rerank_cross_encoder(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """Reranking con cross-encoder local (sentence-transformers)."""
        if not hasattr(self, "_cross_encoder"):
            print(f"  [GraphRAG] Cargando cross-encoder (primera vez)...")
            try:
                self._cross_encoder = CrossEncoder(
                    "cross-encoder/ms-marco-MiniLM-L-6-v2",
                    max_length=512,
                )
            except Exception as e:
                print(f"  [GraphRAG] Cross-encoder no disponible ({e}), fallback a LLM")
                return self._rerank_with_llm_fallback(query, candidates, top_k)

        print(f"  [GraphRAG] Reranking {len(candidates)} candidatos con cross-encoder...")

        # Preparar pares (query, documento)
        pairs = []
        for c in candidates[:15]:
            doc_text = f"{c['codigo']} {c['nombre']} {c.get('texto', '')[:500]}"
            pairs.append((query, doc_text))

        try:
            scores = self._cross_encoder.predict(pairs)
        except Exception as e:
            print(f"  [GraphRAG] Cross-encoder fallo ({e}), fallback a LLM")
            return self._rerank_with_llm_fallback(query, candidates, top_k)

        # Ordenar por score descendente
        ranked_idx = scores.argsort()[::-1]
        reranked = [candidates[i] for i in ranked_idx if i < len(candidates)]
        return reranked[:top_k]

    def _rerank_with_llm_fallback(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """Reranking con LLM (fallback cuando cross-encoder no disponible)."""
        if not candidates or not self.client:
            return candidates[:top_k]

        docs_list = []
        for i, c in enumerate(candidates[:15]):
            docs_list.append(f"{i+1}. [{c['codigo']}] {c['nombre'][:80]}")

        prompt = (
            f"Pregunta del usuario: {query}\n\n"
            f"Documentos candidatos:\n" + "\n".join(docs_list) + "\n\n"
            f"Ordena los documentos del MÁS relevante al MENOS relevante para responder la pregunta.\n"
            f"Responde SOLO con los números separados por comas, ej: 3,1,5,2,4"
        )

        try:
            resp, provider = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100,
            )
            print(f"  [GraphRAG] Reranking via {provider} (fallback LLM)")
            respuesta = resp.choices[0].message.content.strip()

            orden = []
            for num in re.findall(r'\d+', respuesta):
                idx = int(num) - 1
                if 0 <= idx < len(candidates) and candidates[idx] not in [candidates[i] for i in orden]:
                    orden.append(idx)

            reranked = [candidates[i] for i in orden]
            for i, c in enumerate(candidates[:15]):
                if c not in reranked:
                    reranked.append(c)

            return reranked[:top_k]

        except Exception as e:
            print(f"  [GraphRAG] Reranking fallo ({e}), usando orden original")
            return candidates[:top_k]

    def _hyde_generate(self, query: str) -> str | None:
        """HyDE: genera un documento hipotetico de respuesta para mejorar retrieval.
        El LLM genera una respuesta hipotetica, se embede y se usa para busqueda semantica.
        Esto mejora el recall porque el documento hipotetico esta mas cerca de los
        documentos reales que la pregunta original.
        """
        try:
            prompt = (
                f"Eres un experto en calidad HSEQ farmaceutica. "
                f"Responde brevemente (maximo 200 palabras) la siguiente pregunta "
                f"como si fuera un fragmento de un procedimiento de calidad:\n\n"
                f"Pregunta: {query}\n\nRespuesta hipotetica:"
            )
            resp, provider = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            hyde_text = resp.choices[0].message.content.strip()
            if len(hyde_text) > 50:
                print(f"  [GraphRAG] HyDE: documento hipotetico generado ({len(hyde_text)} chars, via {provider})")
                return hyde_text
        except Exception as e:
            print(f"  [GraphRAG] HyDE: no disponible ({e}), usando query original")
        return None

    def _multi_query_reformulate(self, query: str) -> list[str]:
        """Multi-query: reformula la pregunta en 3 variantes para mejorar recall.
        Si el LLM no esta disponible, usa variaciones basadas en keywords.
        """
        try:
            prompt = (
                f"Eres un experto en calidad HSEQ. Reformula la siguiente pregunta "
                f"en 3 variantes diferentes que busquen la misma informacion. "
                f"Responde SOLO con las 3 variantes, una por linea, sin numeracion.\n\n"
                f"Pregunta original: {query}\n\nVariantes:"
            )
            resp, provider = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )
            text = resp.choices[0].message.content.strip()
            variantes = [v.strip() for v in text.split("\n") if v.strip() and len(v.strip()) > 10]
            if len(variantes) >= 2:
                print(f"  [GraphRAG] Multi-query: {len(variantes)} variantes generadas (via {provider})")
                return variantes[:3]
        except Exception:
            pass

        # Fallback: variaciones simples basadas en keywords
        variantes = [query]
        if "?" in query:
            variantes.append(query.replace("?", " procedimiento"))
        if not query.startswith("como"):
            variantes.append(f"como {query}")
        return variantes[:3]

    def _crag_evaluate(self, query: str, resultados: list[dict]) -> str:
        """Corrective RAG: evalua la calidad de la recuperacion.
        Retorna: 'good', 'ambiguous', o 'poor'
        """
        if not resultados:
            return "poor"

        # Evaluar por scores
        top_score = resultados[0].get("score_total", 0)
        avg_score = sum(r.get("score_total", 0) for r in resultados) / len(resultados)

        # Si el top score es alto y hay varios resultados, es good
        if top_score > 0.3 and len(resultados) >= 3:
            return "good"
        # Si hay algunos resultados pero scores bajos, es ambiguous
        elif top_score > 0.1 or len(resultados) >= 2:
            return "ambiguous"
        else:
            return "poor"

    def retrieve(self, query: str, top_k: int = TOP_K_FINAL, use_reranking: bool = True) -> list[dict]:
        """Recuperación híbrida: semántico + lexical + grafo.
        Incluye HyDE, multi-query retrieval y CRAG.
        """
        # 1. HyDE: generar documento hipotetico
        hyde_text = self._hyde_generate(query)

        # 2. Multi-query: reformular en variantes
        query_variants = self._multi_query_reformulate(query)

        # 3. Generar embeddings: query original + HyDE + variantes
        embeddings_to_search = []
        query_emb = self._embed_query(query)
        embeddings_to_search.append(query_emb)

        if hyde_text:
            hyde_emb = self._embed_query(hyde_text)
            embeddings_to_search.append(hyde_emb)

        for v in query_variants[1:]:  # skip first (original)
            try:
                v_emb = self._embed_query(v)
                embeddings_to_search.append(v_emb)
            except Exception:
                pass

        # 4. Búsqueda semántica con todos los embeddings (fusion)
        sem_results = {}
        for emb in embeddings_to_search:
            results = self._semantic_search(emb, top_k=TOP_K_SEED)
            for codigo, score in results:
                # Max fusion: quedarse con el mejor score
                sem_results[codigo] = max(sem_results.get(codigo, 0), score)

        # 5. Búsqueda lexical BM25 con query original + variantes
        lex_results = {}
        for q in query_variants:
            results = self._lexical_search(q, top_k=TOP_K_SEED)
            for codigo, score in results:
                lex_results[codigo] = max(lex_results.get(codigo, 0), score)

        # 6. Combinar seeds
        all_seeds = set(sem_results.keys()) | set(lex_results.keys())

        # 7. Expansión por grafo
        graph_scores = self._graph_expand(list(all_seeds), max_hops=MAX_GRAPH_HOPS)

        # 8. Scoring híbrido
        candidates = set(sem_results.keys()) | set(lex_results.keys()) | set(graph_scores.keys())

        scored = []
        for codigo in candidates:
            sem_score = sem_results.get(codigo, 0.0)
            lex_score = lex_results.get(codigo, 0.0)
            gra_score = graph_scores.get(codigo, 0.0)

            # Score combinado
            total = (
                W_SEMANTIC * sem_score
                + W_LEXICAL * lex_score
                + W_GRAPH * gra_score
            )
            scored.append((codigo, total, sem_score, lex_score, gra_score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # 9. Construir resultados con contexto del grafo
        # Tomar más candidatos para reranking (top 15) y luego rerankear a top_k
        rerank_pool = min(top_k * 3, 15) if use_reranking else top_k
        resultados = []
        for codigo, total, sem, lex, gra in scored[:rerank_pool]:
            doc = self.docs.get(codigo, {})
            grafo_info = self._get_graph_context(codigo)
            # Parent-child: recuperar secciones relevantes del documento padre
            secciones = self._get_relevant_sections(codigo, query, max_sections=3)
            resultados.append({
                "codigo": codigo,
                "nombre": doc.get("nombre", ""),
                "proceso": doc.get("proceso_nom", ""),
                "tipo_documento": doc.get("tipo_documento", ""),
                "estado": doc.get("estado_desc", ""),
                "fecha_publicacion": doc.get("fecha_publicacion", ""),
                "score_total": total,
                "score_semantico": sem,
                "score_lexical": lex,
                "score_grafo": gra,
                "texto": doc.get("texto", "")[:2500],
                "secciones": secciones,
                "grafo": grafo_info,
            })

        # 10. CRAG: evaluar calidad de la recuperacion
        crag_quality = self._crag_evaluate(query, resultados)
        if crag_quality == "poor":
            print(f"  [GraphRAG] CRAG: recuperacion POOR (scores bajos)")
            # Intentar con mas candidatos y sin reranking
            if len(resultados) < top_k:
                for codigo, total, sem, lex, gra in scored[rerank_pool:rerank_pool + top_k]:
                    doc = self.docs.get(codigo, {})
                    grafo_info = self._get_graph_context(codigo)
                    resultados.append({
                        "codigo": codigo,
                        "nombre": doc.get("nombre", ""),
                        "proceso": doc.get("proceso_nom", ""),
                        "tipo_documento": doc.get("tipo_documento", ""),
                        "estado": doc.get("estado_desc", ""),
                        "fecha_publicacion": doc.get("fecha_publicacion", ""),
                        "score_total": total,
                        "score_semantico": sem,
                        "score_lexical": lex,
                        "score_grafo": gra,
                        "texto": doc.get("texto", "")[:2500],
                        "secciones": [],
                        "grafo": grafo_info,
                    })
        elif crag_quality == "ambiguous":
            print(f"  [GraphRAG] CRAG: recuperacion AMBIGUOUS (scores medios)")
        else:
            print(f"  [GraphRAG] CRAG: recuperacion GOOD (scores altos)")

        # 11. Reranking con cross-encoder (o LLM fallback)
        if use_reranking and len(resultados) > top_k:
            print(f"  [GraphRAG] Reranking {len(resultados)} candidatos...")
            resultados = self._rerank_with_llm(query, resultados, top_k=top_k)

        return resultados[:top_k]

    def _get_relevant_sections(self, codigo: str, query: str, max_sections: int = 3) -> list[dict]:
        """Parent-child retrieval: obtiene las secciones mas relevantes del documento.
        Busca dentro del texto del documento las secciones que mejor matchean la query.
        """
        doc = self.docs.get(codigo, {})
        texto = doc.get("texto", "")
        if not texto or len(texto) < 200:
            return []

        # Dividir el documento en secciones por headers comunes
        secciones = re.split(r'\n(?=[A-Z][A-ZÁÉÍÓÚ\s]{5,}:?)', texto)
        if len(secciones) <= 1:
            # Fallback: dividir por parrafos
            secciones = texto.split("\n\n")

        # Filtrar secciones muy cortas
        secciones = [s for s in secciones if len(s.strip()) > 50]

        if not secciones:
            return []

        # BM25 sobre las secciones del documento
        query_tokens = re.findall(r"[a-záéíóúñ]{3,}", query.lower())
        if not query_tokens:
            return []

        try:
            from rank_bm25 import BM25Okapi
            sec_tokens = [re.findall(r"[a-záéíóúñ]{3,}", s.lower()) for s in secciones]
            bm25_sec = BM25Okapi(sec_tokens)
            scores = bm25_sec.get_scores(query_tokens)
            top_idx = scores.argsort()[-max_sections:][::-1]
            return [
                {
                    "texto": secciones[i].strip()[:800],
                    "score": float(scores[i]),
                }
                for i in top_idx if scores[i] > 0
            ]
        except Exception:
            return []

    def _get_graph_context(self, codigo: str) -> dict:
        """Obtiene el contexto del grafo para un documento."""
        node = f"doc:{codigo}"
        if node not in self.graph:
            return {}

        procesos = []
        tipos = []
        usuarios = []
        temas = []
        docs_relacionados = []

        for neighbor in self.graph.neighbors(node):
            n_data = self.graph.nodes[neighbor]
            edge = self.graph.get_edge_data(node, neighbor) or {}
            relation = edge.get("relation", "")
            n_type = n_data.get("type", "")

            if n_type == "proceso":
                procesos.append(n_data.get("nombre", ""))
            elif n_type == "tipo_documento":
                tipos.append(n_data.get("nombre", ""))
            elif n_type == "usuario":
                usuarios.append({"nombre": n_data.get("nombre", ""), "rol": relation})
            elif n_type == "tema":
                temas.append(n_data.get("nombre", ""))
            elif n_type == "documento" and neighbor != node:
                docs_relacionados.append({
                    "codigo": n_data.get("codigo", ""),
                    "nombre": n_data.get("nombre", ""),
                    "relation": relation,
                })

        return {
            "procesos": procesos,
            "tipos": tipos,
            "usuarios": usuarios[:4],  # limitar
            "temas": temas,
            "docs_relacionados": docs_relacionados[:5],
        }

    # ──────────────────────────────────────────────
    # Generación de respuesta
    # ──────────────────────────────────────────────

    def _filtrar_obsoletos(self, resultados: list[dict]) -> list[dict]:
        """Filtra documentos obsoletos de los resultados.
        Excluye cualquier documento con estado 'O' (Obsoleto).
        """
        filtrados = []
        excluidos = 0
        for r in resultados:
            estado = (r.get("estado") or "").upper().strip()
            # Excluir obsoletos
            if estado == "OBSOLETO" or estado == "O":
                excluidos += 1
                continue
            filtrados.append(r)
        if excluidos > 0:
            print(f"  [GraphRAG] {excluidos} documentos obsoletos excluidos")
        return filtrados

    def ask(self, question: str) -> str:
        """Responde una pregunta usando Graph RAG."""
        # ── Guardrail de entrada: governance ──
        if self.governance:
            ok, reason = self.governance.validate_input(question)
            if not ok:
                safe = self.governance.safe_response(reason)
                print(f"  [GraphRAG] Entrada bloqueada por governance: {reason}")
                return safe, []

        # ── Content moderation de entrada ──
        if self.moderation:
            mod_result = self.moderation.moderate(question)
            if mod_result.get("blocked"):
                safe = (
                    f"Tu mensaje fue bloqueado por content moderation. "
                    f"Categoria: {mod_result.get('category', 'N/A')}. "
                    f"Por favor, mantén la conversación enfocada en calidad HSEQ."
                )
                print(f"  [GraphRAG] Entrada bloqueada por moderation: {mod_result.get('category')}")
                return safe, []
            question = mod_result.get("filtered_text", question)

        # ── Cache semantico: buscar si ya respondimos esta pregunta ──
        if self.memoria:
            cached = self.memoria.cache_semantic_lookup(question)
            if cached:
                print(f"  [GraphRAG] Cache HIT (match: {cached.get('match_type', 'exact')})")
                return cached["respuesta"], []

        # Iniciar traza de observabilidad
        trace_id = self.obs.start_trace(question)

        print(f"\n  [GraphRAG] Recuperando documentos...")
        t_rec_start = time.time()
        resultados = self.retrieve(question, top_k=TOP_K_FINAL * 2)  # recuperar más para compensar filtrado

        # Filtrar documentos obsoletos
        n_before = len(resultados)
        resultados = self._filtrar_obsoletos(resultados)
        n_obsoletos = n_before - len(resultados)
        resultados = resultados[:TOP_K_FINAL]
        t_rec_end = time.time()

        # Trackear recuperación
        self.obs.track_retrieval(
            trace_id, question, len(resultados), n_obsoletos,
            t_rec_end - t_rec_start
        )

        print(f"  [GraphRAG] {len(resultados)} documentos vigentes recuperados:")
        for i, r in enumerate(resultados):
            print(f"    {i+1}. {r['codigo']} (total={r['score_total']:.3f} "
                  f"sem={r['score_semantico']:.2f} lex={r['score_lexical']:.2f} "
                  f"grafo={r['score_grafo']:.2f}) - {r['nombre'][:50]}")

        # Glosario relevante
        glosario_ctx = glosario_para_contexto(question)

        # Construir contexto enriquecido con grafo + resúmenes
        contexto_parts = []
        for i, r in enumerate(resultados):
            grafo = r.get("grafo", {})
            grafo_str = ""
            if grafo.get("procesos"):
                grafo_str += f"Proceso: {', '.join(grafo['procesos'])}\n"
            if grafo.get("temas"):
                grafo_str += f"Tema: {', '.join(grafo['temas'])}\n"
            if grafo.get("docs_relacionados"):
                rels = [f"{d['codigo']} ({d['relation']})" for d in grafo['docs_relacionados'][:3]]
                grafo_str += f"Documentos relacionados: {', '.join(rels)}\n"

            # Resumen ejecutivo si existe
            resumen = self.get_resumen(r["codigo"])
            resumen_str = ""
            if resumen and resumen.get("resumen"):
                resumen_str = f"Resumen ejecutivo: {resumen['resumen']}\n"
                if resumen.get("proposito"):
                    resumen_str += f"Propósito: {resumen['proposito']}\n"
                if resumen.get("alcance"):
                    resumen_str += f"Alcance: {resumen['alcance']}\n"
                if resumen.get("palabras_clave"):
                    resumen_str += f"Palabras clave: {resumen['palabras_clave']}\n"

            contexto_parts.append(
                f"--- Documento {i+1}: {r['codigo']} ---\n"
                f"Nombre: {r['nombre']}\n"
                f"Estado: {r['estado']}\n"
                f"{grafo_str}{resumen_str}"
                f"Contenido:\n{r['texto'][:2000]}\n"
            )

        contexto = "\n".join(contexto_parts)

        # Incluir glosario si hay términos relevantes
        if glosario_ctx:
            contexto = glosario_ctx + "\n\n" + contexto

        # Incluir alertas de vencimiento si la pregunta es sobre vigencia
        if any(w in question.lower() for w in ["venc", "vigente", "caduc", "actual", "vigencia"]):
            alertas = self.alertas_vencimiento(solo_vencidos=True)
            if alertas:
                alertas_str = "\nALERTAS DE VENCIMIENTO:\n"
                for a in alertas[:5]:
                    alertas_str += f"- {a['codigo']}: {a['estado_alerta']} ({a['dias_restantes']} días) - {a['nombre'][:50]}\n"
                contexto = alertas_str + "\n" + contexto

        system_prompt = SYSTEM_PROMPT_CALIDAD

        # Cargar skills relevantes a la pregunta
        skills_ctx = _load_relevant_skills(question)
        skills_activados = []
        if skills_ctx:
            system_prompt = system_prompt + skills_ctx
            skills_activados = [s.strip() for s in skills_ctx.split("=== SKILL:")[1:]]
            skills_activados = [s.split("===")[0].strip() for s in skills_activados]
            print(f"  [GraphRAG] Skills activados: {len(skills_activados)}")
            self.obs.track_skills(trace_id, skills_activados)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Contexto:\n{contexto}\n\nPregunta: {question}"},
        ]

        if self.history:
            messages = [messages[0]] + self.history[-6:] + [messages[1]]

        print(f"  [GraphRAG] Consultando LLM...")
        t_llm_start = time.time()
        try:
            response, provider_used = self.llm.chat(
                messages=messages,
                temperature=0.2,
            )
            if provider_used != "mistral":
                print(f"  [GraphRAG] Respuesta via {provider_used} (fallback)")
        except RuntimeError as e:
            print(f"  [GraphRAG] Error: todos los proveedores fallaron")
            raise
        t_llm_end = time.time()
        answer = response.choices[0].message.content

        # ── Guardrail de salida: governance (PII, credenciales) ──
        if self.governance:
            ok_out, reason_out = self.governance.validate_output(answer)
            if not ok_out:
                answer = self.governance.safe_response(reason_out)
                print(f"  [GraphRAG] Salida bloqueada por governance: {reason_out}")
            else:
                answer = self.governance._filter_pii(answer)

        # ── Content moderation de salida ──
        if self.moderation:
            mod_out = self.moderation.moderate(answer)
            if mod_out.get("blocked"):
                answer = self.governance.safe_response("content_moderation_output") if self.governance else "Respuesta bloqueada por content moderation."
                print(f"  [GraphRAG] Salida bloqueada por moderation")
            else:
                answer = mod_out.get("filtered_text", answer)

        # Trackear llamada LLM
        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0
        self.obs.track_llm_call(
            trace_id, provider_used, "chat_completion",
            prompt_tokens, completion_tokens,
            t_llm_end - t_llm_start
        )

        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})

        # ── Guardar en cache semantico ──
        if self.memoria:
            cache_type = "procedimiento" if any(
                kw in question.lower()
                for kw in ["procedimiento", "pafa", "peop", "pgc", "pco", "pwhs", "pcp"]
            ) else "general"
            self.memoria.cache_set(
                question, answer,
                modelo=provider_used,
                tokens_input=prompt_tokens,
                tokens_output=completion_tokens,
                cache_type=cache_type,
            )

        # Cerrar traza
        self.obs.end_trace(trace_id, answer)

        return answer, resultados

    def ask_stream(self, question: str):
        """Version streaming de ask(). Genera tokens uno a uno.

        Yields:
            (token_text, provider_used, resultados)
            El primer yield tiene token="" y provider="" con los resultados.
            Los siguientes yields tienen tokens de texto.
            El ultimo yield tiene token=None para señalar fin.
        """
        # ── Guardrail de entrada: governance ──
        if self.governance:
            ok, reason = self.governance.validate_input(question)
            if not ok:
                safe = self.governance.safe_response(reason)
                print(f"  [GraphRAG] Entrada bloqueada por governance: {reason}")
                yield safe, "governance", []
                return

        # ── Content moderation de entrada ──
        if self.moderation:
            mod_result = self.moderation.moderate(question)
            if mod_result.get("blocked"):
                safe = (
                    f"Tu mensaje fue bloqueado por content moderation. "
                    f"Categoria: {mod_result.get('category', 'N/A')}. "
                    f"Por favor, mantén la conversación enfocada en calidad HSEQ."
                )
                print(f"  [GraphRAG] Entrada bloqueada por moderation: {mod_result.get('category')}")
                yield safe, "moderation", []
                return
            question = mod_result.get("filtered_text", question)

        # ── Cache semantico: buscar si ya respondimos esta pregunta ──
        if self.memoria:
            cached = self.memoria.cache_semantic_lookup(question)
            if cached:
                print(f"  [GraphRAG] Cache HIT (match: {cached.get('match_type', 'exact')})")
                yield cached["respuesta"], "cache", []
                return

        trace_id = self.obs.start_trace(question)

        print(f"\n  [GraphRAG] Recuperando documentos...")
        t_rec_start = time.time()
        resultados = self.retrieve(question, top_k=TOP_K_FINAL * 2)

        n_before = len(resultados)
        resultados = self._filtrar_obsoletos(resultados)
        n_obsoletos = n_before - len(resultados)
        resultados = resultados[:TOP_K_FINAL]
        t_rec_end = time.time()

        self.obs.track_retrieval(
            trace_id, question, len(resultados), n_obsoletos,
            t_rec_end - t_rec_start
        )

        print(f"  [GraphRAG] {len(resultados)} documentos vigentes recuperados:")
        for i, r in enumerate(resultados):
            print(f"    {i+1}. {r['codigo']} (total={r['score_total']:.3f} "
                  f"sem={r['score_semantico']:.2f} lex={r['score_lexical']:.2f} "
                  f"grafo={r['score_grafo']:.2f}) - {r['nombre'][:50]}")

        glosario_ctx = glosario_para_contexto(question)

        contexto_parts = []
        for i, r in enumerate(resultados):
            grafo = r.get("grafo", {})
            grafo_str = ""
            if grafo.get("procesos"):
                grafo_str += f"Proceso: {', '.join(grafo['procesos'])}\n"
            if grafo.get("temas"):
                grafo_str += f"Tema: {', '.join(grafo['temas'])}\n"
            if grafo.get("docs_relacionados"):
                rels = [f"{d['codigo']} ({d['relation']})" for d in grafo['docs_relacionados'][:3]]
                grafo_str += f"Documentos relacionados: {', '.join(rels)}\n"

            resumen = self.get_resumen(r["codigo"])
            resumen_str = ""
            if resumen and resumen.get("resumen"):
                resumen_str = f"Resumen ejecutivo: {resumen['resumen']}\n"
                if resumen.get("proposito"):
                    resumen_str += f"Propósito: {resumen['proposito']}\n"
                if resumen.get("alcance"):
                    resumen_str += f"Alcance: {resumen['alcance']}\n"
                if resumen.get("palabras_clave"):
                    resumen_str += f"Palabras clave: {resumen['palabras_clave']}\n"

            contexto_parts.append(
                f"--- Documento {i+1}: {r['codigo']} ---\n"
                f"Nombre: {r['nombre']}\n"
                f"Estado: {r['estado']}\n"
                f"{grafo_str}{resumen_str}"
                f"Contenido:\n{r['texto'][:2000]}\n"
            )

        contexto = "\n".join(contexto_parts)

        if glosario_ctx:
            contexto = glosario_ctx + "\n\n" + contexto

        if any(w in question.lower() for w in ["venc", "vigente", "caduc", "actual", "vigencia"]):
            alertas = self.alertas_vencimiento(solo_vencidos=True)
            if alertas:
                alertas_str = "\nALERTAS DE VENCIMIENTO:\n"
                for a in alertas[:5]:
                    alertas_str += f"- {a['codigo']}: {a['estado_alerta']} ({a['dias_restantes']} días) - {a['nombre'][:50]}\n"
                contexto = alertas_str + "\n" + contexto

        system_prompt = SYSTEM_PROMPT_CALIDAD

        skills_ctx = _load_relevant_skills(question)
        skills_activados = []
        if skills_ctx:
            system_prompt = system_prompt + skills_ctx
            skills_activados = [s.strip() for s in skills_ctx.split("=== SKILL:")[1:]]
            skills_activados = [s.split("===")[0].strip() for s in skills_activados]
            print(f"  [GraphRAG] Skills activados: {len(skills_activados)}")
            self.obs.track_skills(trace_id, skills_activados)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Contexto:\n{contexto}\n\nPregunta: {question}"},
        ]

        if self.history:
            messages = [messages[0]] + self.history[-6:] + [messages[1]]

        print(f"  [GraphRAG] Consultando LLM (streaming)...")
        t_llm_start = time.time()

        # Yield inicial con los resultados (para que la UI los muestre)
        yield "", "", resultados

        full_answer = ""
        provider_used = ""
        try:
            for token, provider in self.llm.chat_stream(
                messages=messages,
                temperature=0.2,
            ):
                provider_used = provider
                full_answer += token
                yield token, provider, None
        except RuntimeError as e:
            print(f"  [GraphRAG] Error: todos los proveedores fallaron")
            raise

        t_llm_end = time.time()

        # ── Guardrail de salida: governance (PII, credenciales) ──
        # Nota: en streaming, el filtrado se hace al final sobre la respuesta completa
        if self.governance:
            ok_out, reason_out = self.governance.validate_output(full_answer)
            if not ok_out:
                full_answer = self.governance.safe_response(reason_out)
                print(f"  [GraphRAG] Salida bloqueada por governance: {reason_out}")
            else:
                full_answer = self.governance._filter_pii(full_answer)

        # ── Content moderation de salida ──
        if self.moderation:
            mod_out = self.moderation.moderate(full_answer)
            if mod_out.get("blocked"):
                full_answer = self.governance.safe_response("content_moderation_output") if self.governance else "Respuesta bloqueada por content moderation."
                print(f"  [GraphRAG] Salida bloqueada por moderation")
            else:
                full_answer = mod_out.get("filtered_text", full_answer)

        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": full_answer})

        # ── Guardar en cache semantico ──
        if self.memoria:
            cache_type = "procedimiento" if any(
                kw in question.lower()
                for kw in ["procedimiento", "pafa", "peop", "pgc", "pco", "pwhs", "pcp"]
            ) else "general"
            self.memoria.cache_set(
                question, full_answer,
                modelo=provider_used,
                tokens_input=0, tokens_output=0,
                cache_type=cache_type,
            )

        self.obs.end_trace(trace_id, full_answer)

        # Senal de fin
        yield None, provider_used, None

    # ──────────────────────────────────────────────
    # Feedback del usuario
    # ──────────────────────────────────────────────

    def guardar_feedback(self, pregunta: str, respuesta: str, feedback: str, comentario: str = "") -> bool:
        """Guarda feedback del usuario (thumbs up/down) en SQLite.
        feedback: 'positive' o 'negative'
        """
        try:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback_usuario (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pregunta TEXT,
                    respuesta TEXT,
                    feedback TEXT,
                    comentario TEXT,
                    timestamp TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            self.conn.execute("""
                INSERT INTO feedback_usuario (pregunta, respuesta, feedback, comentario)
                VALUES (?, ?, ?, ?)
            """, (pregunta[:500], respuesta[:2000], feedback, comentario[:500]))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"  [GraphRAG] Error guardando feedback: {e}")
            return False

    def obtener_feedback_stats(self) -> dict:
        """Obtiene estadisticas de feedback del usuario."""
        try:
            rows = self.conn.execute("""
                SELECT feedback, COUNT(*) as count
                FROM feedback_usuario
                GROUP BY feedback
            """).fetchall()
            stats = {"positive": 0, "negative": 0, "total": 0}
            for row in rows:
                fb, count = row
                stats[fb] = count
                stats["total"] += count
            return stats
        except Exception:
            return {"positive": 0, "negative": 0, "total": 0}

    # ──────────────────────────────────────────────
    # Exploración del grafo
    # ──────────────────────────────────────────────

    # ──────────────────────────────────────────────
    # Comparador de versiones de documentos
    # ──────────────────────────────────────────────

    def buscar_versiones(self, nombre: str = "", proceso: str = "") -> list[dict]:
        """Busca documentos que tienen multiples versiones (mismo nombre, diferentes codigos).
        Retorna grupos de versiones.
        """
        if nombre:
            rows = self.conn.execute("""
                SELECT codigo, nombre, estado, estado_desc, proceso_nom,
                       tipo_documento, fecha_elaboracion, fecha_publicacion,
                       fecha_obsoleto, texto_length
                FROM procedimientos
                WHERE nombre LIKE ?
                ORDER BY fecha_elaboracion
            """, (f"%{nombre}%",)).fetchall()
        elif proceso:
            rows = self.conn.execute("""
                SELECT codigo, nombre, estado, estado_desc, proceso_nom,
                       tipo_documento, fecha_elaboracion, fecha_publicacion,
                       fecha_obsoleto, texto_length
                FROM procedimientos
                WHERE proceso_nom LIKE ?
                ORDER BY nombre, fecha_elaboracion
            """, (f"%{proceso}%",)).fetchall()
        else:
            # Buscar todos los grupos con multiples versiones
            rows = self.conn.execute("""
                SELECT codigo, nombre, estado, estado_desc, proceso_nom,
                       tipo_documento, fecha_elaboracion, fecha_publicacion,
                       fecha_obsoleto, texto_length
                FROM procedimientos
                WHERE nombre IN (
                    SELECT nombre FROM procedimientos
                    GROUP BY nombre HAVING COUNT(*) > 1
                )
                ORDER BY nombre, fecha_elaboracion
            """).fetchall()

        # Agrupar por nombre
        grupos = {}
        for row in rows:
            nombre_doc = row[1]
            if nombre_doc not in grupos:
                grupos[nombre_doc] = []
            grupos[nombre_doc].append({
                "codigo": row[0],
                "nombre": row[1],
                "estado": row[2],
                "estado_desc": row[3],
                "proceso_nom": row[4],
                "tipo_documento": row[5],
                "fecha_elaboracion": row[6],
                "fecha_publicacion": row[7],
                "fecha_obsoleto": row[8],
                "texto_length": row[9],
            })

        # Solo retornar grupos con mas de 1 version
        resultado = []
        for nombre_doc, versiones in grupos.items():
            if len(versiones) > 1:
                resultado.append({
                    "nombre": nombre_doc,
                    "num_versiones": len(versiones),
                    "versiones": versiones,
                })

        return resultado

    def comparar_documentos(self, codigo1: str, codigo2: str) -> dict:
        """Compara dos documentos y retorna las diferencias.
        Usa difflib para generar un diff linea por linea.
        """
        import difflib

        doc1 = self.get_documento(codigo1)
        doc2 = self.get_documento(codigo2)

        if not doc1:
            return {"error": f"No se encontro el documento {codigo1}"}
        if not doc2:
            return {"error": f"No se encontro el documento {codigo2}"}

        texto1 = doc1.get("texto", "")
        texto2 = doc2.get("texto", "")

        lineas1 = texto1.splitlines()
        lineas2 = texto2.splitlines()

        # Diff unificado
        diff = list(difflib.unified_diff(
            lineas1, lineas2,
            fromfile=f"{codigo1} ({doc1.get('estado_desc', '')})",
            tofile=f"{codigo2} ({doc2.get('estado_desc', '')})",
            lineterm="",
        ))

        # Estadisticas
        agregadas = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        eliminadas = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        modificadas = min(agregadas, eliminadas)

        # Similaridad
        ratio = difflib.SequenceMatcher(None, texto1, texto2).ratio()

        # Diff lado a lado (para HTML)
        side_by_side = []
        matcher = difflib.SequenceMatcher(None, lineas1, lineas2)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for i in range(i1, i2):
                    side_by_side.append({"tipo": "igual", "linea": lineas1[i]})
            elif tag == "replace":
                for i in range(i1, i2):
                    side_by_side.append({"tipo": "eliminada", "linea": lineas1[i]})
                for j in range(j1, j2):
                    side_by_side.append({"tipo": "agregada", "linea": lineas2[j]})
            elif tag == "delete":
                for i in range(i1, i2):
                    side_by_side.append({"tipo": "eliminada", "linea": lineas1[i]})
            elif tag == "insert":
                for j in range(j1, j2):
                    side_by_side.append({"tipo": "agregada", "linea": lineas2[j]})

        return {
            "doc1": {
                "codigo": codigo1,
                "nombre": doc1.get("nombre", ""),
                "estado": doc1.get("estado_desc", ""),
                "fecha_publicacion": doc1.get("fecha_publicacion", ""),
                "texto_length": len(texto1),
            },
            "doc2": {
                "codigo": codigo2,
                "nombre": doc2.get("nombre", ""),
                "estado": doc2.get("estado_desc", ""),
                "fecha_publicacion": doc2.get("fecha_publicacion", ""),
                "texto_length": len(texto2),
            },
            "similitud": ratio,
            "lineas_agregadas": agregadas,
            "lineas_eliminadas": eliminadas,
            "lineas_modificadas": modificadas,
            "diff_unificado": "\n".join(diff),
            "diff_lado_a_lado": side_by_side,
        }

    # ──────────────────────────────────────────────
    # Dashboard de metricas en tiempo real
    # ──────────────────────────────────────────────

    def dashboard_metricas(self) -> dict:
        """Obtiene metricas detalladas para el dashboard interactivo."""
        # Traces por dia
        traces_por_dia = self.conn.execute("""
            SELECT DATE(timestamp) as fecha,
                   COUNT(*) as traces,
                   SUM(total_tokens) as tokens,
                   SUM(costo_usd) as costo,
                   AVG(latencia_total) as latencia_avg,
                   AVG(latencia_recuperacion) as latencia_rec,
                   AVG(latencia_llm) as latencia_llm
            FROM finops_traces
            GROUP BY DATE(timestamp)
            ORDER BY fecha
        """).fetchall()

        # Llamadas por modelo
        por_modelo = self.conn.execute("""
            SELECT modelo,
                   COUNT(*) as llamadas,
                   SUM(prompt_tokens) as prompt_tokens,
                   SUM(completion_tokens) as completion_tokens,
                   SUM(total_tokens) as total_tokens,
                   SUM(costo_usd) as costo,
                   AVG(latencia) as latencia_avg
            FROM finops_llm_calls
            GROUP BY modelo
            ORDER BY llamadas DESC
        """).fetchall()

        # Traces recientes (ultimas 20)
        traces_recientes = self.conn.execute("""
            SELECT timestamp, pregunta, modelo, total_tokens,
                   costo_usd, latencia_total, documentos_recuperados,
                   skills_activados, obsoletos_filtrados
            FROM finops_traces
            ORDER BY id DESC
            LIMIT 20
        """).fetchall()

        # Distribucion de latencia
        latencia_dist = self.conn.execute("""
            SELECT
                CASE
                    WHEN latencia_total < 5 THEN '0-5s'
                    WHEN latencia_total < 15 THEN '5-15s'
                    WHEN latencia_total < 30 THEN '15-30s'
                    WHEN latencia_total < 60 THEN '30-60s'
                    WHEN latencia_total < 120 THEN '60-120s'
                    ELSE '120s+'
                END as rango,
                COUNT(*) as count
            FROM finops_traces
            GROUP BY rango
            ORDER BY MIN(latencia_total)
        """).fetchall()

        # Tokens por dia (prompt vs completion)
        tokens_por_dia = self.conn.execute("""
            SELECT DATE(timestamp) as fecha,
                   SUM(prompt_tokens) as prompt,
                   SUM(completion_tokens) as completion
            FROM finops_traces
            GROUP BY DATE(timestamp)
            ORDER BY fecha
        """).fetchall()

        # Feedback stats
        fb_stats = self.obtener_feedback_stats()

        return {
            "traces_por_dia": [
                {"fecha": r[0], "traces": r[1], "tokens": r[2],
                 "costo": r[3] or 0, "latencia_avg": r[4] or 0,
                 "latencia_rec": r[5] or 0, "latencia_llm": r[6] or 0}
                for r in traces_por_dia
            ],
            "por_modelo": [
                {"modelo": r[0], "llamadas": r[1], "prompt_tokens": r[2],
                 "completion_tokens": r[3], "total_tokens": r[4],
                 "costo": r[5] or 0, "latencia_avg": r[6] or 0}
                for r in por_modelo
            ],
            "traces_recientes": [
                {"timestamp": r[0], "pregunta": r[1][:80], "modelo": r[2],
                 "tokens": r[3], "costo": r[4] or 0, "latencia": r[5] or 0,
                 "documentos": r[6], "skills": r[7], "obsoletos": r[8]}
                for r in traces_recientes
            ],
            "latencia_dist": [
                {"rango": r[0], "count": r[1]} for r in latencia_dist
            ],
            "tokens_por_dia": [
                {"fecha": r[0], "prompt": r[1], "completion": r[2]}
                for r in tokens_por_dia
            ],
            "feedback": fb_stats,
        }

    def grafo_stats(self) -> dict:
        """Estadísticas del grafo."""
        tipos = defaultdict(int)
        for n in self.graph.nodes:
            tipos[self.graph.nodes[n].get("type", "?")] += 1

        return {
            "nodos": self.graph.number_of_nodes(),
            "aristas": self.graph.number_of_edges(),
            "por_tipo": dict(tipos),
            "documentos": len(self.codigos),
            "embeddings": len(self.embedding_codigos),
        }

    def explorar_nodo(self, nodo_id: str) -> dict:
        """Explora un nodo del grafo y sus vecinos."""
        if nodo_id not in self.graph:
            return {"error": f"Nodo '{nodo_id}' no existe"}

        node_data = self.graph.nodes[nodo_id]
        vecinos = []
        for neighbor in self.graph.neighbors(nodo_id):
            n_data = self.graph.nodes[neighbor]
            edge = self.graph.get_edge_data(nodo_id, neighbor) or {}
            vecinos.append({
                "nodo": neighbor,
                "tipo": n_data.get("type", ""),
                "nombre": n_data.get("nombre", ""),
                "relacion": edge.get("relation", ""),
            })

        return {
            "nodo": nodo_id,
            "tipo": node_data.get("type", ""),
            "nombre": node_data.get("nombre", ""),
            "vecinos": vecinos,
        }

    def listar_temas(self):
        """Lista los temas del grafo."""
        temas = [n for n in self.graph.nodes if self.graph.nodes[n].get("type") == "tema"]
        print(f"\n  Temas en el grafo ({len(temas)}):")
        for t in sorted(temas):
            data = self.graph.nodes[t]
            docs_count = sum(
                1 for nb in self.graph.neighbors(t)
                if self.graph.nodes[nb].get("type") == "documento"
            )
            palabras = data.get("palabras_clave", [])
            print(f"    {t}: {data.get('nombre', '?')} ({docs_count} docs)")
            if palabras:
                print(f"       Palabras: {', '.join(palabras[:5])}")

    # ──────────────────────────────────────────────
    # Resúmenes ejecutivos
    # ──────────────────────────────────────────────

    def get_resumen(self, codigo: str) -> dict | None:
        """Obtiene el resumen ejecutivo de un documento."""
        row = self.conn.execute("""
            SELECT resumen, palabras_clave, proposito, alcance
            FROM resumenes WHERE codigo = ?
        """, (codigo,)).fetchone()
        if not row:
            return None
        return {
            "resumen": row[0],
            "palabras_clave": row[1],
            "proposito": row[2],
            "alcance": row[3],
        }

    def get_documento(self, codigo: str) -> dict | None:
        """Obtiene el documento completo con todos sus metadatos para el visor."""
        row = self.conn.execute("""
            SELECT codigo, nombre, proceso_nom, tipo_documento, estado_desc,
                   fecha_publicacion, vigencia_dias, contenido_texto
            FROM procedimientos WHERE codigo = ?
        """, (codigo,)).fetchone()
        if not row:
            return None

        doc = {
            "codigo": row[0],
            "nombre": row[1],
            "proceso": row[2],
            "tipo_documento": row[3],
            "estado": row[4],
            "fecha_publicacion": row[5],
            "vigencia_dias": row[6],
            "texto": row[7] or "",
        }

        # Resumen si existe
        resumen = self.get_resumen(codigo)
        if resumen:
            doc["resumen"] = resumen.get("resumen", "")
            doc["proposito"] = resumen.get("proposito", "")
            doc["alcance"] = resumen.get("alcance", "")
            doc["palabras_clave"] = resumen.get("palabras_clave", "")

        # Contexto del grafo
        grafo = self._get_graph_context(codigo)
        if grafo:
            doc["grafo_procesos"] = grafo.get("procesos", [])
            doc["grafo_temas"] = grafo.get("temas", [])
            doc["grafo_usuarios"] = grafo.get("usuarios", [])
            doc["docs_relacionados"] = grafo.get("docs_relacionados", [])

        # Alerta de vencimiento si aplica
        try:
            alerta = self.conn.execute("""
                SELECT dias_restantes, estado_alerta, fecha_vencimiento
                FROM alertas_vencimiento WHERE codigo = ?
            """, (codigo,)).fetchone()
            if alerta:
                doc["dias_restantes"] = alerta[0]
                doc["estado_alerta"] = alerta[1]
                doc["fecha_vencimiento"] = alerta[2]
        except Exception:
            pass

        return doc

    def buscar_documentos(self, query: str = "", top_k: int = 20) -> list[dict]:
        """Busca documentos por codigo o nombre. Para el visor de documentos."""
        if query:
            rows = self.conn.execute("""
                SELECT codigo, nombre, proceso_nom, tipo_documento, estado_desc
                FROM procedimientos
                WHERE codigo LIKE ? OR nombre LIKE ? OR proceso_nom LIKE ?
                ORDER BY codigo
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", top_k)).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT codigo, nombre, proceso_nom, tipo_documento, estado_desc
                FROM procedimientos
                ORDER BY codigo
                LIMIT ?
            """, (top_k,)).fetchall()

        return [
            {
                "codigo": r[0],
                "nombre": r[1],
                "proceso": r[2],
                "tipo_documento": r[3],
                "estado": r[4],
            }
            for r in rows
        ]

    def buscar_resumenes(self, query: str, top_k: int = 5) -> list[dict]:
        """Busca resúmenes por palabras clave."""
        rows = self.conn.execute("""
            SELECT r.codigo, r.resumen, r.palabras_clave, r.proposito, r.alcance,
                   p.nombre, p.proceso_nom, p.estado_desc
            FROM resumenes r
            JOIN procedimientos p ON r.codigo = p.codigo
            WHERE r.resumen LIKE ? OR r.palabras_clave LIKE ? OR p.nombre LIKE ?
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%", top_k * 2)).fetchall()

        resultados = []
        query_lower = query.lower()
        for r in rows:
            score = 0
            if query_lower in (r[1] or "").lower():
                score += 3
            if query_lower in (r[2] or "").lower():
                score += 2
            if query_lower in (r[5] or "").lower():
                score += 1
            resultados.append({
                "codigo": r[0],
                "resumen": r[1],
                "palabras_clave": r[2],
                "proposito": r[3],
                "alcance": r[4],
                "nombre": r[5],
                "proceso": r[6],
                "estado": r[7],
                "score": score,
            })
        resultados.sort(key=lambda x: -x["score"])
        return resultados[:top_k]

    # ──────────────────────────────────────────────
    # Tabla jerárquica
    # ──────────────────────────────────────────────

    def tabla_jerarquica(self, proceso: str = None) -> dict:
        """Devuelve la tabla de contenido jerárquica."""
        jerarquia_path = Path(__file__).parent.parent / "tabla_jerarquica.json"
        if not jerarquia_path.exists():
            return {"error": "Tabla jerárquica no generada. Ejecuta generar_resumenes.py"}

        data = json.loads(jerarquia_path.read_text(encoding="utf-8"))
        if proceso:
            # Filtrar por proceso
            proc_lower = proceso.lower()
            filtrado = {}
            for key, val in data.items():
                if proc_lower in (val.get("nombre") or "").lower() or proc_lower in key.lower():
                    filtrado[key] = val
            return filtrado
        return data

    # ──────────────────────────────────────────────
    # Alertas de vencimiento
    # ──────────────────────────────────────────────

    def alertas_vencimiento(self, solo_vencidos: bool = False) -> list[dict]:
        """Devuelve documentos vencidos o por vencer."""
        if solo_vencidos:
            rows = self.conn.execute("""
                SELECT codigo, nombre, proceso, fecha_publicacion, vigencia_dias,
                       fecha_vencimiento, dias_restantes, estado_alerta
                FROM alertas_vencimiento
                WHERE estado_alerta IN ('VENCIDO', 'POR_VENCER_30')
                ORDER BY dias_restantes
            """).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT codigo, nombre, proceso, fecha_publicacion, vigencia_dias,
                       fecha_vencimiento, dias_restantes, estado_alerta
                FROM alertas_vencimiento
                ORDER BY dias_restantes
            """).fetchall()

        return [
            {
                "codigo": r[0], "nombre": r[1], "proceso": r[2],
                "fecha_publicacion": r[3], "vigencia_dias": r[4],
                "fecha_vencimiento": r[5], "dias_restantes": r[6],
                "estado_alerta": r[7],
            }
            for r in rows
        ]

    # ──────────────────────────────────────────────
    # Glosario
    # ──────────────────────────────────────────────

    def buscar_glosario(self, query: str) -> list[dict]:
        """Busca términos del glosario relevantes a la consulta."""
        return buscar_termino(query)


# ──────────────────────────────────────────────
# CLI interactivo
# ──────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  AGENTE DE CALIDAD - INTEGRA")
    print("  Consultor: calidad, SOPs, NC, CAPA, auditorías")
    print("  Graph RAG: grafo + TF-IDF + embeddings")
    print("  LLM: OpenAI → Mistral → Ollama → Groq → Gemini (fallback)")
    print("=" * 60)

    rag = GraphRAG()

    print("\n  Comandos:")
    print("    /stats         - Estadísticas del grafo")
    print("    /temas         - Lista temas detectados")
    print("    /nodo <id>     - Explora un nodo del grafo")
    print("    /retrieve <q>  - Solo recuperación (sin LLM)")
    print("    /jerarquia     - Tabla jerárquica de procesos")
    print("    /jerarquia <p> - Tabla filtrada por proceso")
    print("    /vencidos      - Documentos vencidos/por vencer")
    print("    /resumen <cod> - Resumen ejecutivo de un documento")
    print("    /glosario <q>  - Buscar términos del glosario")
    print("    /finops        - Dashboard de costos y tokens")
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

        if user == "/stats":
            stats = rag.grafo_stats()
            print(f"\n  Grafo: {stats['nodos']} nodos, {stats['aristas']} aristas")
            print(f"  Documentos: {stats['documentos']}, Embeddings: {stats['embeddings']}")
            print(f"  Por tipo: {stats['por_tipo']}\n")
            continue

        if user == "/temas":
            rag.listar_temas()
            continue

        if user.startswith("/nodo "):
            nodo = user.split(" ", 1)[1]
            info = rag.explorar_nodo(nodo)
            print(json.dumps(info, ensure_ascii=False, indent=2))
            continue

        if user.startswith("/retrieve "):
            query = user.split(" ", 1)[1]
            resultados = rag.retrieve(query, top_k=5)
            print(f"\n  Resultados:")
            for i, r in enumerate(resultados):
                print(f"    {i+1}. {r['codigo']} (total={r['score_total']:.3f}) - {r['nombre'][:60]}")
                print(f"       sem={r['score_semantico']:.2f} lex={r['score_lexical']:.2f} grafo={r['score_grafo']:.2f}")
            continue

        if user == "/jerarquia":
            jerarquia = rag.tabla_jerarquica()
            if "error" in jerarquia:
                print(f"\n  {jerarquia['error']}")
            else:
                print(f"\n  Tabla jerárquica ({len(jerarquia)} procesos):")
                for key, val in sorted(jerarquia.items(), key=lambda x: -x[1]["total_docs"]):
                    print(f"    📁 {val['nombre']} ({val['total_docs']} docs)")
                    for tipo, tipo_data in sorted(val["tipos"].items(), key=lambda x: -x[1]["total"]):
                        print(f"       📄 {tipo} ({tipo_data['total']})")
            continue

        if user.startswith("/jerarquia "):
            proc = user.split(" ", 1)[1]
            jerarquia = rag.tabla_jerarquica(proceso=proc)
            if not jerarquia:
                print(f"\n  No se encontró el proceso '{proc}'")
            else:
                for key, val in jerarquia.items():
                    print(f"\n  📁 {val['nombre']} ({val['total_docs']} docs)")
                    for tipo, tipo_data in val["tipos"].items():
                        print(f"     📄 {tipo} ({tipo_data['total']})")
                        for doc in tipo_data["documentos"][:10]:
                            print(f"        {doc['codigo']} | {doc['estado_desc']} | {doc['nombre'][:50]}")
            continue

        if user == "/vencidos":
            alertas = rag.alertas_vencimiento(solo_vencidos=True)
            if not alertas:
                print("\n  No hay documentos vencidos ni por vencer. ✅")
            else:
                print(f"\n  Documentos vencidos/por vencer ({len(alertas)}):")
                for a in alertas[:20]:
                    icono = "🔴" if a["estado_alerta"] == "VENCIDO" else "🟡"
                    dias = a["dias_restantes"]
                    dias_str = f"vencido hace {abs(dias)} días" if dias < 0 else f"vence en {dias} días"
                    print(f"    {icono} {a['codigo']} | {dias_str} | {a['nombre'][:40]}")
            continue

        if user.startswith("/resumen "):
            codigo = user.split(" ", 1)[1].strip()
            resumen = rag.get_resumen(codigo)
            if not resumen:
                print(f"\n  No hay resumen para '{codigo}'. Ejecuta generar_resumenes.py primero.")
            else:
                print(f"\n  📋 Resumen ejecutivo: {codigo}")
                print(f"     Resumen: {resumen['resumen']}")
                print(f"     Propósito: {resumen['proposito']}")
                print(f"     Alcance: {resumen['alcance']}")
                print(f"     Palabras clave: {resumen['palabras_clave']}")
            continue

        if user.startswith("/glosario "):
            query = user.split(" ", 1)[1]
            terminos = rag.buscar_glosario(query)
            if not terminos:
                print(f"\n  No se encontraron términos del glosario para '{query}'")
            else:
                print(f"\n  📖 Glosario ({len(terminos)} términos):")
                for t in terminos:
                    print(f"    {t['termino']}")
                    print(f"      Categoría: {t['categoria']}")
                    print(f"      Definición: {t['definicion']}")
            continue

        if user == "/finops":
            rag.obs.print_dashboard()
            continue

        # Pregunta normal → Graph RAG
        try:
            answer, resultados = rag.ask(user)
            print(f"\nAgente: {answer}\n")
        except Exception as e:
            print(f"\n  Error: {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    main()
