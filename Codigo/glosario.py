"""
Glosario de dominio Calidad + Logística para el agente Integr@.
Contiene términos técnicos que el agente consulta antes de responder
para dar contexto preciso a las preguntas del usuario.

Se carga automáticamente en graph_rag.py.
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
# Glosario de términos de Calidad y Logística
# ──────────────────────────────────────────────

GLOSARIO = {
    # ─── Calificación de equipos ───
    "IQ": {
        "termino": "IQ (Installation Qualification)",
        "categoria": "Calificación de equipos",
        "definicion": "Calificación de Instalación. Verifica que el equipo está instalado correctamente según especificaciones del fabricante: conexiones eléctricas, neumáticas, ubicación, materiales, etc.",
        "relacionado": ["OQ", "PQ", "calificación", "equipo", "instalación"],
    },
    "OQ": {
        "termino": "OQ (Operational Qualification)",
        "categoria": "Calificación de equipos",
        "definicion": "Calificación de Operación. Verifica que el equipo funciona correctamente en todos los rangos operativos especificados: temperaturas, presiones, velocidades, alarmas, etc.",
        "relacionado": ["IQ", "PQ", "calificación", "operación", "rangos"],
    },
    "PQ": {
        "termino": "PQ (Performance Qualification)",
        "categoria": "Calificación de equipos",
        "definicion": "Calificación de Desempeño. Verifica que el equipo mantiene su rendimiento de forma consistente bajo condiciones reales de trabajo durante un período definido.",
        "relacionado": ["IQ", "OQ", "calificación", "desempeño", "rango"],
    },
    "calificacion": {
        "termino": "Calificación (Qualification)",
        "categoria": "Calificación de equipos",
        "definicion": "Proceso documentado que demuestra que un equipo funciona correctamente y produce resultados confiables. Incluye IQ, OQ y PQ.",
        "relacionado": ["IQ", "OQ", "PQ", "validación", "equipo"],
    },
    "validacion": {
        "termino": "Validación (Validation)",
        "categoria": "Calidad",
        "definicion": "Proceso documentado que proporciona alto grado de seguridad de que un proceso, sistema o equipo produce consistentemente un resultado que cumple con especificaciones predeterminadas.",
        "relacionado": ["calificación", "IQ", "OQ", "PQ", "GMP"],
    },

    # ─── Documentos de calidad ───
    "PGC": {
        "termino": "PGC (Procedimiento de Gestión de Calidad)",
        "categoria": "Documentos",
        "definicion": "Procedimiento maestro del sistema de gestión de calidad. Define cómo se realizan las actividades de calidad en la organización. Prefijo usado en Integr@ para documentos del proceso GC.",
        "relacionado": ["procedimiento", "calidad", "gestión", "GC"],
    },
    "FGC": {
        "termino": "FGC (Formato de Gestión de Calidad)",
        "categoria": "Documentos",
        "definicion": "Formato o plantilla asociada a un procedimiento de gestión de calidad. Prefijo usado en Integr@ para formatos del proceso GC.",
        "relacionado": ["PGC", "formato", "calidad", "GC"],
    },
    "procedimiento": {
        "termino": "Procedimiento",
        "categoria": "Documentos",
        "definicion": "Documento formal que describe cómo realizar una actividad específica de forma estandarizada. En Integr@ se almacena en la tabla PROCEDIMIENTOS con un código único (ej: PGC-16-15).",
        "relacionado": ["PGC", "formato", "manual", "instructivo"],
    },
    "formato": {
        "termino": "Formato",
        "categoria": "Documentos",
        "definicion": "Plantilla o documento asociado a un procedimiento que se usa para registrar información específica (registros, checklists, reportes). En Integr@ se identifican con prefijo F.",
        "relacionado": ["procedimiento", "PGC", "FGC", "registro"],
    },
    "base documental": {
        "termino": "Base Documental",
        "categoria": "Documentos",
        "definicion": "Conjunto estructurado de documentos que componen el sistema de gestión de calidad. En Integr@ es un tipo de documento (TipoDocumento) que incluye procedimientos, manuales, instructivos.",
        "relacionado": ["procedimiento", "documental", "calidad", "sistema"],
    },
    "regulatorio": {
        "termino": "Documento Regulatorio",
        "categoria": "Documentos",
        "definicion": "Documento que cumple con requisitos de autoridades regulatorias (INVIMA, FDA, ICH, etc.). En Integr@ es un tipo de documento distinto a la Base Documental.",
        "relacionado": ["INVIMA", "FDA", "normativa", "cumplimiento"],
    },

    # ─── No conformidades ───
    "no conformidad": {
        "termino": "No Conformidad (NC)",
        "categoria": "Gestión de calidad",
        "definicion": "Incumplimiento de un requisito especificado. Puede detectarse en auditorías, quejas, desviaciones de procesos, etc. En Integr@ se gestiona en las tablas NoConformidad, CorreccionNC, PlanesAccionNC.",
        "relacionado": ["corrección", "acción correctiva", "auditoría", "desviación"],
    },
    "correccion": {
        "termino": "Corrección",
        "categoria": "Gestión de calidad",
        "definicion": "Acción inmediata para eliminar una no conformidad detectada. Diferente de la acción correctiva, que elimina la causa raíz.",
        "relacionado": ["no conformidad", "acción correctiva", "NC"],
    },
    "accion correctiva": {
        "termino": "Acción Correctiva",
        "categoria": "Gestión de calidad",
        "definicion": "Acción para eliminar la causa de una no conformidad u otra situación indeseable, para prevenir su recurrencia.",
        "relacionado": ["no conformidad", "corrección", "acción preventiva", "CAPA"],
    },
    "accion preventiva": {
        "termino": "Acción Preventiva",
        "categoria": "Gestión de calidad",
        "definicion": "Acción para eliminar la causa de una potencial no conformidad, para prevenir su ocurrencia.",
        "relacionado": ["acción correctiva", "CAPA", "no conformidad"],
    },
    "CAPA": {
        "termino": "CAPA (Corrective and Preventive Action)",
        "categoria": "Gestión de calidad",
        "definicion": "Sistema de acciones correctivas y preventivas. Proceso estructurado para investigar y resolver no conformidades, incluyendo corrección inmediata, análisis de causa raíz y prevención de recurrencia.",
        "relacionado": ["acción correctiva", "acción preventiva", "no conformidad"],
    },

    # ─── Estados de documentos ───
    "elaborado": {
        "termino": "Estado: Elaborado (E)",
        "categoria": "Estados de documento",
        "definicion": "El documento ha sido creado pero aún no ha sido revisado. Es el estado inicial del flujo de aprobación.",
        "relacionado": ["revisado", "aprobado", "publicado", "estado"],
    },
    "devuelto": {
        "termino": "Estado: Devuelto (D)",
        "categoria": "Estados de documento",
        "definicion": "El documento fue devuelto con observaciones para corrección. Requiere modificación antes de continuar el flujo.",
        "relacionado": ["observación", "revisado", "elaborado", "estado"],
    },
    "revisado": {
        "termino": "Estado: Revisado (R)",
        "categoria": "Estados de documento",
        "definicion": "El documento ha sido revisado por el responsable del proceso. Pendiente de revisión por Calidad.",
        "relacionado": ["elaborado", "calidad", "aprobado", "estado"],
    },
    "publicado": {
        "termino": "Estado: Publicado (P)",
        "categoria": "Estados de documento",
        "definicion": "El documento está vigente y disponible para uso en la organización. Ha completado todo el flujo de aprobación.",
        "relacionado": ["aprobado", "vigente", "obsoleto", "estado"],
    },
    "obsoleto": {
        "termino": "Estado: Obsoleto (O)",
        "categoria": "Estados de documento",
        "definicion": "El documento ya no está vigente. Ha sido reemplazado por una versión más reciente o retirado del uso.",
        "relacionado": ["publicado", "vigente", "versión", "estado"],
    },

    # ─── Logística y almacenamiento ───
    "cadena frio": {
        "termino": "Cadena de Frío",
        "categoria": "Logística",
        "definicion": "Sistema logístico que mantiene productos a temperaturas controladas (refrigeración o congelación) durante almacenamiento y transporte. Crítico para productos farmacéuticos y biológicos.",
        "relacionado": ["refrigeración", "congelación", "temperatura", "almacenamiento"],
    },
    "almacenamiento": {
        "termino": "Almacenamiento",
        "categoria": "Logística",
        "definicion": "Proceso de guarda y conservación de productos en instalaciones adecuadas (bodegas, cuartos fríos, etc.) bajo condiciones controladas. En Integr@ se identifica con el proceso WH.",
        "relacionado": ["bodega", "cadena frío", "WH", "temperatura"],
    },
    "bodega": {
        "termino": "Bodega",
        "categoria": "Logística",
        "definicion": "Instalación física para almacenamiento de productos. En Integr@ los procedimientos de bodega se identifican con códigos como AC (Acondicionamiento), CF (Cuarto Frío), etc.",
        "relacionado": ["almacenamiento", "WH", "cuarto frío", "refrigeración"],
    },
    "cuarto frio": {
        "termino": "Cuarto Frío",
        "categoria": "Logística",
        "definicion": "Espacio climatizado para almacenamiento de productos que requieren control de temperatura (refrigeración 2-8°C o congelación -15°C a -25°C).",
        "relacionado": ["cadena frío", "refrigeración", "congelación", "temperatura"],
    },
    "LTL": {
        "termino": "LTL (Less Than Truckload)",
        "categoria": "Logística",
        "definicion": "Transporte de carga parcial. Envíos que no llenan un camión completo. En Integr@ es un proceso con código LTL.",
        "relacionado": ["transporte", "carga", "logística"],
    },
    "maquila": {
        "termino": "Maquila",
        "categoria": "Logística",
        "definicion": "Servicio de procesamiento, empaque o reempaque de productos. En Integr@ es un proceso con código MQ.",
        "relacionado": ["empaque", "procesamiento", "MQ"],
    },

    # ─── Normativas ───
    "GMP": {
        "termino": "GMP (Good Manufacturing Practices)",
        "categoria": "Normativas",
        "definicion": "Buenas Prácticas de Manufactura. Conjunto de regulaciones que aseguran que los productos se fabrican y controlan de forma consistente según estándares de calidad.",
        "relacionado": ["calidad", "INVIMA", "FDA", "normativa", "validación"],
    },
    "INVIMA": {
        "termino": "INVIMA",
        "categoria": "Normativas",
        "definicion": "Instituto Nacional de Vigilancia de Medicamentos y Alimentos de Colombia. Autoridad regulatoria que supervisa productos farmacéuticos, alimentos, dispositivos médicos, etc.",
        "relacionado": ["GMP", "regulatorio", "Colombia", "normativa"],
    },
    "FDA": {
        "termino": "FDA (Food and Drug Administration)",
        "categoria": "Normativas",
        "definicion": "Agencia federal de Estados Unidos que regula alimentos, medicamentos, cosméticos, dispositivos médicos, etc. Sus estándares son referencia global.",
        "relacionado": ["GMP", "regulatorio", "normativa", "cumplimiento"],
    },
    "ICH": {
        "termino": "ICH (International Council for Harmonisation)",
        "categoria": "Normativas",
        "definicion": "Consejo Internacional de Armonización. Organización que armoniza regulaciones farmacéuticas entre Europa, Japón y EE.UU.",
        "relacionado": ["GMP", "FDA", "normativa", "regulatorio"],
    },
    "ISO": {
        "termino": "ISO (International Organization for Standardization)",
        "categoria": "Normativas",
        "definicion": "Organización Internacional de Normalización. Desarrolla estándares internacionales. ISO 9001 es el estándar de gestión de calidad más conocido.",
        "relacionado": ["calidad", "normativa", "9001", "estándar"],
    },

    # ─── Procesos Integr@ ───
    "GC": {
        "termino": "GC (Gestión de Calidad)",
        "categoria": "Procesos Integr@",
        "definicion": "Proceso de Gestión de Calidad en Integr@. Incluye procedimientos del sistema de gestión, auditorías, no conformidades, indicadores, etc.",
        "relacionado": ["PGC", "FGC", "calidad", "proceso"],
    },
    "WH": {
        "termino": "WH (Almacenamiento / Warehousing)",
        "categoria": "Procesos Integr@",
        "definicion": "Proceso de Almacenamiento en Integr@. Incluye procedimientos de recepción, almacenamiento, despacho, control de temperatura, etc.",
        "relacionado": ["bodega", "almacenamiento", "cuarto frío", "cadena frío"],
    },
    "MQ": {
        "termino": "MQ (Maquila)",
        "categoria": "Procesos Integr@",
        "definicion": "Proceso de Maquila en Integr@. Incluye procedimientos de empaque, reempaque, procesamiento, etiquetado, etc.",
        "relacionado": ["maquila", "empaque", "procesamiento"],
    },
    "SR": {
        "termino": "SR (Gestión de Riesgo y Seguridad)",
        "categoria": "Procesos Integr@",
        "definicion": "Proceso de Gestión de Riesgo y Seguridad en Integr@. Incluye procedimientos de evaluación de riesgos, seguridad física, continuidad de negocio, etc.",
        "relacionado": ["riesgo", "seguridad", "proceso"],
    },
    "ST": {
        "termino": "ST (Seguridad y Salud en el Trabajo)",
        "categoria": "Procesos Integr@",
        "definicion": "Proceso de Seguridad y Salud en el Trabajo (SST) en Integr@. Incluye procedimientos de prevención de riesgos laborales, EPP, investigación de incidentes, etc.",
        "relacionado": ["seguridad", "salud ocupacional", "SST", "EPP"],
    },
    "RH": {
        "termino": "RH (Recursos Humanos)",
        "categoria": "Procesos Integr@",
        "definicion": "Proceso de Recursos Humanos en Integr@. Incluye procedimientos de selección, capacitación, evaluación de desempeño, bienestar, etc.",
        "relacionado": ["recursos humanos", "capacitación", "personal"],
    },

    # ─── Auditoría ───
    "auditoria": {
        "termino": "Auditoría",
        "categoria": "Gestión de calidad",
        "definicion": "Proceso sistemático, independiente y documentado para obtener evidencias y evaluarlas objetivamente, determinando el grado de cumplimiento de criterios de auditoría.",
        "relacionado": ["no conformidad", "calidad", "GMP", "ISO"],
    },
    "auditoria interna": {
        "termino": "Auditoría Interna",
        "categoria": "Gestión de calidad",
        "definicion": "Auditoría realizada por personal de la propia organización para evaluar la conformidad del sistema de gestión de calidad.",
        "relacionado": ["auditoría", "calidad", "ISO", "9001"],
    },

    # ─── Trazabilidad ───
    "trazabilidad": {
        "termino": "Trazabilidad",
        "categoria": "Gestión de calidad",
        "definicion": "Capacidad de seguir la historia, aplicación o localización de un producto mediante identificaciones registradas. Crítico en logística farmacéutica.",
        "relacionado": ["lote", "serie", "cadena frío", "registro"],
    },
    "lote": {
        "termino": "Lote",
        "categoria": "Gestión de calidad",
        "definicion": "Cantidad definida de producto fabricado en un solo proceso bajo condiciones uniformes. Unidad de trazabilidad.",
        "relacionado": ["trazabilidad", "serie", "fabricación"],
    },

    # ─── Estabilidad ───
    "estabilidad": {
        "termino": "Estabilidad",
        "categoria": "Calidad farmacéutica",
        "definicion": "Capacidad de un producto para mantener sus propiedades fisicoquímicas y microbiológicas dentro de especificaciones durante su vida útil.",
        "relacionado": ["vida útil", "caducidad", "almacenamiento", "temperatura"],
    },
    "vida util": {
        "termino": "Vida Útil / Caducidad",
        "categoria": "Calidad farmacéutica",
        "definicion": "Período durante el cual un producto mantiene sus características de calidad bajo condiciones de almacenamiento especificadas.",
        "relacionado": ["estabilidad", "caducidad", "almacenamiento", "vigencia"],
    },

    # ─── Desviación ───
    "desviacion": {
        "termino": "Desviación",
        "categoria": "Gestión de calidad",
        "definicion": "Salida de un procedimiento, especificación o estándar aprobado. Debe ser investigada, documentada y evaluada para determinar impacto en calidad.",
        "relacionado": ["no conformidad", "especificación", "investigación", "CAPA"],
    },

    # ─── Estados de documentos Integr@ ───
    "estado E": {
        "termino": "Estado E - Elaborado",
        "categoria": "Estados de documento Integr@",
        "definicion": "El documento ha sido creado y elaborado por el responsable. Está en la fase inicial del flujo de aprobación. Aún no ha sido revisado ni aprobado. No es vigente.",
        "relacionado": ["estado D", "estado R", "estado P", "flujo de aprobación"],
    },
    "estado D": {
        "termino": "Estado D - Devuelto",
        "categoria": "Estados de documento Integr@",
        "definicion": "El documento fue devuelto con observaciones por el revisor. El elaborador debe corregir y reenviar. No es vigente mientras esté en este estado.",
        "relacionado": ["estado E", "estado R", "observaciones", "corrección"],
    },
    "estado R": {
        "termino": "Estado R - Revisado por responsable de proceso",
        "categoria": "Estados de documento Integr@",
        "definicion": "El documento ha sido revisado y validado por el responsable del proceso. Pendiente de revisión por Calidad (Q). No es vigente aún.",
        "relacionado": ["estado Q", "estado A", "estado P", "revisión", "calidad"],
    },
    "estado Q": {
        "termino": "Estado Q - Revisado por Calidad (QA)",
        "categoria": "Estados de documento Integr@",
        "definicion": "El documento ha sido revisado y aprobado por el área de Calidad (Quality Assurance). Pendiente de aprobación gerencial. No es vigente aún.",
        "relacionado": ["estado A", "estado R", "estado P", "QA", "calidad"],
    },
    "estado A": {
        "termino": "Estado A - Aprobado gerencial",
        "categoria": "Estados de documento Integr@",
        "definicion": "El documento ha sido aprobado por gerencia. Pendiente de publicación. No es vigente hasta que se publique (estado P).",
        "relacionado": ["estado P", "estado Q", "aprobación", "gerencia"],
    },
    "estado P": {
        "termino": "Estado P - Publicado (Vigente)",
        "categoria": "Estados de documento Integr@",
        "definicion": "El documento está publicado y vigente. Es la versión oficial y autorizada para uso operativo. Todos los documentos con estado P son considerados válidos y aplicables.",
        "relacionado": ["estado O", "vigencia", "publicación", "vigente"],
    },
    "estado O": {
        "termino": "Estado O - Obsoleto",
        "categoria": "Estados de documento Integr@",
        "definicion": "El documento ha sido declarado obsoleto y ya no está vigente. No debe usarse para operaciones. El agente excluye automáticamente todos los documentos con estado O de los resultados de búsqueda.",
        "relacionado": ["estado P", "obsoleto", "excluido", "no vigente"],
    },
    "estado Z": {
        "termino": "Estado Z - Especial / Pendiente",
        "categoria": "Estados de documento Integr@",
        "definicion": "Estado especial o transitorio. Su significado exacto requiere confirmación con el administrador de Integr@. Puede indicar documentos en transición, en revisión especial, o con un flujo no estándar.",
        "relacionado": ["estados Integr@", "transitorio", "especial"],
    },
    "estados integra": {
        "termino": "Estados de documentos en Integr@",
        "categoria": "Estados de documento Integr@",
        "definicion": "Los documentos en Integr@ siguen un flujo de aprobación: E (Elaborado) → D (Devuelto con observaciones) → R (Revisado por responsable de proceso) → Q (Revisado por Calidad) → A (Aprobado gerencial) → P (Publicado/Vigente). Un documento publicado puede pasar a O (Obsoleto) cuando es reemplazado o anulado. El estado Z es especial/transitorio.",
        "relacionado": ["estado E", "estado D", "estado R", "estado Q", "estado A", "estado P", "estado O", "estado Z"],
    },
    "flujo aprobacion": {
        "termino": "Flujo de aprobación de documentos",
        "categoria": "Estados de documento Integr@",
        "definicion": "Secuencia de aprobación: E (Elaborado) → R (Revisado por proceso) → Q (Revisado por Calidad) → A (Aprobado gerencial) → P (Publicado). Si hay observaciones en cualquier etapa, el documento vuelve a D (Devuelto) para corrección. Solo P es vigente.",
        "relacionado": ["estado E", "estado D", "estado R", "estado Q", "estado A", "estado P"],
    },
}


def instalar_glosario(db_path: Path = DB_PATH):
    """Guarda el glosario en SQLite para que el agente lo consulte."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS glosario (
            clave TEXT PRIMARY KEY,
            termino TEXT,
            categoria TEXT,
            definicion TEXT,
            relacionado TEXT
        )
    """)
    conn.execute("DELETE FROM glosario")

    for clave, info in GLOSARIO.items():
        conn.execute("""
            INSERT INTO glosario (clave, termino, categoria, definicion, relacionado)
            VALUES (?, ?, ?, ?, ?)
        """, (
            clave,
            info["termino"],
            info["categoria"],
            info["definicion"],
            json.dumps(info["relacionado"], ensure_ascii=False),
        ))

    conn.commit()
    print(f"Glosario instalado: {len(GLOSARIO)} términos")
    conn.close()


def buscar_termino(query: str, db_path: Path = DB_PATH) -> list[dict]:
    """Busca términos del glosario relevantes a una consulta."""
    query_lower = query.lower()
    resultados = []

    for clave, info in GLOSARIO.items():
        # Coincidencia por clave o términos relacionados
        if clave in query_lower:
            resultados.append(info)
            continue
        for rel in info["relacionado"]:
            if rel.lower() in query_lower:
                resultados.append(info)
                break

    return resultados


def glosario_para_contexto(query: str) -> str:
    """Genera texto del glosario para incluir en el contexto del LLM."""
    terminos = buscar_termino(query)
    if not terminos:
        return ""
    parts = ["GLOSARIO RELEVANTE:"]
    for t in terminos[:5]:  # máximo 5 términos
        parts.append(f"- {t['termino']}: {t['definicion']}")
    return "\n".join(parts)


if __name__ == "__main__":
    instalar_glosario()
    print("\nCategorías:")
    cats = {}
    for info in GLOSARIO.values():
        cats.setdefault(info["categoria"], 0)
        cats[info["categoria"]] += 1
    for cat, count in sorted(cats.items()):
        print(f"  {cat}: {count} términos")
