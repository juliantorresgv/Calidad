"""
Sincronización incremental con Integr@.
Detecta documentos nuevos, modificados y eliminados sin reindexar todo.

Compara los registros actuales de SQLite con los de SQL Server y:
- INSERTA documentos nuevos
- ACTUALIZA documentos modificados (cambio de estado, contenido, fecha)
- MARCA documentos eliminados (que ya no están en Integr@)

Uso:
    $env:INTEGRA_DB_SERVER="10.238.66.14"
    python Codigo/sync_incremental.py
"""
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"
SCHEMA_PATH = Path(__file__).parent / "schema_map.json"


def get_db_connection():
    """Conexión a SQL Server Integr@ usando credenciales de credenciales.txt."""
    import pyodbc
    server = os.environ.get("INTEGRA_DB_SERVER", "10.238.66.14")

    # Leer credenciales de credenciales.txt (igual que IntegraDBClient)
    cred_path = Path(__file__).parent.parent / "credenciales.txt"
    username, password = None, None
    if cred_path.exists():
        lines = [l.strip() for l in cred_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if len(lines) >= 2:
            username, password = lines[0], lines[1]

    # Fallback a variables de entorno
    username = username or os.environ.get("INTEGRA_DB_USER")
    password = password or os.environ.get("INTEGRA_DB_PASSWORD")

    if username and password:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};DATABASE=Integra;"
            f"UID={username};PWD={password};"
            f"TrustServerCertificate=yes;Connection Timeout=30;"
        )
    else:
        # Fallback a Windows auth si no hay credenciales
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};DATABASE=Integra;Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;Connection Timeout=30;"
        )
    return pyodbc.connect(conn_str)


def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def sync_incremental(solo_reporte: bool = False) -> dict:
    """Sincroniza SQLite con Integr@ detectando cambios.

    Args:
        solo_reporte: Si True, solo detecta cambios sin aplicarlos.

    Returns:
        Reporte estructurado con nuevos, modificados, eliminados, sin_cambios.
    """
    print("=" * 60)
    print("  SINCRONIZACIÓN INCREMENTAL CON INTEGR@")
    print("=" * 60)

    start_time = time.time()
    reporte = {
        "nuevos": [],
        "modificados": [],
        "eliminados": [],
        "sin_cambios": 0,
        "total_integra": 0,
        "total_local": 0,
        "tiempo_segundos": 0,
        "solo_reporte": solo_reporte,
    }

    # ─── 1. Conectar a SQL Server ───
    print("\n[1/5] Conectando a SQL Server Integr@...")
    try:
        sql_conn = get_db_connection()
        print("  Conexión exitosa.")
    except Exception as e:
        print(f"  Error de conexión: {e}")
        reporte["error"] = str(e)
        return reporte

    # ─── 2. Obtener inventario actual de Integr@ ───
    print("\n[2/5] Obteniendo inventario de Integr@...")
    sql_rows = sql_conn.execute("""
        SELECT
            TRIM(PROCEDIMIENTOS_COD),
            TRIM(PROCEDIMIENTOS_NOMBRE),
            PROCEDIMIENTOS_ESTADO,
            TRIM(PROCEDIMIENTOS_ANTE),
            PROCEDIMIENTOS_FCHPUBLICACION,
            PROCEDIMIENTOS_FCHELBABORACION,
            PROCEDIMIENTOS_VIGENCIA,
            ProcesoCod,
            LEN(PROCEDIMIENTOS_WORD) as word_len
        FROM PROCEDIMIENTOS
        WHERE PROCEDIMIENTOS_COD IS NOT NULL
    """).fetchall()

    sql_docs = {}
    for r in sql_rows:
        codigo = r[0]
        if not codigo:
            continue
        sql_docs[codigo] = {
            "nombre": r[1],
            "estado": r[2],
            "ante": r[3],
            "fch_publicacion": str(r[4]) if r[4] else None,
            "fch_elaboracion": str(r[5]) if r[5] else None,
            "vigencia": r[6],
            "proceso_cod": r[7],
            "word_len": r[8] or 0,
        }

    print(f"  Documentos en Integr@: {len(sql_docs)}")
    reporte["total_integra"] = len(sql_docs)

    # ─── 3. Obtener inventario actual de SQLite ───
    print("\n[3/5] Obteniendo inventario local (SQLite)...")
    sqlite_conn = sqlite3.connect(str(DB_PATH))

    local_rows = sqlite_conn.execute("""
        SELECT codigo, nombre, estado, fecha_publicacion, vigencia_dias, texto_length
        FROM procedimientos
    """).fetchall()

    local_docs = {}
    for r in local_rows:
        local_docs[r[0]] = {
            "nombre": r[1],
            "estado": r[2],
            "fecha_publicacion": r[3],
            "vigencia_dias": r[4],
            "texto_length": r[5] or 0,
        }

    print(f"  Documentos en SQLite: {len(local_docs)}")
    reporte["total_local"] = len(local_docs)

    # ─── 4. Detectar cambios ───
    print("\n[4/5] Detectando cambios...")

    nuevos = []
    modificados = []
    eliminados = []
    sin_cambios = 0

    for codigo, sql_info in sql_docs.items():
        if codigo not in local_docs:
            nuevos.append(codigo)
            reporte["nuevos"].append({"codigo": codigo, "nombre": sql_info["nombre"]})
        else:
            local = local_docs[codigo]
            # Detectar cambios
            cambio_estado = (sql_info["estado"] or "") != (local["estado"] or "")
            cambio_nombre = (sql_info["nombre"] or "") != (local["nombre"] or "")
            cambio_vigencia = (sql_info["vigencia"] or 0) != (local["vigencia_dias"] or 0)
            cambio_fecha = str(sql_info["fch_publicacion"] or "") != str(local["fecha_publicacion"] or "")
            # Detectar documentos sin contenido (fallaron en descarga anterior)
            sin_contenido = (local["texto_length"] or 0) == 0

            if cambio_estado or cambio_nombre or cambio_vigencia or cambio_fecha or sin_contenido:
                modificados.append({
                    "codigo": codigo,
                    "cambios": [],
                })
                m = modificados[-1]["cambios"]
                cambios_detectados = []
                if cambio_estado:
                    m.append(f"estado: {local['estado']} → {sql_info['estado']}")
                    cambios_detectados.append("estado")
                if cambio_nombre:
                    m.append(f"nombre actualizado")
                    cambios_detectados.append("nombre")
                if cambio_vigencia:
                    m.append(f"vigencia: {local['vigencia_dias']} → {sql_info['vigencia']}")
                    cambios_detectados.append("vigencia")
                if cambio_fecha:
                    m.append(f"fecha publicación actualizada")
                    cambios_detectados.append("fecha")
                if sin_contenido:
                    m.append("sin contenido - re-descargar")
                    cambios_detectados.append("contenido")
                reporte["modificados"].append({"codigo": codigo, "cambios": cambios_detectados})
            else:
                sin_cambios += 1

    for codigo in local_docs:
        if codigo not in sql_docs:
            eliminados.append(codigo)
            reporte["eliminados"].append({"codigo": codigo, "nombre": local_docs[codigo]["nombre"]})

    reporte["sin_cambios"] = sin_cambios

    # ─── Reporte de cambios ───
    print(f"\n  {'='*50}")
    print(f"  REPORTE DE CAMBIOS")
    print(f"  {'='*50}")
    print(f"  🟢 Nuevos:          {len(nuevos)}")
    print(f"  🟡 Modificados:     {len(modificados)}")
    print(f"  🔴 Eliminados:      {len(eliminados)}")
    print(f"  ⚪ Sin cambios:     {sin_cambios}")

    if nuevos:
        print(f"\n  🟢 Documentos NUEVOS:")
        for c in nuevos[:10]:
            print(f"    {c} - {sql_docs[c]['nombre'][:50]}")
        if len(nuevos) > 10:
            print(f"    ... y {len(nuevos) - 10} más")

    if modificados:
        print(f"\n  🟡 Documentos MODIFICADOS:")
        for m in modificados[:10]:
            print(f"    {m['codigo']} - {', '.join(m['cambios'])}")
        if len(modificados) > 10:
            print(f"    ... y {len(modificados) - 10} más")

    if eliminados:
        print(f"\n  🔴 Documentos ELIMINADOS (ya no en Integr@):")
        for c in eliminados[:10]:
            print(f"    {c} - {local_docs[c]['nombre'][:50]}")
        if len(eliminados) > 10:
            print(f"    ... y {len(eliminados) - 10} más")

    # ─── 5. Aplicar cambios ───
    if solo_reporte:
        print(f"\n[5/5] Modo solo reporte - no se aplican cambios.")
    else:
        print(f"\n[5/5] Aplicando cambios a SQLite...")

        # Marcar eliminados
        if eliminados:
            sqlite_conn.executemany(
                "UPDATE procedimientos SET estado = 'ELIMINADO' WHERE codigo = ?",
                [(c,) for c in eliminados]
            )
            print(f"  {len(eliminados)} documentos marcados como ELIMINADO")

        # Descargar y insertar nuevos
        if nuevos:
            print(f"\n  Descargando {len(nuevos)} documentos nuevos...")
            from integra_procedimientos import get_procedimiento_completo
            for i, codigo in enumerate(nuevos):
                try:
                    info = get_procedimiento_completo(sql_conn, codigo)
                    if info:
                        sqlite_conn.execute("""
                            INSERT OR REPLACE INTO procedimientos
                            (codigo, nombre, estado, estado_desc, proceso_cod, proceso_nom,
                             tipo_documento, contenido_html, contenido_texto, texto_length,
                             fecha_publicacion, vigencia_dias, fecha_elaboracion)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            info["codigo"], info["nombre"], info["estado"], info["estado_desc"],
                            info["proceso_cod"], info["proceso_nom"], info["tipo_documento"],
                            info["contenido_html"], info["contenido_texto"], len(info["contenido_texto"] or ""),
                            info["fecha_publicacion"], info["vigencia_dias"], info["fecha_elaboracion"],
                        ))
                        sqlite_conn.commit()
                except Exception as e:
                    print(f"  Error descargando {codigo}: {e}")

                if (i + 1) % 10 == 0:
                    print(f"  Progresado: {i+1}/{len(nuevos)}")

            print(f"  {len(nuevos)} documentos nuevos insertados")

        # Actualizar modificados (incluye re-descarga de contenido)
        if modificados:
            from integra_procedimientos import get_procedimiento_completo
            print(f"\n  Descargando {len(modificados)} documentos modificados...")
            for i, m in enumerate(modificados):
                codigo = m["codigo"]
                sql_info = sql_docs[codigo]
                try:
                    info = get_procedimiento_completo(sql_conn, codigo)
                    if info:
                        sqlite_conn.execute("""
                            UPDATE procedimientos
                            SET estado = ?, nombre = ?, vigencia_dias = ?, fecha_publicacion = ?,
                                estado_desc = ?, proceso_cod = ?, proceso_nom = ?, tipo_documento = ?,
                                contenido_html = ?, contenido_texto = ?, texto_length = ?,
                                fecha_elaboracion = ?
                            WHERE codigo = ?
                        """, (
                            info["estado"], info["nombre"], info["vigencia_dias"], info["fecha_publicacion"],
                            info["estado_desc"], info["proceso_cod"], info["proceso_nom"], info["tipo_documento"],
                            info["contenido_html"], info["contenido_texto"], len(info["contenido_texto"] or ""),
                            info["fecha_elaboracion"],
                            codigo
                        ))
                        sqlite_conn.commit()
                except Exception as e:
                    print(f"  Error re-descargando {codigo}: {e}")

                if (i + 1) % 10 == 0:
                    print(f"  Progresado: {i+1}/{len(modificados)}")

            print(f"  {len(modificados)} documentos actualizados")

        if not nuevos and not modificados and not eliminados:
            print("  No hay cambios. Base de datos actualizada.")

        # Guardar log de sincronización
        sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                fecha TEXT,
                nuevos INTEGER,
                modificados INTEGER,
                eliminados INTEGER,
                sin_cambios INTEGER
            )
        """)
        sqlite_conn.execute("""
            INSERT INTO sync_log (fecha, nuevos, modificados, eliminados, sin_cambios)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            len(nuevos), len(modificados), len(eliminados), sin_cambios
        ))
        sqlite_conn.commit()

    elapsed = time.time() - start_time
    reporte["tiempo_segundos"] = round(elapsed, 1)
    print(f"\n{'='*60}")
    print(f"  SINCRONIZACIÓN COMPLETADA en {fmt_time(elapsed)}")
    print(f"{'='*60}")

    if nuevos or modificados:
        print(f"\n  Para actualizar embeddings de documentos nuevos/modificados:")
        print(f"    $env:MISTRAL_API_KEY=\"<tu_api_key>\"")
        print(f"    python generate_embeddings.py  # solo procesa pendientes")

    if nuevos or modificados:
        print(f"\n  Para actualizar resúmenes de documentos nuevos/modificados:")
        print(f"    $env:MISTRAL_API_KEY=\"<tu_api_key>\"")
        print(f"    python generar_resumenes.py  # solo procesa pendientes")

    sqlite_conn.close()
    sql_conn.close()

    return reporte


def sync_completo_con_embeddings():
    """Sincroniza documentos + regenera embeddings y resumenes de cambios.
    Funcion completa para uso automatico (boton UI o task diaria).
    """
    # 1. Sincronizar documentos
    reporte = sync_incremental(solo_reporte=False)

    if "error" in reporte:
        return reporte

    hay_cambios = bool(reporte["nuevos"] or reporte["modificados"])
    if not hay_cambios:
        print("\n[SYNC] No hay cambios. No se regeneran embeddings/resumenes.")
        return reporte

    # 2. Regenerar embeddings de documentos nuevos/modificados
    print("\n" + "=" * 60)
    print("  REGENERANDO EMBEDDINGS")
    print("=" * 60)
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from generate_embeddings import main as gen_embeddings
        gen_embeddings()
        reporte["embeddings_regenerados"] = True
    except Exception as e:
        print(f"  Error regenerando embeddings: {e}")
        reporte["embeddings_error"] = str(e)

    # 3. Regenerar resumenes de documentos nuevos/modificados
    print("\n" + "=" * 60)
    print("  REGENERANDO RESUMENES")
    print("=" * 60)
    try:
        from generar_resumenes import main as gen_resumenes
        gen_resumenes()
        reporte["resumenes_regenerados"] = True
    except Exception as e:
        print(f"  Error regenerando resumenes: {e}")
        reporte["resumenes_error"] = str(e)

    # 4. Reconstruir grafo de conocimiento
    print("\n" + "=" * 60)
    print("  RECONSTRUYENDO GRAFO DE CONOCIMIENTO")
    print("=" * 60)
    try:
        from inventario_metadatos import main as gen_inventario
        gen_inventario()
        reporte["grafo_reconstruido"] = True
    except Exception as e:
        print(f"  Error reconstruyendo grafo: {e}")
        reporte["grafo_error"] = str(e)

    return reporte


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--reporte", action="store_true", help="Solo detectar cambios sin aplicar")
    parser.add_argument("--completo", action="store_true", help="Sync + embeddings + resumenes + grafo")
    args = parser.parse_args()

    if args.completo:
        sync_completo_con_embeddings()
    elif args.reporte:
        sync_incremental(solo_reporte=True)
    else:
        sync_incremental()
