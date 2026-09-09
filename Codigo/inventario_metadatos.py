"""
Inventario de metadatos de calidad.
Genera un reporte consolidado del estado documental del sistema Integr@
y lo guarda en SQLite para que el agente lo consulte.

También persiste el grafo de relaciones en SQLite para no reconstruirlo
cada vez que se inicia el agente.

Uso:
    python Codigo/inventario_metadatos.py
"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"


# ──────────────────────────────────────────────
# 1. INVENTARIO DE METADATOS
# ──────────────────────────────────────────────

def generar_inventario(conn):
    """Genera el inventario de metadatos de calidad."""
    print("\n  Generando inventario de metadatos...")

    # Crear tabla
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventario_metadatos (
            categoria TEXT,
            subcategoria TEXT,
            valor TEXT,
            cantidad INTEGER,
            porcentaje REAL,
            observacion TEXT,
            PRIMARY KEY (categoria, subcategoria, valor)
        )
    """)
    conn.execute("DELETE FROM inventario_metadatos")

    rows = conn.execute("""
        SELECT
            TRIM(codigo), TRIM(nombre), estado, estado_desc,
            TRIM(proceso_cod), TRIM(proceso_nom),
            TRIM(tipo_documento),
            fecha_publicacion, vigencia_dias,
            texto_length
        FROM procedimientos
    """).fetchall()

    total = len(rows)
    print(f"  Total documentos: {total}")

    batch = []

    # ─── Por estado ───
    estados = Counter()
    estado_desc_map = {}
    for r in rows:
        estado = r[2] or "NULL"
        estados[estado] += 1
        estado_desc_map[estado] = r[3] or estado
    for estado, count in estados.most_common():
        pct = count / total * 100
        obs = ""
        if estado == "P":
            obs = "Vigentes - disponibles para consulta"
        elif estado == "O":
            obs = "Obsoletos - excluidos por defecto"
        elif estado == "E":
            obs = "En elaboración - no publicados"
        batch.append(("ESTADO", estado_desc_map.get(estado, estado), estado, count, pct, obs))

    # ─── Por proceso ───
    procesos = Counter()
    proceso_nom_map = {}
    for r in rows:
        proc = r[4] or "SIN_PROCESO"
        procesos[proc] += 1
        proceso_nom_map[proc] = r[5] or proc
    for proc, count in procesos.most_common():
        pct = count / total * 100
        batch.append(("PROCESO", proceso_nom_map.get(proc, proc), proc, count, pct, ""))

    # ─── Por tipo de documento ───
    tipos = Counter()
    for r in rows:
        tipo = r[6] or "SIN_TIPO"
        tipos[tipo] += 1
    for tipo, count in tipos.most_common():
        pct = count / total * 100
        batch.append(("TIPO_DOCUMENTO", tipo, tipo, count, pct, ""))

    # ─── Por vigencia ───
    hoy = datetime.now()
    vigentes = 0
    vencidos = 0
    sin_vigencia = 0
    por_vencer_30 = 0
    por_vencer_90 = 0

    for r in rows:
        estado = r[2]
        fecha_pub = r[7]
        vigencia = r[8]

        if estado != "P":
            continue

        if not fecha_pub or not vigencia:
            sin_vigencia += 1
            continue

        try:
            fecha_str = str(fecha_pub).split(".")[0].strip()
            fecha_pub_dt = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            try:
                fecha_pub_dt = datetime.strptime(str(fecha_pub)[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                sin_vigencia += 1
                continue

        fecha_venc = fecha_pub_dt + timedelta(days=int(vigencia or 0))
        dias = (fecha_venc - hoy).days

        if dias < 0:
            vencidos += 1
        elif dias <= 30:
            por_vencer_30 += 1
        elif dias <= 90:
            por_vencer_90 += 1
        else:
            vigentes += 1

    batch.append(("VIGENCIA", "Vigentes", "vigentes", vigentes, vigentes/total*100, "Publicados y dentro de vigencia"))
    batch.append(("VIGENCIA", "Vencidos", "vencidos", vencidos, vencidos/total*100, "Publicados pero vencidos"))
    batch.append(("VIGENCIA", "Por vencer 30 días", "por_vencer_30", por_vencer_30, por_vencer_30/total*100, "Vencen en 30 días"))
    batch.append(("VIGENCIA", "Por vencer 90 días", "por_vencer_90", por_vencer_90, por_vencer_90/total*100, "Vencen en 90 días"))
    batch.append(("VIGENCIA", "Sin vigencia definida", "sin_vigencia", sin_vigencia, sin_vigencia/total*100, "No tienen fecha o días de vigencia"))

    # ─── Por contenido ───
    con_texto = sum(1 for r in rows if r[9] and r[9] > 100)
    sin_texto = total - con_texto
    batch.append(("CONTENIDO", "Con texto extraído", "con_texto", con_texto, con_texto/total*100, "Texto disponible para búsqueda"))
    batch.append(("CONTENIDO", "Sin texto", "sin_texto", sin_texto, sin_texto/total*100, "No se pudo extraer texto del HTML"))

    # ─── Por rango de tamaño ───
    pequeno = sum(1 for r in rows if r[9] and r[9] < 1000)
    mediano = sum(1 for r in rows if r[9] and 1000 <= r[9] < 5000)
    grande = sum(1 for r in rows if r[9] and 5000 <= r[9] < 20000)
    muy_grande = sum(1 for r in rows if r[9] and r[9] >= 20000)
    batch.append(("TAMAÑO", "Pequeño (<1KB)", "pequeno", pequeno, pequeno/total*100, ""))
    batch.append(("TAMAÑO", "Mediano (1-5KB)", "mediano", mediano, mediano/total*100, ""))
    batch.append(("TAMAÑO", "Grande (5-20KB)", "grande", grande, grande/total*100, ""))
    batch.append(("TAMAÑO", "Muy grande (>20KB)", "muy_grande", muy_grande, muy_grande/total*100, ""))

    conn.executemany("""
        INSERT OR REPLACE INTO inventario_metadatos
        (categoria, subcategoria, valor, cantidad, porcentaje, observacion)
        VALUES (?, ?, ?, ?, ?, ?)
    """, batch)
    conn.commit()

    # Reporte
    print(f"\n  {'='*50}")
    print(f"  INVENTARIO DE METADATOS DE CALIDAD")
    print(f"  {'='*50}")

    categorias = defaultdict(list)
    for b in batch:
        categorias[b[0]].append(b)

    for cat, items in categorias.items():
        print(f"\n  [{cat}]")
        for item in sorted(items, key=lambda x: -x[3]):
            obs = f" - {item[5]}" if item[5] else ""
            print(f"    {item[1]}: {item[3]} ({item[4]:.1f}%){obs}")


# ──────────────────────────────────────────────
# 2. PERSISTENCIA DEL GRAFO
# ──────────────────────────────────────────────

def persistir_grafo(conn):
    """Persiste el grafo de relaciones en SQLite para no reconstruirlo cada vez."""
    print("\n  Persistiendo grafo de relaciones...")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS grafo_nodos (
            id TEXT PRIMARY KEY,
            tipo TEXT,
            nombre TEXT,
            atributos TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grafo_aristas (
            origen TEXT,
            destino TEXT,
            tipo_relacion TEXT,
            peso REAL,
            PRIMARY KEY (origen, destino, tipo_relacion)
        )
    """)
    conn.execute("DELETE FROM grafo_nodos")
    conn.execute("DELETE FROM grafo_aristas")

    # Construir grafo desde procedimientos
    nodos_batch = []
    aristas_batch = []

    rows = conn.execute("""
        SELECT TRIM(codigo), TRIM(nombre), estado, estado_desc,
               TRIM(proceso_cod), TRIM(proceso_nom), TRIM(tipo_documento)
        FROM procedimientos
    """).fetchall()

    # Nodos de documento
    for r in rows:
        codigo, nombre, estado, estado_desc, proc_cod, proc_nom, tipo = r
        if not codigo:
            continue
        nodos_batch.append((
            f"doc:{codigo}",
            "documento",
            nombre or "",
            json.dumps({
                "codigo": codigo,
                "estado": estado,
                "estado_desc": estado_desc,
                "tipo": tipo,
            }, ensure_ascii=False)
        ))

        # Arista: documento → proceso
        if proc_cod:
            proc_id = f"proc:{proc_cod}"
            aristas_batch.append((f"doc:{codigo}", proc_id, "pertenece_a_proceso", 1.0))

        # Arista: documento → tipo
        if tipo:
            tipo_id = f"tipo:{tipo}"
            aristas_batch.append((f"doc:{codigo}", tipo_id, "es_de_tipo", 1.0))

        # Arista: documento → estado
        if estado:
            estado_id = f"estado:{estado}"
            aristas_batch.append((f"doc:{codigo}", estado_id, "tiene_estado", 1.0))

    # Nodos de proceso
    procesos = {}
    for r in rows:
        proc_cod = r[4]
        proc_nom = r[5]
        if proc_cod and proc_cod not in procesos:
            procesos[proc_cod] = proc_nom
            nodos_batch.append((
                f"proc:{proc_cod}",
                "proceso",
                proc_nom or proc_cod,
                json.dumps({"codigo": proc_cod, "nombre": proc_nom}, ensure_ascii=False)
            ))

    # Nodos de tipo
    tipos = set()
    for r in rows:
        tipo = r[6]
        if tipo and tipo not in tipos:
            tipos.add(tipo)
            nodos_batch.append((
                f"tipo:{tipo}",
                "tipo_documento",
                tipo,
                json.dumps({"nombre": tipo}, ensure_ascii=False)
            ))

    # Nodos de estado
    estados_map = {}
    for r in rows:
        estado = r[2]
        estado_desc = r[3]
        if estado and estado not in estados_map:
            estados_map[estado] = estado_desc
            nodos_batch.append((
                f"estado:{estado}",
                "estado",
                estado_desc or estado,
                json.dumps({"codigo": estado, "descripcion": estado_desc}, ensure_ascii=False)
            ))

    conn.executemany("""
        INSERT OR REPLACE INTO grafo_nodos (id, tipo, nombre, atributos)
        VALUES (?, ?, ?, ?)
    """, nodos_batch)

    conn.executemany("""
        INSERT OR REPLACE INTO grafo_aristas (origen, destino, tipo_relacion, peso)
        VALUES (?, ?, ?, ?)
    """, aristas_batch)

    conn.commit()

    print(f"  Nodos persistidos: {len(nodos_batch)}")
    print(f"  Aristas persistidas: {len(aristas_batch)}")

    # Resumen
    tipos_nodos = Counter(n[1] for n in nodos_batch)
    print(f"\n  Nodos por tipo:")
    for t, c in tipos_nodos.most_common():
        print(f"    {t}: {c}")

    tipos_aristas = Counter(a[2] for a in aristas_batch)
    print(f"\n  Aristas por tipo:")
    for t, c in tipos_aristas.most_common():
        print(f"    {t}: {c}")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  INVENTARIO DE METADATOS + GRAFO PERSISTENTE")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))

    # 1. Inventario de metadatos
    print("\n[1/2] Inventario de metadatos...")
    generar_inventario(conn)

    # 2. Persistir grafo
    print("\n[2/2] Grafo persistente...")
    persistir_grafo(conn)

    print(f"\n{'='*60}")
    print(f"  COMPLETADO")
    print(f"{'='*60}")
    print(f"  Inventario:  inventario_metadatos (SQLite)")
    print(f"  Grafo:       grafo_nodos + grafo_aristas (SQLite)")
    conn.close()


if __name__ == "__main__":
    main()
