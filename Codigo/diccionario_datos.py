"""
Diccionario de datos de Integr@.
Describe cada columna de las tablas principales para que el agente
pueda interpretar campos correctamente al responder preguntas.

Se instala en SQLite tabla `diccionario_datos`.
"""
import json
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"

# ──────────────────────────────────────────────
# Diccionario de datos de Integr@
# ──────────────────────────────────────────────

DICCIONARIO = {
    # ─── Tabla PROCEDIMIENTOS ───
    "PROCEDIMIENTOS_COD": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_COD",
        "tipo": "varchar",
        "descripcion": "Código único del documento. Incluye versión (ej: PGC-16-15_V_02). Es la clave principal para identificar un procedimiento.",
        "ejemplo": "PGC-16-15_V_02",
        "obligatorio": True,
    },
    "PROCEDIMIENTOS_NOMBRE": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_NOMBRE",
        "tipo": "varchar",
        "descripcion": "Nombre descriptivo del documento. Título que aparece en Integr@.",
        "ejemplo": "SEGUIMIENTO A PROCESOS",
        "obligatorio": True,
    },
    "PROCEDIMIENTOS_ESTADO": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_ESTADO",
        "tipo": "char(1)",
        "descripcion": "Estado del documento en el flujo de aprobación. Valores: E=Elaborado, D=Devuelto, R=Revisado, Q=Revisado por Calidad, A=Aprobado, P=Publicado, O=Obsoleto, Z=Especial.",
        "valores": {"E": "Elaborado", "D": "Devuelto", "R": "Revisado", "Q": "Revisado por Calidad", "A": "Aprobado", "P": "Publicado", "O": "Obsoleto", "Z": "Especial"},
        "obligatorio": True,
    },
    "PROCEDIMIENTOS_WORD": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_WORD",
        "tipo": "varchar(max)",
        "descripcion": "Contenido del documento en formato HTML. Es el texto completo del procedimiento, formato o instructivo. La aplicación Integr@ renderiza este HTML y genera el PDF.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_ANTE": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_ANTE",
        "tipo": "varchar",
        "descripcion": "Código del documento anterior (versión previa). Permite trazar la cadena de versiones de un procedimiento.",
        "ejemplo": "PGC-16-15_V_01",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_VIGENCIA": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_VIGENCIA",
        "tipo": "int",
        "descripcion": "Vigencia del documento en días. Se suma a PROCEDIMIENTOS_FCHPUBLICACION para calcular la fecha de vencimiento.",
        "ejemplo": "1095",
        "obligatorio": False,
    },
    "ProcesoCod": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "ProcesoCod",
        "tipo": "varchar",
        "descripcion": "Código del proceso al que pertenece el documento. Relacionado con tabla Proceso.",
        "ejemplo": "GC",
        "obligatorio": True,
    },
    "TipoDocumento_Id": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "TipoDocumento_Id",
        "tipo": "int",
        "descripcion": "Identificador del tipo de documento. Relacionado con tabla TipoDocumento. Valores típicos: Base Documental, Regulatorio.",
        "obligatorio": True,
    },
    "PROCEDIMIENTOS_FCHELBABORACION": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_FCHELBABORACION",
        "tipo": "datetime",
        "descripcion": "Fecha de elaboración del documento. Cuando el creador lo redactó inicialmente.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_FCHREVISIONPROC": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_FCHREVISIONPROC",
        "tipo": "datetime",
        "descripcion": "Fecha de revisión por el responsable del proceso.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_FECHREVISIONCAL": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_FECHREVISIONCAL",
        "tipo": "datetime",
        "descripcion": "Fecha de revisión por el área de Calidad (QA).",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_FCHAPROGERENCIA": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_FCHAPROGERENCIA",
        "tipo": "datetime",
        "descripcion": "Fecha de aprobación gerencial.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_FCHPUBLICACION": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_FCHPUBLICACION",
        "tipo": "datetime",
        "descripcion": "Fecha de publicación del documento. Cuando quedó vigente y disponible para uso.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_FCHOBSOLETO": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_FCHOBSOLETO",
        "tipo": "datetime",
        "descripcion": "Fecha en que el documento quedó obsoleto. Si tiene valor, el documento ya no está vigente.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_ELABORADOR": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_ELABORADOR",
        "tipo": "varchar",
        "descripcion": "Usuario que elaboró el documento. Relacionado con tabla TUsuarioC.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_REVISORPROC": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_REVISORPROC",
        "tipo": "varchar",
        "descripcion": "Usuario responsable del proceso que revisó el documento.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_REVISIONCALIDAD": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_REVISIONCALIDAD",
        "tipo": "varchar",
        "descripcion": "Usuario de Calidad (QA) que revisó el documento.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_APROGERENCIA": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_APROGERENCIA",
        "tipo": "varchar",
        "descripcion": "Usuario gerencial que aprobó el documento.",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_PUBLICACION": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_PUBLICACION",
        "tipo": "varchar",
        "descripcion": "Usuario que publicó el documento (lo puso en vigencia).",
        "obligatorio": False,
    },
    "PROCEDIMIENTOS_OBSERVACION": {
        "tabla": "PROCEDIMIENTOS",
        "columna": "PROCEDIMIENTOS_OBSERVACION",
        "tipo": "text",
        "descripcion": "Observaciones generales del documento.",
        "obligatorio": False,
    },

    # ─── Tabla Proceso ───
    "ProcesoCod_Proceso": {
        "tabla": "Proceso",
        "columna": "ProcesoCod",
        "tipo": "varchar",
        "descripcion": "Código del proceso. Clave primaria.",
        "ejemplo": "GC, WH, MQ, SR, ST, RH, LTL, AFA, BR",
        "obligatorio": True,
    },
    "ProcesoNom": {
        "tabla": "Proceso",
        "columna": "ProcesoNom",
        "tipo": "varchar",
        "descripcion": "Nombre descriptivo del proceso.",
        "ejemplo": "GESTION DE CALIDAD",
        "obligatorio": True,
    },

    # ─── Tabla TipoDocumento ───
    "TipoDocumento_Descr": {
        "tabla": "TipoDocumento",
        "columna": "TipoDocumento_Descr",
        "tipo": "varchar",
        "descripcion": "Descripción del tipo de documento. Valores: Base Documental, Regulatorio.",
        "valores": {"Base Documental": "Documentos del sistema de gestión", "Regulatorio": "Documentos que cumplen requisitos regulatorios"},
        "obligatorio": True,
    },

    # ─── Tabla TUsuarioC ───
    "UsrCdgC": {
        "tabla": "TUsuarioC",
        "columna": "UsrCdgC",
        "tipo": "varchar",
        "descripcion": "Código único del usuario en Integr@.",
        "obligatorio": True,
    },
    "UsrDscC": {
        "tabla": "TUsuarioC",
        "columna": "UsrDscC",
        "tipo": "varchar",
        "descripcion": "Nombre completo del usuario.",
        "obligatorio": True,
    },

    # ─── Tabla PROCEDIMIENTOSANEXO ───
    "ANEXO_ARCHIVO": {
        "tabla": "PROCEDIMIENTOSANEXO",
        "columna": "ANEXO_ARCHIVO",
        "tipo": "varbinary(max)",
        "descripcion": "Archivo binario adjunto al procedimiento (PDF, Excel, imágenes). Contenido binario real.",
        "obligatorio": False,
    },
    "ANEXO_NOMBARCH": {
        "tabla": "PROCEDIMIENTOSANEXO",
        "columna": "ANEXO_NOMBARCH",
        "tipo": "varchar",
        "descripcion": "Nombre del archivo anexo.",
        "obligatorio": False,
    },
    "ANEXO_TIPO": {
        "tabla": "PROCEDIMIENTOSANEXO",
        "columna": "ANEXO_TIPO",
        "tipo": "varchar",
        "descripcion": "Tipo MIME del archivo anexo (ej: application/pdf, image/png).",
        "obligatorio": False,
    },

    # ─── Tabla PROCEDIMIENTOSFORMATO ───
    "FormatoCod": {
        "tabla": "PROCEDIMIENTOSFORMATO",
        "columna": "FormatoCod",
        "tipo": "varchar",
        "descripcion": "Código del formato asociado al procedimiento. Los formatos empiezan con F (ej: FGC-16-03).",
        "obligatorio": True,
    },

    # ─── Tabla PROCEDIMIENTOSNORMAS ───
    "NormaCod": {
        "tabla": "PROCEDIMIENTOSNORMAS",
        "columna": "NormaCod",
        "tipo": "varchar",
        "descripcion": "Código de la norma asociada al procedimiento (ej: ISO 9001, ICH Q7).",
        "obligatorio": True,
    },

    # ─── Tabla PROCEDIMIENTOSCAMBIO ───
    "CambioDescr": {
        "tabla": "PROCEDIMIENTOSCAMBIO",
        "columna": "CambioDescr",
        "tipo": "text",
        "descripcion": "Descripción del cambio realizado al documento. Historial de modificaciones.",
        "obligatorio": False,
    },

    # ─── Tabla ProcedimientoEstado ───
    "EstadoAnterior": {
        "tabla": "ProcedimientoEstado",
        "columna": "EstadoAnterior",
        "tipo": "char(1)",
        "descripcion": "Estado anterior del documento en el flujo de aprobación.",
        "obligatorio": False,
    },
    "EstadoNuevo": {
        "tabla": "ProcedimientoEstado",
        "columna": "EstadoNuevo",
        "tipo": "char(1)",
        "descripcion": "Estado nuevo al que transitó el documento.",
        "obligatorio": True,
    },
    "FechaCambio": {
        "tabla": "ProcedimientoEstado",
        "columna": "FechaCambio",
        "tipo": "datetime",
        "descripcion": "Fecha en que se realizó el cambio de estado.",
        "obligatorio": True,
    },

    # ─── Tabla NoConformidad ───
    "NCDescr": {
        "tabla": "NoConformidad",
        "columna": "NCDescr",
        "tipo": "text",
        "descripcion": "Descripción de la no conformidad detectada.",
        "obligatorio": True,
    },
    "NCFecha": {
        "tabla": "NoConformidad",
        "columna": "NCFecha",
        "tipo": "datetime",
        "descripcion": "Fecha de detección de la no conformidad.",
        "obligatorio": True,
    },
    "NCEstado": {
        "tabla": "NoConformidad",
        "columna": "NCEstado",
        "tipo": "varchar",
        "descripcion": "Estado de la NC: Abierta, En análisis, En acción, Cerrada.",
        "obligatorio": True,
    },

    # ─── Tabla DocumenExternos ───
    "DocumenExternosArch": {
        "tabla": "DocumenExternos",
        "columna": "DocumenExternosArch",
        "tipo": "varbinary(max)",
        "descripcion": "Archivo binario de documento externo (normas, regulaciones, manuales de fabricantes).",
        "obligatorio": False,
    },
}


def instalar_diccionario(db_path: Path = DB_PATH):
    """Guarda el diccionario en SQLite."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS diccionario_datos (
            clave TEXT PRIMARY KEY,
            tabla TEXT,
            columna TEXT,
            tipo TEXT,
            descripcion TEXT,
            ejemplo TEXT,
            valores TEXT,
            obligatorio INTEGER
        )
    """)
    conn.execute("DELETE FROM diccionario_datos")

    for clave, info in DICCIONARIO.items():
        conn.execute("""
            INSERT INTO diccionario_datos
            (clave, tabla, columna, tipo, descripcion, ejemplo, valores, obligatorio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            clave,
            info.get("tabla", ""),
            info.get("columna", ""),
            info.get("tipo", ""),
            info.get("descripcion", ""),
            info.get("ejemplo", ""),
            json.dumps(info.get("valores", {}), ensure_ascii=False) if info.get("valores") else None,
            1 if info.get("obligatorio") else 0,
        ))

    conn.commit()
    print(f"Diccionario instalado: {len(DICCIONARIO)} campos")

    # Resumen por tabla
    tablas = {}
    for info in DICCIONARIO.values():
        tablas.setdefault(info["tabla"], 0)
        tablas[info["tabla"]] += 1
    print("\nCampos por tabla:")
    for t, c in sorted(tablas.items()):
        print(f"  {t}: {c} campos")

    conn.close()


def buscar_campo(query: str, db_path: Path = DB_PATH) -> list[dict]:
    """Busca campos del diccionario relevantes a una consulta."""
    query_upper = query.upper()
    query_lower = query.lower()
    resultados = []

    for clave, info in DICCIONARIO.items():
        if clave.upper() in query_upper or info["columna"].upper() in query_upper:
            resultados.append(info)
        elif query_lower in info.get("descripcion", "").lower():
            resultados.append(info)

    return resultados[:10]


def diccionario_para_contexto(query: str) -> str:
    """Genera texto del diccionario para incluir en el contexto del LLM."""
    campos = buscar_campo(query)
    if not campos:
        return ""
    parts = ["DICCIONARIO DE DATOS RELEVANTE:"]
    for c in campos[:5]:
        parts.append(f"- {c['tabla']}.{c['columna']} ({c['tipo']}): {c['descripcion']}")
    return "\n".join(parts)


if __name__ == "__main__":
    instalar_diccionario()
