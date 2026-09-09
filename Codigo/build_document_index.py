"""
Extrae TODOS los procedimientos de dbo.PROCEDIMIENTOS, convierte el HTML a texto plano,
y los almacena en una base SQLite local para indexación y búsqueda semántica.

Uso:
    $env:INTEGRA_DB_SERVER="10.238.66.14"
    python Codigo/build_document_index.py

Muestra barra de progreso con %, archivos procesados y tiempo estimado.
"""
import re
import sqlite3
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

from integra_db_client import IntegraDBClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"

ESTADO_LABELS = {
    "E": "Elaborado", "D": "Devuelto", "R": "Revisado",
    "Q": "Revisado por Calidad", "A": "Aprobado",
    "P": "Publicado", "O": "Obsoleto", "Z": "Especial",
}


def html_to_text(html: str) -> str:
    """Convierte HTML a texto plano limpio."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def fmt_date(d):
    if d is None:
        return None
    s = str(d)
    if s.startswith("1753-") or s.startswith("1900-"):
        return None
    return s


def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def progress_bar(current: int, total: int, start_time: float, width: int = 30):
    pct = current / total * 100 if total else 0
    filled = int(width * current / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    elapsed = time.time() - start_time
    if current > 0:
        eta = elapsed / current * (total - current)
    else:
        eta = 0
    sys.stdout.write(
        f"\r  |{bar}| {current}/{total} ({pct:.1f}%) "
        f"elapsed: {fmt_time(elapsed)} eta: {fmt_time(eta)}"
    )
    sys.stdout.flush()


def create_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS procedimientos (
            codigo TEXT PRIMARY KEY,
            nombre TEXT,
            estado TEXT,
            estado_desc TEXT,
            proceso_cod TEXT,
            proceso_nom TEXT,
            tipo_documento TEXT,
            vigencia_dias INTEGER,
            fecha_elaboracion TEXT,
            fecha_publicacion TEXT,
            fecha_obsoleto TEXT,
            elaborador TEXT,
            revisor_proceso TEXT,
            revisor_calidad TEXT,
            aprobador_gerencia TEXT,
            publicador TEXT,
            contenido_html TEXT,
            contenido_texto TEXT,
            texto_length INTEGER,
            indexado INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            codigo TEXT PRIMARY KEY,
            embedding BLOB,
            modelo TEXT,
            creado TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS temas (
            tema_id INTEGER PRIMARY KEY,
            nombre TEXT,
            descripcion TEXT,
            num_docs INTEGER,
            palabras_clave TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documento_tema (
            codigo TEXT,
            tema_id INTEGER,
            similitud REAL,
            PRIMARY KEY (codigo, tema_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_proc_estado ON procedimientos(estado)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_proc_proceso ON procedimientos(proceso_cod)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_proc_tipo ON procedimientos(tipo_documento)")
    conn.commit()
    return conn


def main():
    print("=" * 60)
    print("  INDEXADOR DE PROCEDIMIENTOS INTEGRA")
    print("=" * 60)

    # Paso 1: Conectar y contar
    print("\n[1/4] Conectando a SQL Server Integra...")
    client = IntegraDBClient(server="10.238.66.14")
    conn_db = client.connect()
    cur = conn_db.cursor()

    print("[2/4] Descargando todos los procedimientos...")
    cur.execute("""
        SELECT
            TRIM(p.PROCEDIMIENTOS_COD),
            TRIM(p.PROCEDIMIENTOS_NOMBRE),
            p.PROCEDIMIENTOS_ESTADO,
            TRIM(p.ProcesoCod),
            TRIM(pr.ProcesoNom),
            td.TipoDocumento_Descr,
            p.PROCEDIMIENTOS_VIGENCIA,
            p.PROCEDIMIENTOS_FCHELBABORACION,
            p.PROCEDIMIENTOS_FCHPUBLICACION,
            p.PROCEDIMIENTOS_FCHOBSOLETO,
            TRIM(el.UsrDscC),
            TRIM(rev.UsrDscC),
            TRIM(revcal.UsrDscC),
            TRIM(apro.UsrDscC),
            TRIM(pub.UsrDscC),
            p.PROCEDIMIENTOS_WORD
        FROM dbo.PROCEDIMIENTOS p
        LEFT JOIN dbo.Proceso pr ON TRIM(p.ProcesoCod) = TRIM(pr.ProcesoCod)
        LEFT JOIN dbo.TipoDocumento td ON p.TipoDocumento_Id = td.TipoDocumento_Id
        LEFT JOIN dbo.TUsuarioC el ON p.PROCEDIMIENTOS_ELABORADOR = el.UsrCdgC
        LEFT JOIN dbo.TUsuarioC rev ON p.PROCEDIMIENTOS_REVISORPROC = rev.UsrCdgC
        LEFT JOIN dbo.TUsuarioC revcal ON p.PROCEDIMIENTOS_REVISIONCALIDAD = revcal.UsrCdgC
        LEFT JOIN dbo.TUsuarioC apro ON p.PROCEDIMIENTOS_APROGERENCIA = apro.UsrCdgC
        LEFT JOIN dbo.TUsuarioC pub ON p.PROCEDIMIENTOS_PUBLICACION = pub.UsrCdgC
        ORDER BY p.PROCEDIMIENTOS_COD
    """)

    rows = cur.fetchall()
    total = len(rows)
    print(f"  Total de procedimientos: {total}")

    # Paso 3: Crear DB local
    print(f"\n[3/4] Creando índice local en {DB_PATH.name}...")
    conn = create_db(DB_PATH)

    # Paso 4: Procesar con barra de progreso
    print(f"\n[4/4] Extrayendo texto de cada documento...")
    start_time = time.time()
    batch = []
    BATCH_SIZE = 50
    processed = 0
    con_texto = 0

    for i, row in enumerate(rows):
        (codigo, nombre, estado, proceso_cod, proceso_nom, tipo_doc,
         vigencia, fec_elab, fec_pub, fec_obs, elaborador, rev_proc,
         rev_cal, apro_ger, publicador, html) = row

        texto = html_to_text(html or "")
        texto_length = len(texto)
        if texto_length > 100:
            con_texto += 1

        batch.append((
            codigo, nombre, estado, ESTADO_LABELS.get(estado, ""),
            proceso_cod, proceso_nom, tipo_doc, vigencia,
            fmt_date(fec_elab), fmt_date(fec_pub), fmt_date(fec_obs),
            elaborador, rev_proc, rev_cal, apro_ger, publicador,
            (html or "")[:50000],
            texto[:20000],
            texto_length,
            0,
        ))

        if len(batch) >= BATCH_SIZE:
            conn.executemany("""
                INSERT OR REPLACE INTO procedimientos
                (codigo, nombre, estado, estado_desc, proceso_cod, proceso_nom,
                 tipo_documento, vigencia_dias, fecha_elaboracion, fecha_publicacion,
                 fecha_obsoleto, elaborador, revisor_proceso, revisor_calidad,
                 aprobador_gerencia, publicador, contenido_html, contenido_texto,
                 texto_length, indexado)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, batch)
            conn.commit()
            batch = []

        processed += 1
        progress_bar(processed, total, start_time)

    if batch:
        conn.executemany("""
            INSERT OR REPLACE INTO procedimientos
            (codigo, nombre, estado, estado_desc, proceso_cod, proceso_nom,
             tipo_documento, vigencia_dias, fecha_elaboracion, fecha_publicacion,
             fecha_obsoleto, elaborador, revisor_proceso, revisor_calidad,
             aprobador_gerencia, publicador, contenido_html, contenido_texto,
             texto_length, indexado)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, batch)
        conn.commit()

    elapsed = time.time() - start_time
    print(f"\n\n{'=' * 60}")
    print(f"  COMPLETADO en {fmt_time(elapsed)}")
    print(f"{'=' * 60}")

    # Estadísticas
    total_db = conn.execute("SELECT COUNT(*) FROM procedimientos").fetchone()[0]
    sin_texto = conn.execute("SELECT COUNT(*) FROM procedimientos WHERE texto_length <= 100").fetchone()[0]
    por_estado = conn.execute(
        "SELECT estado, estado_desc, COUNT(*) FROM procedimientos GROUP BY estado, estado_desc ORDER BY COUNT(*) DESC"
    ).fetchall()
    por_proceso = conn.execute(
        "SELECT proceso_cod, proceso_nom, COUNT(*) FROM procedimientos GROUP BY proceso_cod, proceso_nom ORDER BY COUNT(*) DESC LIMIT 10"
    ).fetchall()
    por_tipo = conn.execute(
        "SELECT tipo_documento, COUNT(*) FROM procedimientos GROUP BY tipo_documento"
    ).fetchall()

    print(f"\n  Total en índice:     {total_db}")
    print(f"  Con contenido:       {con_texto}")
    print(f"  Sin texto (vacíos):  {sin_texto}")
    print(f"  Tamaño DB:           {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")

    print(f"\n  Por estado:")
    for est, desc, cnt in por_estado:
        print(f"    {est} ({desc}): {cnt}")

    print(f"\n  Por tipo:")
    for tipo, cnt in por_tipo:
        print(f"    {tipo}: {cnt}")

    print(f"\n  Top 10 procesos:")
    for cod, nom, cnt in por_proceso:
        print(f"    {cod} - {nom}: {cnt}")

    print(f"\n  DB guardada en: {DB_PATH}")
    conn.close()
    conn_db.close()


if __name__ == "__main__":
    main()
