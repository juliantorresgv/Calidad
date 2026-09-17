"""
Gestion de Calidad Avanzada para el Agente de Calidad Integr@.

Modulos:
    - Grafo de procesos (BPMN): modela flujos de proceso como grafo navegable
    - Base de conocimiento de hallazgos: almacena hallazgos historicos de auditorias y sus CAPA
    - Matriz RACI automatica: genera matriz RACI desde los documentos
    - Indicadores automaticos: calcula KPIs (tasa NC, tiempo cierre CAPA, etc.)

Uso:
    from gestion_calidad import GestionCalidad
    gc = GestionCalidad()
    procesos = gc.grafo_procesos_bpmn()
    hallazgos = gc.listar_hallazgos()
    raci = gc.matriz_raci("PGC-16-15")
    kpis = gc.indicadores_kpi()
"""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"


class GestionCalidad:
    """Gestion de calidad avanzada: BPMN, hallazgos, RACI, KPIs."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        """Crea las tablas necesarias."""
        # Base de conocimiento de hallazgos
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS hallazgos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                tipo TEXT,
                severidad TEXT,
                proceso TEXT,
                documento_origen TEXT,
                auditoria TEXT,
                fecha_deteccion TEXT,
                estado TEXT DEFAULT 'Abierto',
                capa_aplicada TEXT,
                fecha_cierre TEXT,
                leccion_aprendida TEXT,
                creado TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        # Matriz RACI
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS matriz_raci (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                documento_codigo TEXT,
                actividad TEXT,
                responsable TEXT,
                accountable TEXT,
                consulted TEXT,
                informed TEXT,
                creado TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        # KPIs historicos
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS kpis_historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                kpi_nombre TEXT,
                kpi_valor REAL,
                kpi_meta REAL,
                kpi_unidad TEXT,
                proceso TEXT
            )
        """)
        self.conn.commit()

    # ──────────────────────────────────────────────
    # Grafo de procesos (BPMN)
    # ──────────────────────────────────────────────

    def grafo_procesos_bpmn(self) -> dict:
        """Modela flujos de proceso como grafo navegable.
        Extrae actividades, decisiones y secuencias desde los documentos.
        """
        # Obtener procesos unicos
        rows = self.conn.execute("""
            SELECT DISTINCT proceso_cod, proceso_nom
            FROM procedimientos
            WHERE proceso_nom IS NOT NULL AND estado = 'P'
            ORDER BY proceso_nom
        """).fetchall()

        procesos = []
        for r in rows:
            proc_cod, proc_nom = r[0], r[1]
            # Documentos del proceso
            docs = self.conn.execute("""
                SELECT codigo, nombre, tipo_documento, estado
                FROM procedimientos
                WHERE proceso_cod = ? AND estado = 'P'
                ORDER BY nombre
            """, (proc_cod,)).fetchall()

            # Tipos de documento en el proceso
            tipos = self.conn.execute("""
                SELECT DISTINCT tipo_documento
                FROM procedimientos
                WHERE proceso_cod = ? AND estado = 'P'
            """, (proc_cod,)).fetchall()

            procesos.append({
                "codigo": proc_cod,
                "nombre": proc_nom,
                "documentos": [
                    {"codigo": d[0], "nombre": d[1], "tipo": d[2], "estado": d[3]}
                    for d in docs
                ],
                "tipos_documento": [t[0] for t in tipos if t[0]],
                "total_docs": len(docs),
            })

        # Construir nodos y aristas del grafo
        nodos = []
        aristas = []

        # Nodo raiz: "Integr@"
        nodos.append({"id": "root", "tipo": "sistema", "nombre": "Integr@"})

        for p in procesos:
            nodo_proc = f"proc:{p['codigo']}"
            nodos.append({"id": nodo_proc, "tipo": "proceso", "nombre": p["nombre"]})
            aristas.append({"source": "root", "target": nodo_proc, "tipo": "contiene"})

            # Nodos por tipo de documento
            for tipo in p["tipos_documento"]:
                nodo_tipo = f"tipo:{p['codigo']}:{tipo}"
                nodos.append({"id": nodo_tipo, "tipo": "tipo_doc", "nombre": tipo})
                aristas.append({"source": nodo_proc, "target": nodo_tipo, "tipo": "agrupa"})

            # Nodos por documento
            for d in p["documentos"]:
                nodo_doc = f"doc:{d['codigo']}"
                nodos.append({"id": nodo_doc, "tipo": "documento", "nombre": d["nombre"][:60]})
                aristas.append({"source": nodo_proc, "target": nodo_doc, "tipo": "pertenece_a"})

        return {
            "nodos": nodos,
            "aristas": aristas,
            "total_procesos": len(procesos),
            "total_documentos": sum(p["total_docs"] for p in procesos),
        }

    def flujo_proceso_bpmn(self, proceso: str) -> dict:
        """Genera un flujo BPMN simplificado para un proceso especifico.
        Extrae actividades secuenciales desde el contenido de los documentos.
        """
        # Obtener documentos del proceso
        docs = self.conn.execute("""
            SELECT codigo, nombre, contenido_texto
            FROM procedimientos
            WHERE (proceso_nom LIKE ? OR proceso_cod = ?) AND estado = 'P'
            ORDER BY nombre
        """, (f"%{proceso}%", proceso)).fetchall()

        actividades = []
        for d in docs:
            codigo, nombre, texto = d[0], d[1], d[2] or ""
            # Extraer actividades (lineas que empiezan con verbo o numero)
            lineas = texto.split("\n")
            for linea in lineas:
                linea = linea.strip()
                # Patrones de actividad: "1. ...", "Paso 1: ...", verbos
                if re.match(r'^\d+[\.\)]\s+', linea) or re.match(r'^Paso\s+\d+', linea, re.I):
                    actividad = re.sub(r'^\d+[\.\)]\s+', '', linea)
                    actividad = re.sub(r'^Paso\s+\d+:\s*', '', actividad, flags=re.I)
                    if len(actividad) > 10 and len(actividad) < 200:
                        actividades.append({
                            "documento": codigo,
                            "actividad": actividad[:150],
                        })
                # Decisiones (si...entonces)
                elif re.match(r'^Si\s+', linea, re.I) and len(linea) < 200:
                    actividades.append({
                        "documento": codigo,
                        "actividad": linea[:150],
                        "tipo": "decision",
                    })

        # Construir flujo secuencial
        nodos = []
        aristas = []
        for i, act in enumerate(actividades[:30]):  # limitar a 30 actividades
            nodo_id = f"act_{i}"
            nodos.append({
                "id": nodo_id,
                "tipo": act.get("tipo", "actividad"),
                "nombre": act["actividad"],
                "documento": act["documento"],
            })
            if i > 0:
                aristas.append({"source": f"act_{i-1}", "target": nodo_id, "tipo": "secuencia"})

        # Agregar nodo inicial y final
        nodos.insert(0, {"id": "inicio", "tipo": "inicio", "nombre": "Inicio"})
        if nodos and nodos[1:]:
            aristas.insert(0, {"source": "inicio", "target": "act_0", "tipo": "secuencia"})
        nodos.append({"id": "fin", "tipo": "fin", "nombre": "Fin"})
        if nodos and len(nodos) > 2:
            last_act = f"act_{min(len(actividades), 30) - 1}"
            aristas.append({"source": last_act, "target": "fin", "tipo": "secuencia"})

        return {
            "proceso": proceso,
            "documentos_base": len(docs),
            "actividades": len(actividades),
            "nodos": nodos,
            "aristas": aristas,
        }

    # ──────────────────────────────────────────────
    # Base de conocimiento de hallazgos
    # ──────────────────────────────────────────────

    def registrar_hallazgo(self, titulo: str, descripcion: str, tipo: str = "",
                          severidad: str = "", proceso: str = "",
                          documento_origen: str = "", auditoria: str = "",
                          fecha_deteccion: str = "") -> dict:
        """Registra un hallazgo de auditoria."""
        codigo = f"HAL-{datetime.now().strftime('%Y%m%d')}-{self._next_hallazgo_id()}"
        self.conn.execute("""
            INSERT INTO hallazgos (codigo, titulo, descripcion, tipo, severidad, proceso,
                                   documento_origen, auditoria, fecha_deteccion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (codigo, titulo, descripcion, tipo, severidad, proceso,
              documento_origen, auditoria, fecha_deteccion or datetime.now().strftime("%Y-%m-%d")))
        self.conn.commit()
        return {"ok": True, "codigo": codigo}

    def _next_hallazgo_id(self) -> str:
        """Genera el siguiente ID secuencial de hallazgo."""
        count = self.conn.execute("SELECT COUNT(*) FROM hallazgos").fetchone()[0]
        return f"{count + 1:04d}"

    def listar_hallazgos(self, estado: str = "", proceso: str = "", limit: int = 100) -> list[dict]:
        """Lista hallazgos con filtros."""
        query = "SELECT codigo, titulo, descripcion, tipo, severidad, proceso, documento_origen, auditoria, fecha_deteccion, estado, capa_aplicada, fecha_cierre, leccion_aprendida FROM hallazgos WHERE 1=1"
        params = []

        if estado:
            query += " AND estado = ?"
            params.append(estado)
        if proceso:
            query += " AND proceso LIKE ?"
            params.append(f"%{proceso}%")

        query += " ORDER BY fecha_deteccion DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [
            {"codigo": r[0], "titulo": r[1], "descripcion": r[2], "tipo": r[3],
             "severidad": r[4], "proceso": r[5], "documento_origen": r[6],
             "auditoria": r[7], "fecha_deteccion": r[8], "estado": r[9],
             "capa_aplicada": r[10], "fecha_cierre": r[11], "leccion_aprendida": r[12]}
            for r in rows
        ]

    def cerrar_hallazgo(self, codigo: str, capa_aplicada: str, leccion_aprendida: str = "") -> dict:
        """Cierra un hallazgo con la CAPA aplicada."""
        self.conn.execute("""
            UPDATE hallazgos
            SET estado = 'Cerrado', capa_aplicada = ?, leccion_aprendida = ?,
                fecha_cierre = datetime('now', 'localtime')
            WHERE codigo = ?
        """, (capa_aplicada, leccion_aprendida, codigo))
        self.conn.commit()
        return {"ok": True, "mensaje": f"Hallazgo {codigo} cerrado"}

    # ──────────────────────────────────────────────
    # Matriz RACI automatica
    # ──────────────────────────────────────────────

    def matriz_raci(self, documento_codigo: str = "", proceso: str = "") -> dict:
        """Genera matriz RACI desde el contenido de los documentos.
        Extrae roles (elaborador, revisor, aprobador) y actividades.
        """
        if documento_codigo:
            rows = self.conn.execute("""
                SELECT codigo, nombre, contenido_texto, proceso_nom
                FROM procedimientos WHERE codigo = ?
            """, (documento_codigo,)).fetchall()
        elif proceso:
            rows = self.conn.execute("""
                SELECT codigo, nombre, contenido_texto, proceso_nom
                FROM procedimientos
                WHERE proceso_nom LIKE ? AND estado = 'P'
                ORDER BY nombre
            """, (f"%{proceso}%",)).fetchall()
        else:
            return {"error": "Especifica documento_codigo o proceso"}

        matriz = []
        for r in rows:
            codigo, nombre, texto, proc = r[0], r[1], r[2] or "", r[3]

            # Extraer responsables del documento
            # Buscar patrones: "Responsable: X", "Elaborado por: X", "Aprobado por: X"
            responsable = self._extraer_campo(texto, ["responsable", "elaborado por", "elaborador"])
            revisor = self._extraer_campo(texto, ["revisado por", "revisor"])
            aprobador = self._extraer_campo(texto, ["aprobado por", "aprobador"])

            # Extraer actividades
            actividades = self._extraer_actividades(texto)

            for act in actividades[:20]:  # limitar a 20 actividades por documento
                matriz.append({
                    "documento": codigo,
                    "proceso": proc,
                    "actividad": act,
                    "responsable": responsable,
                    "accountable": aprobador,
                    "consulted": revisor,
                    "informed": "",  # No se puede extraer automaticamente
                })

        return {
            "documento": documento_codigo,
            "proceso": proceso,
            "total_actividades": len(matriz),
            "matriz": matriz,
        }

    def _extraer_campo(self, texto: str, keywords: list[str]) -> str:
        """Extrae un campo (responsable, revisor, etc.) del texto."""
        for kw in keywords:
            pattern = rf'{kw}\s*[:\-]\s*([^\n]{{3,80}})'
            match = re.search(pattern, texto, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extraer_actividades(self, texto: str) -> list[str]:
        """Extrae actividades de un documento."""
        actividades = []
        for linea in texto.split("\n"):
            linea = linea.strip()
            if re.match(r'^\d+[\.\)]\s+', linea) and len(linea) > 15:
                act = re.sub(r'^\d+[\.\)]\s+', '', linea)
                if len(act) < 200:
                    actividades.append(act)
        return actividades

    # ──────────────────────────────────────────────
    # Indicadores automaticos (KPIs)
    # ──────────────────────────────────────────────

    def indicadores_kpi(self) -> dict:
        """Calcula KPIs desde los documentos y datos disponibles."""
        kpis = {}

        # 1. Total documentos vigentes
        total_vigentes = self.conn.execute(
            "SELECT COUNT(*) FROM procedimientos WHERE estado = 'P'"
        ).fetchone()[0]
        kpis["documentos_vigentes"] = {"valor": total_vigentes, "unidad": "docs", "meta": None}

        # 2. Total documentos obsoletos
        total_obsoletos = self.conn.execute(
            "SELECT COUNT(*) FROM procedimientos WHERE estado = 'O'"
        ).fetchone()[0]
        kpis["documentos_obsoletos"] = {"valor": total_obsoletos, "unidad": "docs", "meta": 0}

        # 3. Documentos por vencer (30 dias)
        por_vencer = self.conn.execute("""
            SELECT COUNT(*) FROM procedimientos
            WHERE vigencia_dias IS NOT NULL AND vigencia_dias >= 0 AND vigencia_dias <= 30
        """).fetchone()[0]
        kpis["documentos_por_vencer"] = {"valor": por_vencer, "unidad": "docs", "meta": 0}

        # 4. Documentos vencidos
        vencidos = self.conn.execute("""
            SELECT COUNT(*) FROM procedimientos
            WHERE vigencia_dias IS NOT NULL AND vigencia_dias < 0
        """).fetchone()[0]
        kpis["documentos_vencidos"] = {"valor": vencidos, "unidad": "docs", "meta": 0}

        # 5. Total procesos
        total_procesos = self.conn.execute(
            "SELECT COUNT(DISTINCT proceso_nom) FROM procedimientos WHERE proceso_nom IS NOT NULL"
        ).fetchone()[0]
        kpis["procesos_activos"] = {"valor": total_procesos, "unidad": "procesos", "meta": None}

        # 6. Promedio de documentos por proceso
        if total_procesos > 0:
            prom_docs = total_vigentes / total_procesos
            kpis["prom_docs_por_proceso"] = {"valor": round(prom_docs, 1), "unidad": "docs/proceso", "meta": None}

        # 7. Hallazgos abiertos
        hallazgos_abiertos = self.conn.execute(
            "SELECT COUNT(*) FROM hallazgos WHERE estado = 'Abierto'"
        ).fetchone()[0]
        kpis["hallazgos_abiertos"] = {"valor": hallazgos_abiertos, "unidad": "hallazgos", "meta": 0}

        # 8. Hallazgos cerrados
        hallazgos_cerrados = self.conn.execute(
            "SELECT COUNT(*) FROM hallazgos WHERE estado = 'Cerrado'"
        ).fetchone()[0]
        kpis["hallazgos_cerrados"] = {"valor": hallazgos_cerrados, "unidad": "hallazgos", "meta": None}

        # 9. Tasa de cierre de hallazgos
        total_hallazgos = hallazgos_abiertos + hallazgos_cerrados
        if total_hallazgos > 0:
            tasa_cierre = (hallazgos_cerrados / total_hallazgos) * 100
            kpis["tasa_cierre_hallazgos"] = {"valor": round(tasa_cierre, 1), "unidad": "%", "meta": 90}

        # 10. Tiempo promedio de cierre de hallazgos (dias)
        tiempo_cierre = self.conn.execute("""
            SELECT AVG(julianday(fecha_cierre) - julianday(fecha_deteccion))
            FROM hallazgos WHERE estado = 'Cerrado' AND fecha_cierre IS NOT NULL
        """).fetchone()[0]
        if tiempo_cierre:
            kpis["tiempo_prom_cierre_hallazgos"] = {"valor": round(tiempo_cierre, 1), "unidad": "dias", "meta": 30}

        # 11. Documentos con resumen ejecutivo
        try:
            docs_con_resumen = self.conn.execute(
                "SELECT COUNT(DISTINCT codigo) FROM resumenes"
            ).fetchone()[0]
        except Exception:
            docs_con_resumen = 0
        kpis["docs_con_resumen"] = {"valor": docs_con_resumen, "unidad": "docs", "meta": total_vigentes}

        # 12. Cobertura de resumenes
        if total_vigentes > 0:
            cobertura = (docs_con_resumen / total_vigentes) * 100
            kpis["cobertura_resumenes"] = {"valor": round(cobertura, 1), "unidad": "%", "meta": 100}

        return kpis
