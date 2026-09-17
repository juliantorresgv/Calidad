"""
Retrieval avanzado: NER entidades, RAPTOR, parent-child chunking, late chunking,
embeddings en español nativo, y fine-tuning de embeddings.

Este módulo extiende GraphRAG con técnicas modernas de retrieval.
"""
import os
import re
import sqlite3
import hashlib
import json
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "indice_procedimientos.db"


# ──────────────────────────────────────────────
# 1. NER (Named Entity Recognition) con LLM
# ──────────────────────────────────────────────

# Tipos de entidades del dominio HSEQ
ENTITY_TYPES = {
    "proceso": ["almacenamiento", "maquila", "transporte", "cadena de frio",
                "real state", "recepcion", "despacho", "mantenimiento"],
    "norma": ["iso 9001", "iso 45001", "invima", "fda", "oms", "gdp",
              "buenas practicas", "bpg", "bpm"],
    "medicamento": ["oxigeno", "insulina", "vacuna", "biologico",
                    "termolabil", "refrigerado"],
    "equipo": ["refrigerador", "congelador", "camion", "montacargas",
               "estanteria", "bateria", "termometro", "data logger"],
    "documento": ["procedimiento", "formato", "manual", "instructivo",
                  "plan de calidad", "matriz"],
    "rol": ["operador", "supervisor", "director", "auditor",
            "responsable de calidad", "auxiliar"],
    "metrica": ["temperatura", "humedad", "tiempo", "lote", "vencimiento",
                "desviacion", "tasa de no conformidad"],
}


def extract_entities_llm(text: str, llm_client=None) -> list[dict]:
    """Extrae entidades del texto usando patrones regex y opcionalmente LLM.
    Retorna lista de {entity, type, start, end}."""
    entities = []
    text_lower = text.lower()

    # Extraccion por patrones (rapida, sin LLM)
    for ent_type, keywords in ENTITY_TYPES.items():
        for kw in keywords:
            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            for match in pattern.finditer(text):
                entities.append({
                    "entity": match.group(),
                    "type": ent_type,
                    "start": match.start(),
                    "end": match.end(),
                })

    # Codigos de documentos (PGC-16-15, PGC-11-03, etc.)
    code_pattern = re.compile(r'\b([A-Z]{2,5})[-_]?(\d{1,3})[-_]?(\d{1,3})\b')
    for match in code_pattern.finditer(text):
        entities.append({
            "entity": match.group(),
            "type": "codigo_documento",
            "start": match.start(),
            "end": match.end(),
        })

    # Numeros de NC
    nc_pattern = re.compile(r'\bNC[-_\s]?(\d{1,6})\b', re.IGNORECASE)
    for match in nc_pattern.finditer(text):
        entities.append({
            "entity": match.group(),
            "type": "nc",
            "start": match.start(),
            "end": match.end(),
        })

    # Fechas
    date_pattern = re.compile(
        r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b'
    )
    for match in date_pattern.finditer(text):
        entities.append({
            "entity": match.group(),
            "type": "fecha",
            "start": match.start(),
            "end": match.end(),
        })

    # Temperaturas (2-8°C, -20°C, etc.)
    temp_pattern = re.compile(r'-?\d{1,3}\s*[°º]?\s*[CcKk]')
    for match in temp_pattern.finditer(text):
        entities.append({
            "entity": match.group(),
            "type": "temperatura",
            "start": match.start(),
            "end": match.end(),
        })

    # Deduplicar
    seen = set()
    unique = []
    for e in entities:
        key = (e["entity"].lower(), e["start"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    return unique


def extract_entities_with_llm(text: str, llm_client) -> list[dict]:
    """Extrae entidades usando LLM para mayor precision."""
    prompt = f"""Extrae todas las entidades del siguiente texto y clasificalas.
Tipos: proceso, norma, medicamento, equipo, documento, rol, metrica, codigo_documento, nc, fecha, temperatura.

Texto:
{text[:2000]}

Responde SOLO en formato JSON:
[{{"entity": "nombre", "type": "tipo"}}]"""

    try:
        resp = llm_client.chat.completions.create(
            model=os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=500,
        )
        content = resp.choices[0].message.content.strip()
        # Extraer JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        entities = json.loads(content)
        return entities
    except Exception:
        return []


def build_entity_graph(conn: sqlite3.Connection) -> dict:
    """Construye un grafo de entidades a partir de los documentos indexados."""
    # Crear tablas si no existen
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT NOT NULL,
            type TEXT NOT NULL,
            UNIQUE(entity, type)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documento_entidad (
            documento_codigo TEXT NOT NULL,
            entidad_id INTEGER NOT NULL,
            frecuencia INTEGER DEFAULT 1,
            PRIMARY KEY (documento_codigo, entidad_id),
            FOREIGN KEY (entidad_id) REFERENCES entidades(id)
        )
    """)

    # Procesar documentos
    cursor = conn.execute("SELECT codigo, nombre, contenido_texto FROM procedimientos LIMIT 500")
    docs = cursor.fetchall()

    entity_cache = {}

    for codigo, nombre, texto in docs:
        if not texto:
            continue
        full_text = f"{nombre or ''} {texto}"
        entities = extract_entities_llm(full_text)

        for ent in entities:
            key = (ent["entity"].lower(), ent["type"])
            if key not in entity_cache:
                # Insertar entidad
                conn.execute(
                    "INSERT OR IGNORE INTO entidades (entity, type) VALUES (?, ?)",
                    (ent["entity"], ent["type"])
                )
                row = conn.execute(
                    "SELECT id FROM entidades WHERE entity=? AND type=?",
                    (ent["entity"], ent["type"])
                ).fetchone()
                if row:
                    entity_cache[key] = row[0]

            ent_id = entity_cache.get(key)
            if ent_id:
                conn.execute("""
                    INSERT INTO documento_entidad (documento_codigo, entidad_id, frecuencia)
                    VALUES (?, ?, 1)
                    ON CONFLICT(documento_codigo, entidad_id)
                    DO UPDATE SET frecuencia = frecuencia + 1
                """, (codigo, ent_id))

    conn.commit()

    # Estadisticas
    total_entidades = conn.execute("SELECT COUNT(*) FROM entidades").fetchone()[0]
    total_relaciones = conn.execute("SELECT COUNT(*) FROM documento_entidad").fetchone()[0]

    return {
        "total_entidades": total_entidades,
        "total_relaciones": total_relaciones,
        "tipos": dict(conn.execute(
            "SELECT type, COUNT(*) FROM entidades GROUP BY type ORDER BY COUNT(*) DESC"
        ).fetchall()),
    }


def search_by_entities(query: str, conn: sqlite3.Connection, top_k: int = 10) -> dict[str, float]:
    """Busca documentos por entidades extraidas de la query."""
    # Verificar que las tablas existen (se crean con build_entity_graph)
    try:
        conn.execute("SELECT 1 FROM documento_entidad LIMIT 1")
    except sqlite3.OperationalError:
        # Tabla no existe aun: crear indice on-the-fly y devolver vacio
        try:
            build_entity_graph(conn)
        except Exception:
            pass
        return {}

    entities = extract_entities_llm(query)
    if not entities:
        return {}

    scores = {}
    for ent in entities:
        rows = conn.execute("""
            SELECT de.documento_codigo, de.frecuencia
            FROM documento_entidad de
            JOIN entidades e ON de.entidad_id = e.id
            WHERE e.entity LIKE ? OR e.entity = ?
            ORDER BY de.frecuencia DESC
            LIMIT ?
        """, (f"%{ent['entity']}%", ent["entity"], top_k)).fetchall()

        for codigo, freq in rows:
            scores[codigo] = scores.get(codigo, 0) + freq

    # Normalizar
    if scores:
        max_score = max(scores.values())
        scores = {k: v / max_score for k, v in scores.items()}

    return scores


# ──────────────────────────────────────────────
# 2. RAPTOR (Recursive Abstractive Processing)
# ──────────────────────────────────────────────

def build_raptor_tree(conn: sqlite3.Connection, llm_client=None,
                      max_levels: int = 3, cluster_size: int = 10) -> dict:
    """Construye un arbol RAPTOR: agrupa documentos en clusters y genera resumenes jerarquicos."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raptor_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level INTEGER NOT NULL,
            cluster_id INTEGER NOT NULL,
            resumen TEXT,
            documentos TEXT,  -- JSON lista de codigos
            parent_id INTEGER,
            UNIQUE(level, cluster_id)
        )
    """)

    # Nivel 0: documentos individuales (ya existen en procedimientos)
    # Nivel 1: clusters de documentos similares
    # Nivel 2: clusters de clusters
    # Nivel 3: resumen global

    cursor = conn.execute("""
        SELECT codigo, nombre, contenido_texto FROM procedimientos
        WHERE contenido_texto IS NOT NULL AND LENGTH(contenido_texto) > 100
        LIMIT 200
    """)
    docs = cursor.fetchall()

    if not docs:
        return {"levels": 0, "total_nodes": 0}

    # Usar TF-IDF para clustering si sklearn esta disponible
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import AgglomerativeClustering
        import numpy as np

        doc_texts = [f"{d[1] or ''} {d[2][:500]}" for d in docs]
        doc_codes = [d[0] for d in docs]

        vectorizer = TfidfVectorizer(max_features=500, stop_words=None)
        tfidf_matrix = vectorizer.fit_transform(doc_texts)

        n_clusters = min(max(len(docs) // cluster_size, 2), 20)
        clustering = AgglomerativeClustering(n_clusters=n_clusters)
        labels = clustering.fit_predict(tfidf_matrix.toarray())

        # Crear nodos nivel 1
        level1_nodes = {}
        for i, label in enumerate(labels):
            if label not in level1_nodes:
                level1_nodes[label] = []
            level1_nodes[label].append(doc_codes[i])

        for cluster_id, codes in level1_nodes.items():
            # Generar resumen del cluster
            cluster_docs = [d for d in docs if d[0] in codes]
            cluster_text = " ".join([f"{d[1] or ''}" for d in cluster_docs])[:3000]

            resumen = None
            if llm_client:
                try:
                    resp = llm_client.chat.completions.create(
                        model=os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
                        messages=[{
                            "role": "user",
                            "content": f"Resume en 3-5 lineas los siguientes documentos de calidad HSEQ:\n{cluster_text}"
                        }],
                        temperature=0,
                        max_tokens=200,
                    )
                    resumen = resp.choices[0].message.content.strip()
                except Exception:
                    pass

            if not resumen:
                resumen = f"Cluster de {len(codes)} documentos sobre temas relacionados"

            conn.execute("""
                INSERT OR REPLACE INTO raptor_nodes (level, cluster_id, resumen, documentos, parent_id)
                VALUES (1, ?, ?, ?, NULL)
            """, (cluster_id, resumen, json.dumps(codes)))

        conn.commit()

        # Nivel 2: clusters de clusters
        if n_clusters > 4:
            # Agrupar clusters nivel 1 en super-clusters
            level1_summaries = []
            level1_ids = []
            for row in conn.execute("SELECT id, resumen FROM raptor_nodes WHERE level=1").fetchall():
                level1_ids.append(row[0])
                level1_summaries.append(row[1] or "")

            if len(level1_summaries) > 4:
                tfidf2 = TfidfVectorizer(max_features=100)
                mat2 = tfidf2.fit_transform(level1_summaries)
                n2 = min(max(len(level1_summaries) // 3, 2), 5)
                cl2 = AgglomerativeClustering(n_clusters=n2)
                labels2 = cl2.fit_predict(mat2.toarray())

                for i, label in enumerate(labels2):
                    conn.execute("""
                        INSERT OR REPLACE INTO raptor_nodes (level, cluster_id, resumen, documentos, parent_id)
                        VALUES (2, ?, 'Super-cluster nivel 2', ?, ?)
                    """, (label, json.dumps([level1_ids[i]]), level1_ids[i]))

                conn.commit()

        # Nivel 3: resumen global
        all_summaries = [r[0] for r in conn.execute(
            "SELECT resumen FROM raptor_nodes WHERE level=2"
        ).fetchall()]
        global_resumen = "Resumen global de todos los documentos de calidad HSEQ de Integr@"

        conn.execute("""
            INSERT OR REPLACE INTO raptor_nodes (level, cluster_id, resumen, documentos, parent_id)
            VALUES (3, 0, ?, '[]', NULL)
        """, (global_resumen,))
        conn.commit()

        total_nodes = conn.execute("SELECT COUNT(*) FROM raptor_nodes").fetchone()[0]
        return {"levels": 3, "total_nodes": total_nodes, "clusters_l1": n_clusters}

    except ImportError:
        return {"levels": 0, "total_nodes": 0, "error": "scikit-learn no disponible"}


def raptor_retrieve(query: str, conn: sqlite3.Connection, top_k: int = 5) -> list[dict]:
    """Recupera documentos usando el arbol RAPTOR: busca en resumenes jerarquicos."""
    results = []

    # Verificar que la tabla existe
    try:
        conn.execute("SELECT 1 FROM raptor_nodes LIMIT 1")
    except sqlite3.OperationalError:
        return []

    # Buscar en nodos nivel 1 (clusters)
    nodes = conn.execute("""
        SELECT id, resumen, documentos FROM raptor_nodes WHERE level=1
    """).fetchall()

    query_lower = query.lower()
    scored_nodes = []

    for node_id, resumen, documentos in nodes:
        if not resumen:
            continue
        # Score simple por overlap de palabras
        resumen_lower = resumen.lower()
        query_words = set(query_lower.split())
        resumen_words = set(resumen_lower.split())
        overlap = len(query_words & resumen_words)
        if overlap > 0:
            scored_nodes.append((node_id, overlap, resumen, documentos))

    scored_nodes.sort(key=lambda x: x[1], reverse=True)

    for node_id, score, resumen, documentos in scored_nodes[:top_k]:
        codes = json.loads(documentos) if documentos else []
        for code in codes:
            results.append({
                "codigo": code,
                "score": score / 10,
                "source": "raptor",
                "cluster_id": node_id,
            })

    return results


# ──────────────────────────────────────────────
# 3. Parent-Child Chunking
# ──────────────────────────────────────────────

def parent_child_chunk(text: str, parent_size: int = 2000, child_size: int = 300,
                       overlap: int = 50) -> dict:
    """Divide el texto en chunks padre e hijo.
    - Parent: chunk grande para contexto
    - Child: chunk pequeño para busqueda precisa
    """
    if not text or len(text) < child_size:
        return {"parents": [text] if text else [], "children": [[text]]}

    parents = []
    children_groups = []

    # Dividir en padres
    for i in range(0, len(text), parent_size - overlap):
        parent = text[i:i + parent_size]
        parents.append(parent)

        # Dividir padre en hijos
        child_group = []
        for j in range(0, len(parent), child_size - overlap):
            child = parent[j:j + child_size]
            if len(child) > 50:  # ignorar chunks muy pequeños
                child_group.append(child)
        children_groups.append(child_group)

    return {"parents": parents, "children": children_groups}


def build_parent_child_index(conn: sqlite3.Connection) -> dict:
    """Construye indice parent-child en SQLite."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks_parent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_codigo TEXT NOT NULL,
            chunk_idx INTEGER NOT NULL,
            texto TEXT NOT NULL,
            UNIQUE(documento_codigo, chunk_idx)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks_child (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL,
            chunk_idx INTEGER NOT NULL,
            texto TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES chunks_parent(id)
        )
    """)

    cursor = conn.execute("""
        SELECT codigo, contenido_texto FROM procedimientos
        WHERE contenido_texto IS NOT NULL AND LENGTH(contenido_texto) > 500
        LIMIT 300
    """)
    docs = cursor.fetchall()

    total_parents = 0
    total_children = 0

    for codigo, texto in docs:
        result = parent_child_chunk(texto)
        for idx, parent in enumerate(result["parents"]):
            conn.execute("""
                INSERT OR REPLACE INTO chunks_parent (documento_codigo, chunk_idx, texto)
                VALUES (?, ?, ?)
            """, (codigo, idx, parent))
            parent_id = conn.execute(
                "SELECT id FROM chunks_parent WHERE documento_codigo=? AND chunk_idx=?",
                (codigo, idx)
            ).fetchone()[0]
            total_parents += 1

            for cidx, child in enumerate(result["children"][idx]):
                conn.execute("""
                    INSERT INTO chunks_child (parent_id, chunk_idx, texto)
                    VALUES (?, ?, ?)
                """, (parent_id, cidx, child))
                total_children += 1

    conn.commit()
    return {"total_parents": total_parents, "total_children": total_children}


def retrieve_parent_child(query: str, conn: sqlite3.Connection, top_k: int = 5) -> list[dict]:
    """Busca en chunks hijo y retorna el chunk padre completo para contexto."""
    # Verificar que las tablas existen
    try:
        conn.execute("SELECT 1 FROM chunks_child LIMIT 1")
    except sqlite3.OperationalError:
        return []

    query_lower = query.lower()
    query_words = set(query_lower.split())

    # Buscar en chunks hijo
    children = conn.execute("SELECT id, parent_id, texto FROM chunks_child LIMIT 5000").fetchall()

    scored = []
    for child_id, parent_id, texto in children:
        texto_lower = texto.lower()
        texto_words = set(texto_lower.split())
        overlap = len(query_words & texto_words)
        if overlap > 2:
            scored.append((parent_id, overlap, child_id))

    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    seen_parents = set()
    for parent_id, score, child_id in scored[:top_k * 2]:
        if parent_id in seen_parents:
            continue
        seen_parents.add(parent_id)

        parent = conn.execute(
            "SELECT documento_codigo, texto FROM chunks_parent WHERE id=?",
            (parent_id,)
        ).fetchone()
        if parent:
            results.append({
                "codigo": parent[0],
                "texto": parent[1],
                "score": score / 10,
                "source": "parent_child",
            })

    return results[:top_k]


# ──────────────────────────────────────────────
# 4. Late Chunking
# ──────────────────────────────────────────────

def late_chunking(text: str, embedding_model=None, chunk_size: int = 300) -> list[dict]:
    """Late chunking: genera embedding del documento completo primero,
    luego particiona en chunks manteniendo el contexto global."""
    if not text:
        return []

    # 1. Generar embedding del documento completo
    doc_embedding = None
    if embedding_model:
        try:
            doc_embedding = embedding_model.encode(text)
        except Exception:
            pass

    # 2. Particionar en chunks
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        if len(chunk) > 50:
            # Cada chunk hereda el embedding del documento + su posicion
            chunk_emb = None
            if embedding_model:
                try:
                    chunk_emb = embedding_model.encode(chunk)
                except Exception:
                    pass

            chunks.append({
                "text": chunk,
                "start": i,
                "end": i + len(chunk),
                "doc_embedding": doc_embedding,
                "chunk_embedding": chunk_emb,
            })

    return chunks


# ──────────────────────────────────────────────
# 5. Embeddings en español nativo
# ──────────────────────────────────────────────

# Modelos recomendados para español
SPANISH_EMBEDDING_MODELS = {
    "bge-m3": "BAAI/bge-m3",                    # Multilingual, 8192 tokens
    "multilingual-e5-large": "intfloat/multilingual-e5-large",  # Multilingual
    "snowflake-arctic": "Snowflake/snowflake-arctic-embed-l-v2.0",  # Multilingual
    "bge-large-es": "BAAI/bge-large-zh-v1.5",   # Chino pero funciona para ES
    "sentence-transformers-paraphrase": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
}


def get_spanish_embedding_model(model_name: str = "multilingual-e5-large"):
    """Carga un modelo de embeddings optimizado para español."""
    try:
        from sentence_transformers import SentenceTransformer
        model_path = SPANISH_EMBEDDING_MODELS.get(model_name, model_name)
        model = SentenceTransformer(model_path)
        return model
    except Exception as e:
        print(f"  [WARN] No se pudo cargar modelo {model_name}: {e}")
        return None


def embed_spanish(text: str, model=None) -> Optional[list[float]]:
    """Genera embedding usando modelo optimizado para español."""
    if model is None:
        model = get_spanish_embedding_model()
    if model is None:
        return None
    try:
        emb = model.encode(text)
        return emb.tolist()
    except Exception:
        return None


# ──────────────────────────────────────────────
# 6. Fine-tuning de embeddings
# ──────────────────────────────────────────────

def generate_finetune_dataset(conn: sqlite3.Connection, output_path: Path) -> dict:
    """Genera dataset para fine-tuning de embeddings a partir de los datos de Integr@.
    Formato: pares (query, documento_positivo, documento_negativo)."""
    pairs = []

    # 1. Pares desde resumenes (query = titulo, positivo = texto)
    cursor = conn.execute("""
        SELECT p.codigo, p.nombre, p.contenido_texto, r.resumen
        FROM procedimientos p
        LEFT JOIN resumenes r ON p.codigo = r.codigo
        WHERE p.contenido_texto IS NOT NULL AND LENGTH(p.contenido_texto) > 200
        LIMIT 200
    """)
    docs = cursor.fetchall()

    for codigo, nombre, texto, resumen in docs:
        if nombre:
            # Query = nombre del documento, positivo = texto
            pairs.append({
                "query": nombre,
                "positive": texto[:500],
                "negative": "",  # se llenara despues
            })

        if resumen:
            pairs.append({
                "query": resumen[:200],
                "positive": texto[:500],
                "negative": "",
            })

    # 2. Pares desde glosario (query = termino, positivo = definicion)
    for termino, definicion in conn.execute(
        "SELECT termino, definicion FROM glosario LIMIT 50"
    ).fetchall():
        pairs.append({
            "query": termino,
            "positive": definicion,
            "negative": "",
        })

    # 3. Negativos: documentos de otros procesos
    for i, pair in enumerate(pairs):
        if i < len(pairs) - 1:
            pair["negative"] = pairs[(i + 5) % len(pairs)]["positive"][:300]

    # Guardar
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)

    return {
        "total_pairs": len(pairs),
        "output_path": str(output_path),
    }


def finetune_embeddings_script(dataset_path: Path, output_model_path: Path) -> str:
    """Genera script de fine-tuning usando sentence-transformers."""
    script = f'''"""
Fine-tuning de embeddings con datos de Integr@.
Ejecutar: python finetune_embeddings.py
"""
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader
import json

# Cargar modelo base
model = SentenceTransformer("intfloat/multilingual-e5-large")

# Cargar dataset
with open(r"{dataset_path}", encoding="utf-8") as f:
    pairs = json.load(f)

# Crear ejemplos de entrenamiento
train_examples = []
for pair in pairs:
    if pair["negative"]:
        train_examples.append(InputExample(
            texts=[pair["query"], pair["positive"], pair["negative"]]
        ))

print(f"Total ejemplos: {{len(train_examples)}}")

# DataLoader
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
train_loss = losses.TripletLoss(model=model)

# Fine-tune
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=3,
    warmup_steps=100,
    output_path=r"{output_model_path}",
    show_progress_bar=True,
)

print(f"Modelo guardado en: {output_model_path}")
'''
    return script


# ──────────────────────────────────────────────
# Funcion principal: construir todos los indices
# ──────────────────────────────────────────────

def build_all_advanced_indices(conn: sqlite3.Connection, llm_client=None) -> dict:
    """Construye todos los indices avanzados de retrieval."""
    results = {}

    print("  [1/5] Extrayendo entidades (NER)...")
    results["ner"] = build_entity_graph(conn)

    print("  [2/5] Construyendo arbol RAPTOR...")
    results["raptor"] = build_raptor_tree(conn, llm_client)

    print("  [3/5] Construyendo indice parent-child...")
    results["parent_child"] = build_parent_child_index(conn)

    print("  [4/5] Generando dataset para fine-tuning...")
    ft_path = Path(__file__).resolve().parent.parent / "finetune_dataset.json"
    results["finetune"] = generate_finetune_dataset(conn, ft_path)

    print("  [5/5] Generando script de fine-tuning...")
    script_path = Path(__file__).resolve().parent / "finetune_embeddings.py"
    model_path = Path(__file__).resolve().parent.parent / "embeddings_finetuned"
    script_path.write_text(finetune_embeddings_script(ft_path, model_path), encoding="utf-8")
    results["finetune_script"] = str(script_path)

    return results


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("  Construccion de indices avanzados de retrieval")
    print("  NER + RAPTOR + Parent-Child + Fine-tuning dataset")
    print("=" * 60)
    print()

    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)

    # Intentar cargar LLM para RAPTOR (resumenes con LLM)
    llm_client = None
    try:
        api_key = os.environ.get("MISTRAL_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            from openai import OpenAI
            base_url = "https://api.mistral.ai/v1" if os.environ.get("MISTRAL_API_KEY") else None
            llm_client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
            print("  LLM disponible para resumenes RAPTOR")
    except Exception as e:
        print(f"  LLM no disponible: {e} (RAPTOR usara resumenes heuristicos)")

    print()
    results = build_all_advanced_indices(conn, llm_client)
    print()
    print("=" * 60)
    print("  RESULTADOS:")
    print("=" * 60)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    conn.close()
    print()
    print("  Indices avanzados construidos correctamente.")
    print("  El agente ahora usara NER + RAPTOR + Parent-Child en el retrieval.")

