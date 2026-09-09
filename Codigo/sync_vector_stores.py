"""
Sincronizacion de almacenes vectoriales: SQLite ↔ ChromaDB ↔ FAISS.

Diagnostica y repara discrepancias entre los 3 almacenes de embeddings:
- SQLite: respaldo principal (embeddings serializados con pickle)
- ChromaDB: store vectorial con metadata
- FAISS: indice ultra-rapido para busqueda

Uso:
    python sync_vector_stores.py           # diagnostico + reparacion
    python sync_vector_stores.py --dry-run # solo diagnostico, no reparar
    python sync_vector_stores.py --rebuild-faiss  # forzar rebuild FAISS
"""
import json
import os
import pickle
import sqlite3
import sys
import time
from pathlib import Path

import faiss
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"
CHROMA_PATH = Path(__file__).parent.parent / "chroma_db"
FAISS_PATH = Path(__file__).parent.parent / "faiss_index.bin"
FAISS_META_PATH = FAISS_PATH.with_suffix(".meta.json")
EMBED_DIM = 1024


def load_sqlite_embeddings(conn) -> dict[str, np.ndarray]:
    """Carga todos los embeddings desde SQLite."""
    rows = conn.execute("SELECT codigo, embedding FROM embeddings").fetchall()
    embeddings = {}
    for codigo, emb_blob in rows:
        try:
            emb = pickle.loads(emb_blob)
            embeddings[codigo] = np.array(emb)
        except Exception as e:
            print(f"  ⚠ Error deserializando {codigo}: {e}")
    return embeddings


def load_chroma_ids() -> set[str]:
    """Carga los IDs almacenados en ChromaDB."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        collection = client.get_or_create_collection("procedimientos")
        if collection.count() == 0:
            return set()
        return set(collection.get()["ids"])
    except Exception as e:
        print(f"  ⚠ Error cargando ChromaDB: {e}")
        return set()


def load_faiss_index() -> tuple[faiss.Index | None, list[str]]:
    """Carga el indice FAISS y su mapeo de codigos."""
    if not FAISS_PATH.exists():
        return None, []
    try:
        index = faiss.read_index(str(FAISS_PATH))
        codigos = []
        if FAISS_META_PATH.exists():
            codigos = json.loads(FAISS_META_PATH.read_text(encoding="utf-8"))
        return index, codigos
    except Exception as e:
        print(f"  ⚠ Error cargando FAISS: {e}")
        return None, []


def rebuild_faiss_from_embeddings(embeddings: dict[str, np.ndarray]) -> tuple[faiss.Index, list[str]]:
    """Reconstruye el indice FAISS desde cero con todos los embeddings."""
    index = faiss.IndexFlatIP(EMBED_DIM)
    codigos = []

    # Ordenar codigos para reproducibilidad
    sorted_codigos = sorted(embeddings.keys())

    vectors = []
    for codigo in sorted_codigos:
        emb = embeddings[codigo]
        vec = emb.reshape(1, -1).astype(np.float32)
        vectors.append(vec)
        codigos.append(codigo)

    if vectors:
        all_vecs = np.vstack(vectors).astype(np.float32)
        faiss.normalize_L2(all_vecs)
        index.add(all_vecs)

    return index, codigos


def save_faiss(index: faiss.Index, codigos: list[str]):
    """Guarda el indice FAISS y su mapeo de codigos."""
    faiss.write_index(index, str(FAISS_PATH))
    FAISS_META_PATH.write_text(json.dumps(codigos), encoding="utf-8")


def sync_chroma_from_embeddings(conn, embeddings: dict[str, np.ndarray], missing_ids: set[str]):
    """Sincroniza ChromaDB con los embeddings que faltan."""
    if not missing_ids:
        return 0

    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_or_create_collection("procedimientos")

    synced = 0
    batch_size = 100

    missing_list = sorted(missing_ids)
    for i in range(0, len(missing_list), batch_size):
        batch = missing_list[i:i + batch_size]
        placeholders = ",".join(["?"] * len(batch))

        rows = conn.execute(f"""
            SELECT p.codigo, p.nombre, p.estado, p.estado_desc, p.proceso_cod,
                   p.proceso_nom, p.tipo_documento, p.fecha_publicacion,
                   p.elaborador, p.contenido_texto
            FROM procedimientos p
            WHERE p.codigo IN ({placeholders})
        """, batch).fetchall()

        if not rows:
            continue

        ids = []
        embs = []
        docs = []
        metas = []

        for row in rows:
            codigo = row[0]
            if codigo not in embeddings:
                continue
            emb = embeddings[codigo]
            ids.append(codigo)
            embs.append(emb.tolist() if isinstance(emb, np.ndarray) else emb)
            docs.append((row[9] or "")[:4000])
            metas.append({
                "nombre": (row[1] or "")[:200],
                "estado": row[2] or "",
                "estado_desc": row[3] or "",
                "proceso_cod": row[4] or "",
                "proceso_nom": (row[5] or "")[:100],
                "tipo_documento": row[6] or "",
                "fecha_publicacion": row[7] or "",
                "elaborador": (row[8] or "")[:100],
            })

        if ids:
            collection.upsert(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
            synced += len(ids)
            print(f"    ChromaDB: {synced}/{len(missing_list)} sincronizados...", end="\r")

    print()
    return synced


def verify_embedding_dimensions(embeddings: dict[str, np.ndarray]) -> dict:
    """Verifica que todos los embeddings tengan la dimension correcta."""
    correct = 0
    incorrect = {}
    for codigo, emb in embeddings.items():
        if emb.shape[-1] != EMBED_DIM:
            incorrect[codigo] = emb.shape
        else:
            correct += 1
    return {"correct": correct, "incorrect": incorrect}


def verify_no_duplicates(codigos: list[str]) -> list[str]:
    """Detecta codigos duplicados en una lista."""
    seen = set()
    duplicates = []
    for c in codigos:
        if c in seen:
            duplicates.append(c)
        else:
            seen.add(c)
    return duplicates


def main():
    dry_run = "--dry-run" in sys.argv
    force_rebuild = "--rebuild-faiss" in sys.argv

    print("=" * 60)
    print("  SINCRONIZACION DE ALMACENES VECTORIALES")
    print("  SQLite ↔ ChromaDB ↔ FAISS")
    print("=" * 60)

    if dry_run:
        print("  MODO: dry-run (solo diagnostico, no reparar)")
    if force_rebuild:
        print("  MODO: rebuild FAISS forzado")

    # ── 1. Cargar datos de los 3 almacenes ──
    print("\n[1/5] Cargando almacenes...")

    conn = sqlite3.connect(str(DB_PATH))

    # SQLite
    print("  Cargando SQLite...", end=" ")
    sqlite_embeddings = load_sqlite_embeddings(conn)
    sqlite_ids = set(sqlite_embeddings.keys())
    print(f"{len(sqlite_ids)} embeddings")

    # ChromaDB
    print("  Cargando ChromaDB...", end=" ")
    chroma_ids = load_chroma_ids()
    print(f"{len(chroma_ids)} documentos")

    # FAISS
    print("  Cargando FAISS...", end=" ")
    faiss_index, faiss_codigos = load_faiss_index()
    faiss_count = faiss_index.ntotal if faiss_index else 0
    print(f"{faiss_count} vectores")

    # Documentos totales en DB
    total_docs = conn.execute(
        "SELECT COUNT(*) FROM procedimientos WHERE texto_length > 100"
    ).fetchone()[0]
    print(f"\n  Documentos con texto en DB: {total_docs}")

    # ── 2. Diagnostico ──
    print("\n[2/5] Diagnostico de discrepancias...")

    issues = []

    # Verificar dimensiones de embeddings
    dim_check = verify_embedding_dimensions(sqlite_embeddings)
    if dim_check["incorrect"]:
        issues.append(f"CRITICO: {len(dim_check['incorrect'])} embeddings con dimension incorrecta")
        for codigo, shape in list(dim_check["incorrect"].items())[:5]:
            print(f"    {codigo}: shape={shape} (esperado {EMBED_DIM})")

    # Verificar duplicados en FAISS
    faiss_duplicates = verify_no_duplicates(faiss_codigos)
    if faiss_duplicates:
        issues.append(f"FAISS tiene {len(faiss_duplicates)} codigos duplicados")

    # Comparar almacenes
    print(f"\n  Tabla de cobertura:")
    print(f"  {'Almacen':<15} {'Total':>8} {'vs SQLite':>12}")
    print(f"  {'-'*35}")
    print(f"  {'SQLite':<15} {len(sqlite_ids):>8} {'(base)':>12}")
    print(f"  {'ChromaDB':<15} {len(chroma_ids):>8} {len(chroma_ids - sqlite_ids):>+12} extra")
    print(f"  {'FAISS':<15} {faiss_count:>8} {faiss_count - len(sqlite_ids):>+12} diff")

    # Faltantes
    chroma_missing = sqlite_ids - chroma_ids
    faiss_missing = sqlite_ids - set(faiss_codigos)
    sqlite_missing_from_chroma = chroma_ids - sqlite_ids  # en Chroma pero no en SQLite

    if chroma_missing:
        issues.append(f"ChromaDB falta {len(chroma_missing)} embeddings (existentes en SQLite)")
    if faiss_missing:
        issues.append(f"FAISS falta {len(faiss_missing)} vectores (existentes en SQLite)")
    if sqlite_missing_from_chroma:
        issues.append(f"ChromaDB tiene {len(sqlite_missing_from_chroma)} IDs no presentes en SQLite (posible orphan)")
    if faiss_count != len(faiss_codigos):
        issues.append(f"FAISS: indice tiene {faiss_count} vectores pero meta tiene {len(faiss_codigos)} codigos")

    if not issues:
        print("\n  ✅ No se detectaron discrepancias. Los 3 almacenes estan sincronizados.")
        conn.close()
        return

    print(f"\n  ⚠ Se detectaron {len(issues)} problemas:")
    for issue in issues:
        print(f"    • {issue}")

    if dry_run:
        print("\n  Modo dry-run: no se aplicaron correcciones.")
        conn.close()
        return

    # ── 3. Reparar ChromaDB ──
    print("\n[3/5] Sincronizando ChromaDB...")
    if chroma_missing:
        print(f"  Faltan {len(chroma_missing)} documentos en ChromaDB")
        synced = sync_chroma_from_embeddings(conn, sqlite_embeddings, chroma_missing)
        print(f"  ✅ {synced} documentos sincronizados en ChromaDB")
    else:
        print("  ✅ ChromaDB esta completo")

    # ── 4. Reconstruir FAISS ──
    print("\n[4/5] Reconstruyendo FAISS...")
    if force_rebuild or faiss_missing or faiss_duplicates or faiss_count != len(faiss_codigos):
        print(f"  Reconstruyendo desde SQLite ({len(sqlite_embeddings)} embeddings)...")
        t0 = time.time()
        new_index, new_codigos = rebuild_faiss_from_embeddings(sqlite_embeddings)
        save_faiss(new_index, new_codigos)
        elapsed = time.time() - t0
        print(f"  ✅ FAISS reconstruido: {new_index.ntotal} vectores en {elapsed:.1f}s")

        # Verificar
        if new_index.ntotal != len(sqlite_embeddings):
            print(f"  ⚠ AUN hay discrepancia: FAISS={new_index.ntotal} vs SQLite={len(sqlite_embeddings)}")
    else:
        print("  ✅ FAISS esta completo")

    # ── 5. Verificacion final ──
    print("\n[5/5] Verificacion final...")

    # Recargar
    chroma_ids_final = load_chroma_ids()
    faiss_index_final, faiss_codigos_final = load_faiss_index()
    faiss_count_final = faiss_index_final.ntotal if faiss_index_final else 0

    print(f"\n  {'Almacen':<15} {'Total':>8} {'Estado':>12}")
    print(f"  {'-'*35}")
    print(f"  {'SQLite':<15} {len(sqlite_ids):>8} {'✅':>12}")
    print(f"  {'ChromaDB':<15} {len(chroma_ids_final):>8} {'✅' if len(chroma_ids_final) == len(sqlite_ids) else '⚠':>12}")
    print(f"  {'FAISS':<15} {faiss_count_final:>8} {'✅' if faiss_count_final == len(sqlite_ids) else '⚠':>12}")

    all_synced = (
        len(chroma_ids_final) == len(sqlite_ids) and
        faiss_count_final == len(sqlite_embeddings) and
        len(set(faiss_codigos_final)) == len(faiss_codigos_final)
    )

    if all_synced:
        print(f"\n  ✅ Sincronizacion completa: {len(sqlite_ids)} embeddings en los 3 almacenes")
    else:
        remaining = []
        if len(chroma_ids_final) != len(sqlite_ids):
            remaining.append(f"ChromaDB: {len(chroma_ids_final)} vs {len(sqlite_ids)}")
        if faiss_count_final != len(sqlite_embeddings):
            remaining.append(f"FAISS: {faiss_count_final} vs {len(sqlite_embeddings)}")
        print(f"\n  ⚠ Problemas restantes: {', '.join(remaining)}")

    conn.close()


if __name__ == "__main__":
    main()
