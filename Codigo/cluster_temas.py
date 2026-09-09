"""
Paso 3: Agrupa los procedimientos por temas usando clustering (K-Means sobre
embeddings) + TF-IDF para extraer palabras clave de cada cluster.
Genera un grafo de relaciones entre temas y documentos.

Uso:
    python Codigo/cluster_temas.py
"""
import json
import math
import pickle
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"

# Número de temas a detectar
NUM_TEMAS = 15
TOP_PALABRAS = 10


def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def main():
    print("=" * 60)
    print("  AGRUPACIÓN POR TEMAS (CLUSTERING + TF-IDF)")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))

    # Cargar embeddings
    print("\n[1/5] Cargando embeddings...")
    rows = conn.execute("""
        SELECT e.codigo, e.embedding, p.nombre, p.proceso_nom, p.tipo_documento, p.contenido_texto
        FROM embeddings e
        JOIN procedimientos p ON e.codigo = p.codigo
    """).fetchall()

    if not rows:
        print("  ERROR: No hay embeddings. Ejecuta generate_embeddings.py primero.")
        conn.close()
        return

    print(f"  Documentos con embedding: {len(rows)}")

    codigos = [r[0] for r in rows]
    embeddings = np.array([pickle.loads(r[1]) for r in rows])
    nombres = [r[2] for r in rows]
    procesos = [r[3] for r in rows]
    tipos = [r[4] for r in rows]
    textos = [r[5] or "" for r in rows]

    # Clustering K-Means
    print(f"\n[2/5] Ejecutando K-Means (k={NUM_TEMAS})...")
    start = time.time()
    kmeans = KMeans(n_clusters=NUM_TEMAS, random_state=42, n_init=10, max_iter=300)
    labels = kmeans.fit_predict(embeddings)
    print(f"  Clustering completado en {fmt_time(time.time() - start)}")

    # TF-IDF para palabras clave por cluster
    print(f"\n[3/5] Extrayendo palabras clave con TF-IDF...")
    vectorizer = TfidfVectorizer(
        max_features=5000,
        stop_words=["el", "la", "los", "las", "de", "del", "y", "o", "a", "en",
                     "que", "es", "se", "para", "con", "por", "un", "una", "su",
                     "al", "lo", "como", "más", "menos", "si", "no", "este", "esta",
                     "the", "of", "and", "to", "in", "for", "is", "are", "with"],
        token_pattern=r"[a-záéíóúñ]{3,}",
        max_df=0.85,
        min_df=3,
    )
    tfidf_matrix = vectorizer.fit_transform(textos)
    feature_names = vectorizer.get_feature_names_out()

    # Para cada cluster, encontrar las palabras más representativas
    temas_info = []
    for cluster_id in range(NUM_TEMAS):
        mask = labels == cluster_id
        cluster_docs = np.where(mask)[0]
        n_docs = len(cluster_docs)

        if n_docs == 0:
            temas_info.append(("Tema vacío", "", 0, []))
            continue

        # Promediar TF-IDF del cluster
        cluster_tfidf = tfidf_matrix[cluster_docs].mean(axis=0).A1
        top_indices = cluster_tfidf.argsort()[-TOP_PALABRAS:][::-1]
        top_words = [feature_names[i] for i in top_indices if cluster_tfidf[i] > 0]

        # Nombre automático del tema: las 3 palabras principales
        tema_nombre = " / ".join(top_words[:3]).upper() if top_words else f"Tema {cluster_id}"

        # Procesos predominantes en el cluster
        procesos_cluster = [procesos[i] for i in cluster_docs if procesos[i]]
        proc_counter = Counter(procesos_cluster)
        proc_top = proc_counter.most_common(3)

        descripcion = f"{n_docs} docs"
        if proc_top:
            descripcion += " | Procesos: " + ", ".join(f"{p}({c})" for p, c in proc_top)

        temas_info.append((tema_nombre, descripcion, n_docs, top_words))

    # Guardar temas en SQLite
    print(f"\n[4/5] Guardando temas en SQLite...")
    conn.execute("DELETE FROM temas")
    conn.execute("DELETE FROM documento_tema")

    for cluster_id, (nombre, desc, n_docs, palabras) in enumerate(temas_info):
        conn.execute("""
            INSERT INTO temas (tema_id, nombre, descripcion, num_docs, palabras_clave)
            VALUES (?, ?, ?, ?, ?)
        """, (cluster_id, nombre, desc, n_docs, json.dumps(palabras, ensure_ascii=False)))

        # Guardar asignaciones de documentos a temas
        mask = labels == cluster_id
        cluster_docs = np.where(mask)[0]
        for idx in cluster_docs:
            # Similitud al centroide
            sim = cosine_similarity(
                embeddings[idx].reshape(1, -1),
                kmeans.cluster_centers_[cluster_id].reshape(1, -1)
            )[0][0]
            conn.execute("""
                INSERT OR REPLACE INTO documento_tema (codigo, tema_id, similitud)
                VALUES (?, ?, ?)
            """, (codigos[idx], cluster_id, float(sim)))

    conn.commit()

    # Grafo de similitud entre temas
    print(f"\n[5/5] Generando grafo de relaciones entre temas...")
    grafo_path = Path(__file__).parent.parent / "grafo_temas.json"
    centroides = kmeans.cluster_centers_
    sim_temas = cosine_similarity(centroides)

    nodos = []
    for cluster_id, (nombre, desc, n_docs, palabras) in enumerate(temas_info):
        nodos.append({
            "id": cluster_id,
            "nombre": nombre,
            "descripcion": desc,
            "num_docs": n_docs,
            "palabras_clave": palabras,
        })

    aristas = []
    for i in range(NUM_TEMAS):
        for j in range(i + 1, NUM_TEMAS):
            sim = float(sim_temas[i][j])
            if sim > 0.3:  # solo conexiones significativas
                aristas.append({
                    "source": i,
                    "target": j,
                    "similitud": sim,
                })

    grafo = {"nodos": nodos, "aristas": aristas}
    grafo_path.write_text(
        json.dumps(grafo, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Resumen
    print(f"\n{'=' * 60}")
    print(f"  TEMAS DETECTADOS")
    print(f"{'=' * 60}")

    for cluster_id, (nombre, desc, n_docs, palabras) in enumerate(temas_info):
        print(f"\n  Tema {cluster_id}: {nombre}")
        print(f"    {desc}")
        print(f"    Palabras clave: {', '.join(palabras)}")

    print(f"\n  Grafo guardado en: {grafo_path}")
    print(f"  Nodos: {len(nodos)} | Aristas: {len(aristas)}")

    conn.close()


if __name__ == "__main__":
    main()
