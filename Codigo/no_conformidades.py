"""
API de No Conformidades de Integr@.

Consulta las tablas NoConformidad, CorreccionNC y PlanesAccionNC de Integr@
para gestion completa de no conformidades, correcciones y planes de accion.

Tablas consultadas (SOLO LECTURA):
    - NoConformidad: registro de NCs
    - CorreccionNC: correcciones asociadas a cada NC
    - PlanesAccionNC: planes de accion para cada NC

Uso:
    from no_conformidades import NoConformidadesAPI
    api = NoConformidadesAPI()
    ncs = api.listar_ncs()
    nc = api.obtener_nc(codigo="NC-2024-001")
    stats = api.estadisticas_nc()
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from integra_db_client import IntegraDBClient


class NoConformidadesAPI:
    """API para consultar no conformidades de Integr@."""

    def __init__(self):
        self.client = IntegraDBClient()

    def _q(self, sql: str, params=None, max_rows: int = 500) -> list[list]:
        """Ejecuta query y devuelve lista de rows."""
        result = self.client.query(sql, params, max_rows=max_rows)
        return result.get("rows", [])

    def listar_ncs(self, estado: str = "", proceso: str = "", limit: int = 100) -> list[dict]:
        """Lista no conformidades con filtros opcionales."""
        sql = """
            SELECT
                NC.NC_Consecutivo,
                NC.NC_QUEPASO,
                NC.NC_Estado,
                NC.NC_FechCreacion,
                NC.TipoNC_Id,
                NC.ProcesoCod,
                P.ProcesoNom,
                NC.NC_Categoria,
                NC.NC_FechaDesviacion,
                NC.NC_DONDEPASO
            FROM NoConformidad NC
            LEFT JOIN Proceso P ON NC.ProcesoCod = P.ProcesoCod
            WHERE 1=1
        """
        params = []

        if estado:
            sql += " AND NC.NC_Estado = ?"
            params.append(int(estado) if estado.isdigit() else estado)

        if proceso:
            sql += " AND (P.ProcesoNom LIKE ? OR NC.ProcesoCod LIKE ?)"
            params.extend([f"%{proceso}%", f"%{proceso}%"])

        sql += " ORDER BY NC.NC_FechCreacion DESC"

        rows = self._q(sql, params, max_rows=limit)
        return [
            {
                "codigo": str(r[0] or "").strip(),
                "descripcion": r[1] or "",
                "estado": str(r[2]) if r[2] is not None else "",
                "fecha": str(r[3]) if r[3] else "",
                "tipo": str(r[4]) if r[4] is not None else "",
                "proceso_cod": str(r[5] or "").strip(),
                "proceso_nombre": str(r[6] or "").strip(),
                "categoria": str(r[7]) if r[7] is not None else "",
                "fecha_desviacion": str(r[8]) if r[8] else "",
                "lugar": r[9] or "",
            }
            for r in rows
        ][:limit]

    def obtener_nc(self, codigo: str) -> dict | None:
        """Obtiene una NC especifica con sus correcciones y planes de accion."""
        # NC principal
        rows = self._q("""
            SELECT
                NC.NC_Id, NC.NC_Consecutivo, NC.NC_QUEPASO, NC.NC_COMOPASO,
                NC.NC_DONDEPASO, NC.NC_CUANDOPASO, NC.NC_QUIEN,
                NC.NC_Estado, NC.NC_FechCreacion, NC.NC_FechaDesviacion,
                NC.ProcesoCod, P.ProcesoNom,
                NC.TipoNC_Id, NC.NC_Categoria, NC.NormaCod, NC.AreaCod
            FROM NoConformidad NC
            LEFT JOIN Proceso P ON NC.ProcesoCod = P.ProcesoCod
            WHERE NC.NC_Consecutivo = ?
        """, [codigo], max_rows=1)

        if not rows:
            return None

        r = rows[0]
        nc_id = r[0]
        nc = {
            "id": nc_id,
            "codigo": str(r[1] or "").strip(),
            "que_paso": r[2] or "",
            "como_paso": r[3] or "",
            "donde_paso": r[4] or "",
            "cuando_paso": r[5] or "",
            "quien": r[6] or "",
            "estado": str(r[7]) if r[7] is not None else "",
            "fecha_creacion": str(r[8]) if r[8] else "",
            "fecha_desviacion": str(r[9]) if r[9] else "",
            "proceso_cod": str(r[10] or "").strip(),
            "proceso_nombre": str(r[11] or "").strip(),
            "tipo": str(r[12]) if r[12] is not None else "",
            "categoria": str(r[13]) if r[13] is not None else "",
            "norma": str(r[14] or "").strip(),
            "area": str(r[15] or "").strip(),
            "correcciones": [],
            "planes_accion": [],
        }

        # Correcciones
        corr_rows = self._q("""
            SELECT
                CorreccionNC_Id, NC_Id, CorreccionNC_Fecha,
                CorreccionNC_Observa, CorreccionNC_Registro
            FROM CorreccionNC
            WHERE NC_Id = ?
            ORDER BY CorreccionNC_Fecha
        """, [nc_id])

        nc["correcciones"] = [
            {
                "id": c[0],
                "fecha": str(c[2]) if c[2] else "",
                "observacion": c[3] or "",
                "registro": str(c[4]) if c[4] is not None else "",
            }
            for c in corr_rows
        ]

        # Planes de accion
        plan_rows = self._q("""
            SELECT
                PlanesAccionNC_Id, NC_Id, PlanesAccionNC_RCA,
                PlanesAccionNC_Tipo, PlanesAccionNC_EstPA,
                PlanesAccionNC_FchRegistro, PlanesAccionNC_FchCompromiso,
                PlanesAccionNC_PAEjec, PlanesAccionNC_Aprobacion
            FROM PlanesAccionNC
            WHERE NC_Id = ?
            ORDER BY PlanesAccionNC_FchRegistro
        """, [nc_id])

        nc["planes_accion"] = [
            {
                "id": p[0],
                "rca": p[2] or "",
                "tipo": str(p[3] or "").strip(),
                "estado": str(p[4] or "").strip(),
                "fecha_registro": str(p[5]) if p[5] else "",
                "fecha_compromiso": str(p[6]) if p[6] else "",
                "accion_ejecutada": p[7] or "",
                "aprobacion": str(p[8]) if p[8] is not None else "",
            }
            for p in plan_rows
        ]

        return nc

    def estadisticas_nc(self) -> dict:
        """Estadisticas de no conformidades."""
        # Total por estado
        rows = self._q("""
            SELECT NC_Estado, COUNT(*)
            FROM NoConformidad
            GROUP BY NC_Estado
        """)
        por_estado = {str(r[0]) if r[0] is not None else "Sin estado": r[1] for r in rows}

        # Total por proceso
        rows = self._q("""
            SELECT P.ProcesoNom, COUNT(*)
            FROM NoConformidad NC
            LEFT JOIN Proceso P ON NC.ProcesoCod = P.ProcesoCod
            GROUP BY P.ProcesoNom
            ORDER BY COUNT(*) DESC
        """)
        por_proceso = {str(r[0] or "Sin proceso").strip(): r[1] for r in rows}

        # Total por categoria
        rows = self._q("""
            SELECT NC_Categoria, COUNT(*)
            FROM NoConformidad
            GROUP BY NC_Categoria
        """)
        por_categoria = {str(r[0]) if r[0] is not None else "Sin categoria": r[1] for r in rows}

        # Totales
        total = sum(por_estado.values())

        return {
            "total": total,
            "por_estado": por_estado,
            "por_proceso": por_proceso,
            "por_categoria": por_categoria,
        }

    def buscar_ncs(self, texto: str, limit: int = 50) -> list[dict]:
        """Busca NCs por texto en la descripcion (NC_QUEPASO)."""
        rows = self._q("""
            SELECT
                NC.NC_Consecutivo, NC.NC_QUEPASO, NC.NC_Estado,
                NC.NC_FechCreacion, P.ProcesoNom
            FROM NoConformidad NC
            LEFT JOIN Proceso P ON NC.ProcesoCod = P.ProcesoCod
            WHERE NC.NC_QUEPASO LIKE ?
               OR NC.NC_COMOPASO LIKE ?
               OR NC.NC_DONDEPASO LIKE ?
            ORDER BY NC.NC_FechCreacion DESC
        """, [f"%{texto}%", f"%{texto}%", f"%{texto}%"], max_rows=limit)

        return [
            {
                "codigo": str(r[0] or "").strip(),
                "descripcion": r[1] or "",
                "estado": str(r[2]) if r[2] is not None else "",
                "fecha": str(r[3]) if r[3] else "",
                "proceso_nombre": str(r[4] or "").strip(),
            }
            for r in rows
        ][:limit]
