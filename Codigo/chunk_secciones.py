"""
Chunking por secciones de documentos.
Divide cada procedimiento en secciones (objetivo, alcance, procedimiento, etc.)
e indexa cada sección por separado en ChromaDB para recuperación más precisa.

Uso:
    $env:MISTRAL_API_KEY="<tu_api_key>"
    python Codigo/chunk_secciones.py
"""
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from openai import OpenAI

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
EMBED_MODEL = "mistral-embed"
CHAT_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
MAX_SECTION_LENGTH = 1500  # caracteres por sección
MIN_SECTION_LENGTH = 50    # mínimo para indexar


def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


# ──────────────────────────────────────────────
# Extracción de secciones desde HTML/texto
# ──────────────────────────────────────────────

# Patrones de secciones comunes en procedimientos de calidad
SECCIONES_PATRONES = [
    "objetivo",
    "alcance",
    "definiciones",
    "responsabilidades",
    "responsables",
    "documentos de referencia",
    "documentos relacionados",
    "normatividad",
    "marco legal",
    "procedimiento",
    "descripción del procedimiento",
    "descripcion del procedimiento",
    "actividades",
    "registros",
    "anexos",
    "control de cambios",
    "indicadores",
    "kpi",
    "glosario",
    "mediciones",
    "frecuencia",
    "evidencias",
    "capacitación",
    "capacitacion",
    "riesgos",
    "sst",
    "seguridad y salud",
    "ep",
    "condiciones de almacenamiento",
    "cadena de frío",
    "cadena de frio",
    "temperatura",
    "calibración",
    "calibracion",
]


def extraer_secciones(texto: str, codigo: str) -> list[dict]:
    """Extrae secciones del texto del documento."""
    if not texto:
        return []

    secciones = []

    # Intentar extraer por encabezados detectados
    lineas = texto.split("\n")
    seccion_actual = "general"
    contenido_actual = []
    nivel_actual = 0

    for linea in lineas:
        linea_stripped = linea.strip()
        if not linea_stripped:
            if contenido_actual:
                contenido_actual.append("")
            continue

        # Detectar si es un encabezado
        es_encabezado = False
        for patron in SECCIONES_PATRONES:
            if linea_stripped.lower().startswith(patron) and len(linea_stripped) < 80:
                # Guardar sección anterior
                if contenido_actual:
                    texto_sec = "\n".join(contenido_actual).strip()
                    if len(texto_sec) >= MIN_SECTION_LENGTH:
                        secciones.append({
                            "codigo": codigo,
                            "seccion": seccion_actual,
                            "texto": texto_sec,
                        })
                seccion_actual = linea_stripped.lower()[:50]
                contenido_actual = []
                es_encabezado = True
                break

        if not es_encabezado:
            contenido_actual.append(linea_stripped)

    # Última sección
    if contenido_actual:
        texto_sec = "\n".join(contenido_actual).strip()
        if len(texto_sec) >= MIN_SECTION_LENGTH:
            secciones.append({
                "codigo": codigo,
                "seccion": seccion_actual,
                "texto": texto_sec,
            })

    # Si no se detectaron secciones, dividir por tamaño
    if len(secciones) <= 1 and len(texto) > MAX_SECTION_LENGTH:
        secciones = []
        for i in range(0, len(texto), MAX_SECTION_LENGTH):
            chunk = texto[i:i + MAX_SECTION_LENGTH]
            if len(chunk) >= MIN_SECTION_LENGTH:
                secciones.append({
                    "codigo": codigo,
                    "seccion": f"chunk_{i // MAX_SECTION_LENGTH}",
                    "texto": chunk,
                })

    return secciones


# ──────────────────────────────────────────────
# Indexación de secciones
# ──────────────────────────────────────────────

def indexar_secciones(conn, client):
    """Extrae secciones de cada documento y las indexa en ChromaDB."""
    print("\n  Extrayendo e indexando secciones...")

    # Crear tabla de secciones en SQLite
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documento_secciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            seccion TEXT,
            texto TEXT,
            texto_length INTEGER,
            embedding_id TEXT
        )
    """)
    conn.execute("DELETE FROM documento_secciones")
    conn.commit()

    # Conectar a ChromaDB
    import chromadb
    chroma_path = str(Path(__file__).parent.parent / "chroma_db")
    chroma_client = chromadb.PersistentClient(path=chroma_path)
    collection = chroma_client.get_or_create_collection(
        name="secciones",
        metadata={"description": "Secciones de documentos Integr@"}
    )

    # Obtener documentos
    total = conn.execute("SELECT COUNT(*) FROM procedimientos WHERE texto_length > 100").fetchone()[0]
    print(f"  Documentos a procesar: {total}")

    start_time = time.time()
    processed = 0
    total_secciones = 0

    rows = conn.execute("""
        SELECT codigo, contenido_texto FROM procedimientos
        WHERE texto_length > 100
    """).fetchall()

    batch_docs = []
    batch_metas = []
    batch_ids = []
    batch_codigos = []

    for codigo, texto in rows:
        secciones = extraer_secciones(texto or "", codigo)

        for idx_sec, sec in enumerate(secciones):
            sec_id = f"{codigo}_sec_{idx_sec}"
            batch_docs.append(sec["texto"][:4000])
            batch_metas.append({
                "codigo": codigo,
                "seccion": sec["seccion"],
            })
            batch_ids.append(sec_id)
            batch_codigos.append((codigo, sec["seccion"], sec["texto"], len(sec["texto"]), sec_id))

            total_secciones += 1

            # Procesar en lotes de 50
            if len(batch_docs) >= 50:
                try:
                    embeddings = client.embeddings.create(
                        model=EMBED_MODEL,
                        input=batch_docs,
                    )
                    vectors = [d.embedding for d in embeddings.data]

                    collection.upsert(
                        ids=batch_ids,
                        embeddings=vectors,
                        documents=batch_docs,
                        metadatas=batch_metas,
                    )

                    conn.executemany("""
                        INSERT INTO documento_secciones
                        (codigo, seccion, texto, texto_length, embedding_id)
                        VALUES (?, ?, ?, ?, ?)
                    """, batch_codigos)
                    conn.commit()

                except Exception as e:
                    print(f"\n  Error en lote: {e}")

                batch_docs = []
                batch_metas = []
                batch_ids = []
                batch_codigos = []

        processed += 1
        if processed % 50 == 0:
            elapsed = time.time() - start_time
            eta = elapsed / processed * (total - processed)
            print(f"  Progresado: {processed}/{total} | secciones: {total_secciones} | "
                  f"elapsed: {fmt_time(elapsed)} eta: {fmt_time(eta)}")

    # Último lote
    if batch_docs:
        try:
            embeddings = client.embeddings.create(
                model=EMBED_MODEL,
                input=batch_docs,
            )
            vectors = [d.embedding for d in embeddings.data]
            collection.upsert(
                ids=batch_ids,
                embeddings=vectors,
                documents=batch_docs,
                metadatas=batch_metas,
            )
            conn.executemany("""
                INSERT INTO documento_secciones
                (codigo, seccion, texto, texto_length, embedding_id)
                VALUES (?, ?, ?, ?, ?)
            """, batch_codigos)
            conn.commit()
        except Exception as e:
            print(f"\n  Error en último lote: {e}")

    elapsed = time.time() - start_time
    print(f"\n  Secciones indexadas: {total_secciones} en {fmt_time(elapsed)}")
    print(f"  Promedio: {total_secciones / max(processed, 1):.1f} secciones por documento")

    # Resumen de secciones más comunes
    from collections import Counter
    secciones_count = Counter()
    for row in conn.execute("SELECT seccion FROM documento_secciones").fetchall():
        secciones_count[row[0]] += 1

    print(f"\n  Top 10 secciones más frecuentes:")
    for sec, count in secciones_count.most_common(10):
        print(f"    {sec}: {count}")


def main():
    print("=" * 60)
    print("  CHUNKING POR SECCIONES")
    print("=" * 60)

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("\n  ⚠ Sin MISTRAL_API_KEY, no se pueden generar embeddings.")
        print("  Ejecuta con: $env:MISTRAL_API_KEY=\"<tu_api_key>\"")
        return

    client = OpenAI(base_url=MISTRAL_BASE_URL, api_key=api_key)
    conn = sqlite3.connect(str(DB_PATH))

    indexar_secciones(conn, client)

    print(f"\n{'='*60}")
    print(f"  COMPLETADO")
    print(f"{'='*60}")
    print(f"  Secciones en: ChromaDB (colección 'secciones') + SQLite (documento_secciones)")
    conn.close()


if __name__ == "__main__":
    main()
