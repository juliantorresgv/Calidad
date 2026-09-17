import re
from datetime import date, datetime
from typing import Any, Optional

from integra_db_client import IntegraDBClient


# Leyenda inferida; D y Z quedan marcados como inciertos hasta confirmar con el usuario
ESTADO_LABELS: dict[str, str] = {
    "E": "Elaborado",
    "D": "Devuelto / con observaciones",
    "R": "Revisado por responsable de proceso",
    "Q": "Revisado por Calidad / QA",
    "A": "Aprobado gerencial",
    "P": "Publicado",
    "O": "Obsoleto",
    "Z": "Estado especial (por confirmar)",
}


def _rtrim(value: Any) -> Any:
    if isinstance(value, str):
        return value.rstrip()
    return value


def _clean_date(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        if value.year <= 1900:
            return None
        return value.isoformat()
    if isinstance(value, str):
        if value.startswith("1753-") or value.startswith("1900-"):
            return None
        return value
    return value


def _clean_row(row: list, columns: list[str]) -> dict[str, Any]:
    out = {}
    for col, val in zip(columns, row):
        val = _rtrim(val)
        if isinstance(col, str) and "fecha" in col.lower() or "fch" in col.lower() or "hora" in col.lower():
            val = _clean_date(val)
        out[col] = val
    return out


class ProcedimientosClient:
    """Consultas de solo lectura sobre la tabla PROCEDIMIENTOS de Integr@."""

    def __init__(self, db_client: Optional[IntegraDBClient] = None):
        self.db = db_client or IntegraDBClient()

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        result = self.db.query(sql, params, max_rows=500)
        columns = result["columns"]
        return [_clean_row(row, columns) for row in result["rows"]]

    def leyenda_estados(self) -> dict:
        return ESTADO_LABELS.copy()

    def resumen(self) -> dict:
        """Totales y conteos por estado, proceso y tipo de documento."""
        by_state = self._query(
            "SELECT PROCEDIMIENTOS_ESTADO AS estado, COUNT(*) AS total "
            "FROM dbo.PROCEDIMIENTOS GROUP BY PROCEDIMIENTOS_ESTADO ORDER BY total DESC"
        )
        for row in by_state:
            row["descripcion"] = ESTADO_LABELS.get(row.get("estado", ""), "Desconocido")
        total = self._query("SELECT COUNT(*) AS total FROM dbo.PROCEDIMIENTOS")[0]["total"]
        by_process = self._query(
            "SELECT TOP 20 TRIM(p.ProcesoCod) AS proceso, TRIM(pr.ProcesoNom) AS proceso_nombre, COUNT(*) AS total "
            "FROM dbo.PROCEDIMIENTOS p LEFT JOIN dbo.Proceso pr ON p.ProcesoCod = pr.ProcesoCod "
            "GROUP BY p.ProcesoCod, pr.ProcesoNom ORDER BY total DESC"
        )
        by_type = self._query(
            "SELECT td.TipoDocumento_Descr AS tipo, COUNT(*) AS total "
            "FROM dbo.PROCEDIMIENTOS p LEFT JOIN dbo.TipoDocumento td ON p.TipoDocumento_Id = td.TipoDocumento_Id "
            "GROUP BY td.TipoDocumento_Descr ORDER BY total DESC"
        )
        return {
            "total": total,
            "por_estado": by_state,
            "por_proceso": by_process,
            "por_tipo": by_type,
        }

    def buscar(
        self,
        codigo: Optional[str] = None,
        nombre: Optional[str] = None,
        estado: Optional[str] = None,
        proceso: Optional[str] = None,
        tipo: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        where: list[str] = []
        params: list[Any] = []

        if codigo:
            where.append("TRIM(p.PROCEDIMIENTOS_COD) LIKE ?")
            params.append(f"%{codigo.strip()}%")
        if nombre:
            where.append("TRIM(p.PROCEDIMIENTOS_NOMBRE) LIKE ?")
            params.append(f"%{nombre.strip()}%")
        if estado:
            where.append("p.PROCEDIMIENTOS_ESTADO = ?")
            params.append(estado.strip().upper())
        if proceso:
            where.append("TRIM(p.ProcesoCod) = ?")
            params.append(proceso.strip())
        if tipo:
            where.append("(td.TipoDocumento_Descr LIKE ? OR p.TipoDocumento_Id = ?)")
            params.append(f"%{tipo.strip()}%")
            # intentamos convertir a int por si pasan el id
            try:
                params.append(int(tipo.strip()))
            except ValueError:
                params.append(-1)

        sql = (
            "SELECT TOP (?) TRIM(p.PROCEDIMIENTOS_COD) AS codigo, "
            "TRIM(p.PROCEDIMIENTOS_NOMBRE) AS nombre, "
            "p.PROCEDIMIENTOS_ESTADO AS estado, "
            "TRIM(pr.ProcesoNom) AS proceso, "
            "td.TipoDocumento_Descr AS tipo_documento, "
            "p.PROCEDIMIENTOS_FCHELBABORACION AS fecha_elaboracion, "
            "p.PROCEDIMIENTOS_FCHPUBLICACION AS fecha_publicacion "
            "FROM dbo.PROCEDIMIENTOS p "
            "LEFT JOIN dbo.Proceso pr ON p.ProcesoCod = pr.ProcesoCod "
            "LEFT JOIN dbo.TipoDocumento td ON p.TipoDocumento_Id = td.TipoDocumento_Id"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY p.PROCEDIMIENTOS_FCHELBABORACION DESC"

        params.insert(0, limit)
        resultados = self._query(sql, tuple(params))
        for r in resultados:
            r["estado_descripcion"] = ESTADO_LABELS.get(r.get("estado", ""), "Desconocido")
        return resultados

    def detalle(self, codigo: str) -> dict:
        """Devuelve la información completa de un procedimiento sin el contenido HTML."""
        cod = codigo.strip()
        rows = self._query(
            "SELECT "
            "TRIM(p.PROCEDIMIENTOS_COD) AS codigo, "
            "TRIM(p.PROCEDIMIENTOS_NOMBRE) AS nombre, "
            "p.PROCEDIMIENTOS_ESTADO AS estado, "
            "TRIM(p.ProcesoCod) AS proceso_cod, "
            "TRIM(pr.ProcesoNom) AS proceso, "
            "td.TipoDocumento_Descr AS tipo_documento, "
            "p.PROCEDIMIENTOS_VIGENCIA AS vigencia_dias, "
            "p.PROCEDIMIENTOS_FCHELBABORACION AS fecha_elaboracion, "
            "p.PROCEDIMIENTOS_FCHREVISIONPROC AS fecha_revision_proc, "
            "p.PROCEDIMIENTOS_FECHREVISIONCAL AS fecha_revision_calidad, "
            "p.PROCEDIMIENTOS_FCHAPROGERENCIA AS fecha_aprob_gerencia, "
            "p.PROCEDIMIENTOS_FCHPUBLICACION AS fecha_publicacion, "
            "p.PROCEDIMIENTOS_FCHOBSOLETO AS fecha_obsoleto, "
            "p.PROCEDIMIENTOS_OBSERVACION AS observacion, "
            "TRIM(el.UsrDscC) AS elaborador, "
            "TRIM(rev.UsrDscC) AS revisor_proceso, "
            "TRIM(revcal.UsrDscC) AS revisor_calidad, "
            "TRIM(apro.UsrDscC) AS aprobador_gerencia, "
            "TRIM(pub.UsrDscC) AS publicador "
            "FROM dbo.PROCEDIMIENTOS p "
            "LEFT JOIN dbo.Proceso pr ON p.ProcesoCod = pr.ProcesoCod "
            "LEFT JOIN dbo.TipoDocumento td ON p.TipoDocumento_Id = td.TipoDocumento_Id "
            "LEFT JOIN dbo.TUsuarioC el ON p.PROCEDIMIENTOS_ELABORADOR = el.UsrCdgC "
            "LEFT JOIN dbo.TUsuarioC rev ON p.PROCEDIMIENTOS_REVISORPROC = rev.UsrCdgC "
            "LEFT JOIN dbo.TUsuarioC revcal ON p.PROCEDIMIENTOS_REVISIONCALIDAD = revcal.UsrCdgC "
            "LEFT JOIN dbo.TUsuarioC apro ON p.PROCEDIMIENTOS_APROGERENCIA = apro.UsrCdgC "
            "LEFT JOIN dbo.TUsuarioC pub ON p.PROCEDIMIENTOS_PUBLICACION = pub.UsrCdgC "
            "WHERE TRIM(p.PROCEDIMIENTOS_COD) = ?",
            (cod,),
        )
        if not rows:
            return {"error": f"No se encontró el procedimiento '{cod}'"}

        det = rows[0]
        det["estado_descripcion"] = ESTADO_LABELS.get(det.get("estado", ""), "Desconocido")

        # Relacionados
        det["formatos"] = self._query(
            "SELECT TRIM(f.ForCalCod) AS formato_cod FROM dbo.PROCEDIMIENTOSFORMATO f WHERE TRIM(f.PROCEDIMIENTOS_COD) = ?",
            (cod,),
        )
        det["anexos"] = self._query(
            "SELECT TRIM(a.ANEXO_NOM) AS anexo FROM dbo.PROCEDIMIENTOSANEXO a WHERE TRIM(a.PROCEDIMIENTOS_COD) = ?",
            (cod,),
        )
        det["normas"] = self._query(
            "SELECT TRIM(n.NormaCod) AS norma_cod, TRIM(n.NormaNumeral) AS numeral FROM dbo.PROCEDIMIENTOSNORMAS n WHERE TRIM(n.PROCEDIMIENTOS_COD) = ?",
            (cod,),
        )
        det["centros_consulta"] = self._query(
            "SELECT TRIM(c.AreaCod) AS area_cod FROM dbo.PROCEDIMIENTOSCENTROCONSULTA c WHERE TRIM(c.PROCEDIMIENTOS_COD) = ?",
            (cod,),
        )
        det["cambios"] = self._query(
            "SELECT PROCE_CAMBIOCONS AS consecutivo, PROCE_CAMBIOFCH AS fecha, TRIM(u.UsrDscC) AS usuario, "
            "LEFT(TRIM(PROCE_CAMBIOOBSERV), 200) AS observacion "
            "FROM dbo.PROCEDIMIENTOSCAMBIO c LEFT JOIN dbo.TUsuarioC u ON c.PROCE_CAMBIOUSR = u.UsrCdgC "
            "WHERE TRIM(c.PROCEDIMIENTOS_COD) = ? ORDER BY PROCE_CAMBIOCONS",
            (cod,),
        )
        return det

    def flujo(self, codigo: str) -> list[dict]:
        """Historial de estados de un procedimiento (tabla ProcedimientoEstado)."""
        cod = codigo.strip()
        return self._query(
            "SELECT e.ProceEstaCns AS consecutivo, e.ProceEstado AS estado, "
            "TRIM(u.UsrDscC) AS usuario, e.ProceEstadFch AS fecha "
            "FROM dbo.ProcedimientoEstado e "
            "LEFT JOIN dbo.TUsuarioC u ON e.ProceEstUsurio = u.UsrCdgC "
            "WHERE TRIM(e.Procecod) = ? ORDER BY e.ProceEstaCns",
            (cod,),
        )

    def contenido(self, codigo: str) -> Optional[str]:
        """Devuelve el contenido HTML de un procedimiento."""
        cod = codigo.strip()
        rows = self._query(
            "SELECT PROCEDIMIENTOS_WORD AS contenido FROM dbo.PROCEDIMIENTOS WHERE TRIM(PROCEDIMIENTOS_COD) = ?",
            (cod,),
        )
        if not rows:
            return None
        return rows[0].get("contenido")


def get_procedimiento_completo(sql_conn, codigo: str) -> Optional[dict]:
    """Descarga un procedimiento completo de Integr@ usando una conexion pyodbc directa.

    Args:
        sql_conn: conexion pyodbc a SQL Server Integr@
        codigo: codigo del procedimiento a descargar

    Returns:
        dict con codigo, nombre, estado, estado_desc, proceso_cod, proceso_nom,
        tipo_documento, contenido_html, contenido_texto, fecha_publicacion,
        vigencia_dias, fecha_elaboracion. None si no se encuentra.
    """
    from bs4 import BeautifulSoup

    cod = codigo.strip()
    cur = sql_conn.execute("""
        SELECT
            TRIM(p.PROCEDIMIENTOS_COD),
            TRIM(p.PROCEDIMIENTOS_NOMBRE),
            p.PROCEDIMIENTOS_ESTADO,
            TRIM(pr.ProcesoNom),
            TRIM(p.ProcesoCod),
            TRIM(td.TipoDocumento_Descr),
            p.PROCEDIMIENTOS_VIGENCIA,
            p.PROCEDIMIENTOS_FCHELBABORACION,
            p.PROCEDIMIENTOS_FCHPUBLICACION,
            p.PROCEDIMIENTOS_WORD
        FROM dbo.PROCEDIMIENTOS p
        LEFT JOIN dbo.Proceso pr ON TRIM(p.ProcesoCod) = TRIM(pr.ProcesoCod)
        LEFT JOIN dbo.TipoDocumento td ON p.TipoDocumento_Id = td.TipoDocumento_Id
        WHERE TRIM(p.PROCEDIMIENTOS_COD) = ?
    """, (cod,))

    row = cur.fetchone()
    if not row:
        return None

    codigo_db, nombre, estado, proceso_nom, proceso_cod, tipo_doc, \
        vigencia, fec_elab, fec_pub, html = row

    # Convertir HTML a texto plano
    texto = ""
    if html:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            texto = "\n".join(lines)
        except Exception:
            texto = ""

    def _fmt_date(d):
        if d is None:
            return None
        if isinstance(d, (date, datetime)):
            if d.year <= 1900:
                return None
            return d.isoformat()
        return str(d) if d else None

    return {
        "codigo": codigo_db,
        "nombre": nombre or "",
        "estado": estado or "",
        "estado_desc": ESTADO_LABELS.get(estado, ""),
        "proceso_cod": proceso_cod or "",
        "proceso_nom": proceso_nom or "",
        "tipo_documento": tipo_doc or "",
        "contenido_html": html or "",
        "contenido_texto": texto,
        "fecha_publicacion": _fmt_date(fec_pub),
        "fecha_elaboracion": _fmt_date(fec_elab),
        "vigencia_dias": vigencia or 0,
    }


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    client = ProcedimientosClient()
    print("Leyenda de estados:", client.leyenda_estados())
    print("Resumen:", client.resumen())
