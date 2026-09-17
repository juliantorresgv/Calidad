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

    # ─── Terminos regulatorios: Invima, FDA, OMS ───
    "invima": {
        "termino": "INVIMA (Instituto Nacional de Vigilancia de Medicamentos y Alimentos)",
        "categoria": "Regulatorio",
        "definicion": "Entidad colombiana responsable de vigilar y controlar la calidad de medicamentos, alimentos, bebidas, cosméticos, dispositivos médicos y productos de aseo. Equivalente a la FDA en Colombia.",
        "relacionado": ["FDA", "OMS", "regulacion", "GMP"],
    },
    "fda": {
        "termino": "FDA (Food and Drug Administration)",
        "categoria": "Regulatorio",
        "definicion": "Agencia federal de Estados Unidos responsable de la regulación de alimentos, medicamentos, cosméticos, dispositivos médicos y productos biológicos. Estándar de referencia mundial.",
        "relacionado": ["INVIMA", "OMS", "GMP", "regulacion"],
    },
    "oms": {
        "termino": "OMS (Organización Mundial de la Salud)",
        "categoria": "Regulatorio",
        "definicion": "Organismo de Naciones Unidas especializado en gestionar y coordinar políticas de salud a nivel mundial. Emite guías técnicas, estándares de calidad y directrices para medicamentos y productos sanitarios.",
        "relacionado": ["FDA", "INVIMA", "GMP", "regulacion"],
    },
    "gmp": {
        "termino": "GMP (Good Manufacturing Practices / Buenas Prácticas de Manufactura)",
        "categoria": "Regulatorio",
        "definicion": "Conjunto de normas que aseguran que los productos se fabrican y controlan de forma consistente según estándares de calidad. Requisito regulatorio para la industria farmacéutica.",
        "relacionado": ["GDP", "GxP", "FDA", "INVIMA", "validacion"],
    },
    "gdp": {
        "termino": "GDP (Good Distribution Practices / Buenas Prácticas de Distribución)",
        "categoria": "Regulatorio",
        "definicion": "Normas que garantizan que la calidad de los productos farmacéuticos se mantiene durante el transporte, almacenamiento y distribución. Aplicable a CEDI y operaciones logísticas.",
        "relacionado": ["GMP", "GxP", "cadena de frio", "almacenamiento"],
    },
    "gxp": {
        "termino": "GxP (Buenas Prácticas)",
        "categoria": "Regulatorio",
        "definicion": "Termino general que abarca todas las buenas prácticas: GMP (manufactura), GDP (distribución), GLP (laboratorio), GCP (clínica), GAP (agricultura), etc.",
        "relacionado": ["GMP", "GDP", "GLP", "GCP"],
    },
    "glp": {
        "termino": "GLP (Good Laboratory Practices / Buenas Prácticas de Laboratorio)",
        "categoria": "Regulatorio",
        "definicion": "Sistema de gestión de calidad para laboratorios que realizan ensayos no clínicos de seguridad sanitaria y ambiental.",
        "relacionado": ["GxP", "GMP"],
    },
    "gcp": {
        "termino": "GCP (Good Clinical Practices / Buenas Prácticas Clínicas)",
        "categoria": "Regulatorio",
        "definicion": "Estándar internacional de calidad científica y ética para el diseño, registro y reporte de ensayos clínicos en humanos.",
        "relacionado": ["GxP", "GMP"],
    },
    "regulacion": {
        "termino": "Regulación farmacéutica",
        "categoria": "Regulatorio",
        "definicion": "Conjunto de normas, directrices y requisitos que regulan la fabricación, distribución y comercialización de productos farmacéuticos para garantizar su calidad, seguridad y eficacia.",
        "relacionado": ["INVIMA", "FDA", "OMS", "GMP", "GDP"],
    },
    "cadena de frio": {
        "termino": "Cadena de frío (Cold Chain)",
        "categoria": "Regulatorio / Logística",
        "definicion": "Sistema de transporte y almacenamiento que mantiene productos a temperatura controlada (2-8°C típicamente) desde el fabricante hasta el paciente final. Crítico para vacunas, insulina y biológicos.",
        "relacionado": ["GDP", "temperatura controlada", "cuarto frio", "monitorizacion"],
    },
    "temperatura controlada": {
        "termino": "Temperatura controlada",
        "categoria": "Regulatorio / Logística",
        "definicion": "Mantenimiento de productos en un rango de temperatura especificado (ej: 2-8°C, 15-25°C, -20°C) durante almacenamiento y transporte. Requiere monitoreo continuo y registros.",
        "relacionado": ["cadena de frio", "cuarto frio", "GDP", "monitorizacion"],
    },
    "cuarto frio": {
        "termino": "Cuarto frío (Cold Room)",
        "categoria": "Infraestructura",
        "definicion": "Espacio de almacenamiento con control de temperatura y humedad para productos que requieren cadena de frío. Debe contar con monitoreo, alarmas y respaldo de energía.",
        "relacionado": ["cadena de frio", "temperatura controlada", "almacenamiento"],
    },
    "monitorizacion": {
        "termino": "Monitoreo / Monitorización",
        "categoria": "Calidad",
        "definicion": "Registro continuo de variables críticas (temperatura, humedad, presión) para garantizar que se mantienen dentro de los rangos especificados. Incluye alarmas y desviaciones.",
        "relacionado": ["temperatura controlada", "cadena de frio", "desviacion"],
    },
    "desviacion": {
        "termino": "Desviación (Deviation)",
        "categoria": "Calidad",
        "definicion": "Salida de un procedimiento, especificación o estándar aprobado. Debe ser documentada, investigada y evaluada para impacto en calidad. Puede generar CAPA.",
        "relacionado": ["NC", "CAPA", "investigacion", "no conformidad"],
    },
    "investigacion": {
        "termino": "Investigación de desviación",
        "categoria": "Calidad",
        "definicion": "Proceso sistemático para identificar la causa raíz de una desviación o no conformidad. Incluye análisis, evidencia, conclusiones y acciones correctivas/preventivas.",
        "relacionado": ["desviacion", "causa raiz", "CAPA", "5 porques"],
    },
    "causa raiz": {
        "termino": "Causa raíz (Root Cause)",
        "categoria": "Calidad",
        "definicion": "Factor fundamental que originó una desviación o no conformidad. Se identifica mediante técnicas como 5 porqués, diagrama de Ishikawa, FMEA o análisis de Pareto.",
        "relacionado": ["investigacion", "CAPA", "5 porques", "ishikawa", "FMEA"],
    },
    "5 porques": {
        "termino": "5 Porqués (5 Whys)",
        "categoria": "Calidad",
        "definicion": "Técnica de análisis de causa raíz que consiste en preguntar 'por qué' 5 veces consecutivas hasta llegar a la causa fundamental de un problema.",
        "relacionado": ["causa raiz", "investigacion", "CAPA", "ishikawa"],
    },
    "ishikawa": {
        "termino": "Diagrama de Ishikawa (Causa-Efecto / Espina de Pescado)",
        "categoria": "Calidad",
        "definicion": "Diagrama que visualiza las causas de un problema organizadas por categorías (6M: Método, Máquina, Material, Mano de obra, Medición, Medio ambiente).",
        "relacionado": ["causa raiz", "5 porques", "FMEA", "investigacion"],
    },
    "pareto": {
        "termino": "Análisis de Pareto (Regla 80/20)",
        "categoria": "Calidad",
        "definicion": "Principio que establece que el 80% de los efectos provienen del 20% de las causas. Se usa para priorizar problemas y enfocar esfuerzos en las causas más impactantes.",
        "relacionado": ["causa raiz", "investigacion", "KPI"],
    },
    "poka yoke": {
        "termino": "Poka-Yoke (A prueba de errores)",
        "categoria": "Calidad",
        "definicion": "Mecanismo o diseño que previene errores humanos antes de que ocurran. Ej: conectores que solo encajan en una posición, alarmas de campo obligatorio.",
        "relacionado": ["CAPA", "prevencion", "calidad"],
    },
    "kaizen": {
        "termino": "Kaizen (Mejora Continua)",
        "categoria": "Calidad",
        "definicion": "Filosofía japonesa de mejora continua mediante pequeños cambios incrementales realizados por todos los miembros de la organización.",
        "relacionado": ["mejora continua", "PDCA", "calidad"],
    },
    "pdca": {
        "termino": "PDCA (Plan-Do-Check-Act)",
        "categoria": "Calidad",
        "definicion": "Ciclo de mejora continua: Planificar (definir objetivos), Hacer (implementar), Verificar (medir resultados), Actuar (ajustar y estandarizar). Base de ISO 9001.",
        "relacionado": ["kaizen", "mejora continua", "ISO 9001"],
    },
    "iso 9001": {
        "termino": "ISO 9001 (Sistemas de Gestión de Calidad)",
        "categoria": "Normas",
        "definicion": "Norma internacional que especifica requisitos para sistemas de gestión de calidad. Enfoque en satisfacción del cliente, mejora continua y enfoque basado en procesos.",
        "relacionado": ["ISO 45001", "PDCA", "calidad", "auditoria"],
    },
    "iso 45001": {
        "termino": "ISO 45001 (Seguridad y Salud en el Trabajo)",
        "categoria": "Normas",
        "definicion": "Norma internacional para sistemas de gestión de seguridad y salud ocupacional. Reemplaza a OHSAS 18001. Enfoque en prevención de lesiones y enfermedades laborales.",
        "relacionado": ["ISO 9001", "SST", "seguridad"],
    },
    "iso 14001": {
        "termino": "ISO 14001 (Gestión Ambiental)",
        "categoria": "Normas",
        "definicion": "Norma internacional para sistemas de gestión ambiental. Ayuda a organizaciones a reducir impacto ambiental, cumplir regulaciones y mejorar de forma continua.",
        "relacionado": ["ISO 9001", "HSEQ"],
    },
    "ohsas 18001": {
        "termino": "OHSAS 18001 (Salud y Seguridad Ocupacional)",
        "categoria": "Normas",
        "definicion": "Norma reemplazada por ISO 45001. Establecía requisitos para sistemas de gestión de seguridad y salud ocupacional.",
        "relacionado": ["ISO 45001", "SST"],
    },
    "sst": {
        "termino": "SST (Seguridad y Salud en el Trabajo)",
        "categoria": "Seguridad",
        "definicion": "Disciplina que previene accidentes y enfermedades laborales mediante identificación de peligros, evaluación de riesgos y controles.",
        "relacionado": ["ISO 45001", "HSEQ", "ARP", "accidente laboral"],
    },
    "hseq": {
        "termino": "HSEQ (Health, Safety, Environment, Quality)",
        "categoria": "Gestión",
        "definicion": "Sistema integrado que combina Salud, Seguridad, Ambiente y Calidad. HSEQ engloba ISO 9001 + ISO 14001 + ISO 45001 en un solo sistema de gestión.",
        "relacionado": ["ISO 9001", "ISO 14001", "ISO 45001", "SST"],
    },
    "arp": {
        "termino": "ARP (Análisis de Riesgo de Procesos)",
        "categoria": "Seguridad",
        "definicion": "Evaluación sistemática de riesgos en procesos para identificar peligros, evaluar consecuencias y definir controles. Base para prevención de accidentes.",
        "relacionado": ["SST", "riesgo", "evaluacion de riesgos"],
    },
    "evaluacion de riesgos": {
        "termino": "Evaluación de riesgos",
        "categoria": "Seguridad",
        "definicion": "Proceso de identificación de peligros, análisis de probabilidad y severidad, y determinación de controles necesarios. Metodologías: HAZOP, FMEA, matriz de riesgo.",
        "relacionado": ["ARP", "FMEA", "riesgo", "SST"],
    },
    "riesgo": {
        "termino": "Riesgo",
        "categoria": "Gestión",
        "definicion": "Combinación de probabilidad de ocurrencia y severidad de un evento no deseado. Se evalúa como Riesgo = Probabilidad × Severidad × Detección (NPR en FMEA).",
        "relacionado": ["evaluacion de riesgos", "FMEA", "NPR"],
    },
    "matriz de riesgo": {
        "termino": "Matriz de riesgo",
        "categoria": "Seguridad",
        "definicion": "Herramienta visual que cruza probabilidad vs severidad para clasificar riesgos en niveles (bajo, medio, alto, critico). Define prioridades de accion.",
        "relacionado": ["evaluacion de riesgos", "riesgo", "ARP"],
    },
    "accidente laboral": {
        "termino": "Accidente laboral",
        "categoria": "Seguridad",
        "definicion": "Evento súbito y violento que ocurre en el trabajo o en relación con este, causando lesión o muerte. Debe investigarse, reportarse y generar CAPA.",
        "relacionado": ["SST", "investigacion", "CAPA", "incidente"],
    },
    "incidente": {
        "termino": "Incidente",
        "categoria": "Seguridad",
        "definicion": "Evento que pudo causar daño pero no lo hizo (near miss). Debe investigarse para prevenir accidentes futuros. Base para mejora proactiva.",
        "relacionado": ["accidente laboral", "SST", "investigacion"],
    },
    "brm": {
        "termino": "BRM (Business Relationship Management)",
        "categoria": "Gestión",
        "definicion": "Gestión de relaciones con clientes y stakeholders. En logística farmacéutica, asegura alineación entre servicio y expectativas del cliente.",
        "relacionado": ["SLA", "cliente", "gestion"],
    },
    "sla": {
        "termino": "SLA (Service Level Agreement)",
        "categoria": "Gestión",
        "definicion": "Acuerdo formal que define el nivel de servicio esperado: tiempos de respuesta, disponibilidad, precisión, etc. Medible y vinculante.",
        "relacionado": ["KPI", "cliente", "gestion"],
    },
    "kpi": {
        "termino": "KPI (Key Performance Indicator)",
        "categoria": "Gestión",
        "definicion": "Indicador clave de desempeño que mide el grado de cumplimiento de objetivos. Ej: tasa de NC, tiempo de cierre CAPA, precisión de picking, OTIF.",
        "relacionado": ["SLA", "indicador", "metrica"],
    },
    "otif": {
        "termino": "OTIF (On Time In Full)",
        "categoria": "Logística",
        "definicion": "Indicador que mide si una entrega se hizo a tiempo (On Time) y completa (In Full). KPI critico en logística farmacéutica.",
        "relacionado": ["KPI", "despacho", "logistica"],
    },
    "picking": {
        "termino": "Picking",
        "categoria": "Logística",
        "definicion": "Proceso de seleccionar y extraer productos del almacen para preparar un pedido. Debe garantizar precisión (producto, cantidad, lote, caducidad).",
        "relacionado": ["packing", "despacho", "WMS", "OTIF"],
    },
    "packing": {
        "termino": "Packing (Empaque / Empaquetado)",
        "categoria": "Logística",
        "definicion": "Proceso de empacar los productos seleccionados en picking para preparar el despacho. Incluye verificacion, etiquetado y proteccion.",
        "relacionado": ["picking", "despacho", "WMS"],
    },
    "lote": {
        "termino": "Lote (Batch)",
        "categoria": "Regulatorio",
        "definicion": "Cantidad definida de producto fabricado en un mismo ciclo. Cada lote tiene un numero unico para trazabilidad. Permite recall si hay problemas de calidad.",
        "relacionado": ["trazabilidad", "caducidad", "recall", "GMP"],
    },
    "caducidad": {
        "termino": "Caducidad / Vencimiento (Expiration Date)",
        "categoria": "Regulatorio",
        "definicion": "Fecha hasta la cual el producto mantiene sus caracteristicas de calidad si se almacena correctamente. No debe usarse despues de esta fecha.",
        "relacionado": ["lote", "vigencia", "trazabilidad", "FEFO"],
    },
    "fefo": {
        "termino": "FEFO (First Expired First Out)",
        "categoria": "Logística",
        "definicion": "Metodo de rotacion de inventario que despacha primero los productos que vencen antes. Critico en farmacia para evitar vencimientos.",
        "relacionado": ["FIFO", "LIFO", "caducidad", "lote", "WMS"],
    },
    "fifo": {
        "termino": "FIFO (First In First Out)",
        "categoria": "Logística",
        "definicion": "Metodo de rotacion de inventario que despacha primero los productos que entraron primero. En farmacia se prefiere FEFO sobre FIFO.",
        "relacionado": ["FEFO", "LIFO", "WMS"],
    },
    "lifo": {
        "termino": "LIFO (Last In First Out)",
        "categoria": "Logística",
        "definicion": "Metodo de rotacion que despacha primero los productos que entraron ultimo. No recomendado para farmacia por riesgo de vencimiento.",
        "relacionado": ["FIFO", "FEFO"],
    },
    "recall": {
        "termino": "Recall (Retiro de producto)",
        "categoria": "Regulatorio",
        "definicion": "Proceso de retirar un producto del mercado por problemas de calidad o seguridad. Requiere trazabilidad total (lote, distribucion, clientes).",
        "relacionado": ["trazabilidad", "lote", "GMP", "GDP"],
    },
    "trazabilidad": {
        "termino": "Trazabilidad",
        "categoria": "Regulatorio",
        "definicion": "Capacidad de seguir el rastro de un producto en toda la cadena: desde materia prima hasta paciente final. Requisito regulatorio (GDP/GMP).",
        "relacionado": ["lote", "recall", "GMP", "GDP"],
    },
    "estabilidad": {
        "termino": "Estabilidad de producto",
        "categoria": "Regulatorio",
        "definicion": "Capacidad de un producto para mantener sus caracteristicas fisicas, quimicas y microbiologicas dentro de especificaciones durante su vida util.",
        "relacionado": ["caducidad", "almacenamiento", "GMP"],
    },
    "bioequivalente": {
        "termino": "Bioequivalente",
        "categoria": "Regulatorio",
        "definicion": "Producto que tiene la misma cantidad del mismo principio activo, forma farmaceutica y biodisponibilidad que el producto de referencia.",
        "relacionado": ["generico", "INVIMA", "FDA"],
    },
    "generico": {
        "termino": "Genérico",
        "categoria": "Regulatorio",
        "definicion": "Medicamento con el mismo principio activo, concentracion y forma farmaceutica que un producto de referencia, pero comercializado bajo nombre cientifico.",
        "relacionado": ["bioequivalente", "INVIMA", "FDA"],
    },
    "condiciones de almacenamiento": {
        "termino": "Condiciones de almacenamiento",
        "categoria": "Regulatorio / Logística",
        "definicion": "Requisitos de temperatura, humedad y luz que un producto necesita durante su almacenamiento. Ej: 2-8°C, 15-25°C, protegido de la luz.",
        "relacionado": ["temperatura controlada", "cadena de frio", "almacenamiento", "GDP"],
    },
    "muestreo": {
        "termino": "Muestreo",
        "categoria": "Calidad",
        "definicion": "Proceso de seleccionar muestras representativas de un lote para inspeccion o ensayo. Debe seguir procedimientos estadisticos y normativos.",
        "relacionado": ["inspeccion", "control de calidad", "lote"],
    },
    "inspeccion": {
        "termino": "Inspección",
        "categoria": "Calidad",
        "definicion": "Verificacion visual o fisica de productos, procesos o instalaciones contra criterios definidos. Puede ser 100% o por muestreo.",
        "relacionado": ["muestreo", "control de calidad", "auditoria"],
    },
    "control de calidad": {
        "termino": "Control de Calidad (QC)",
        "categoria": "Calidad",
        "definicion": "Conjunto de actividades tecnicas para verificar que productos y procesos cumplen especificaciones. Incluye ensayos, muestreo e inspeccion.",
        "relacionado": ["aseguramiento de calidad", "GMP", "inspeccion"],
    },
    "aseguramiento de calidad": {
        "termino": "Aseguramiento de Calidad (QA)",
        "categoria": "Calidad",
        "definicion": "Conjunto de actividades preventivas y sistematicas para garantizar que los procesos generan productos que cumplen requisitos de calidad. Diferente de QC (que es reactivo).",
        "relacionado": ["control de calidad", "GMP", "ISO 9001"],
    },
    "especificacion": {
        "termino": "Especificación",
        "categoria": "Calidad",
        "definicion": "Documento que define los requisitos que debe cumplir un producto: identidad, pureza, potencia, seguridad, estabilidad, etc.",
        "relacionado": ["control de calidad", "GMP", "validacion"],
    },
    "protocolo": {
        "termino": "Protocolo",
        "categoria": "Calidad",
        "definicion": "Documento que describe el proposito, metodologia, criterios de aceptacion y procedimientos de una actividad especifica (validacion, auditoria, ensayo).",
        "relacionado": ["validacion", "auditoria", "IQ", "OQ", "PQ"],
    },
    "informe": {
        "termino": "Informe / Reporte",
        "categoria": "Calidad",
        "definicion": "Documento que registra los resultados de una actividad: datos, analisis, conclusiones y recomendaciones. Debe ser objetivo y trazable.",
        "relacionado": ["protocolo", "auditoria", "investigacion"],
    },
    "accion correctiva": {
        "termino": "Acción Correctiva",
        "categoria": "Calidad",
        "definicion": "Accion tomada para eliminar la causa de una no conformidad detectada y prevenir su recurrencia. Parte de CAPA.",
        "relacionado": ["CAPA", "accion preventiva", "NC", "causa raiz"],
    },
    "accion preventiva": {
        "termino": "Acción Preventiva",
        "categoria": "Calidad",
        "definicion": "Accion tomada para eliminar la causa de una no conformidad potencial antes de que ocurra. Parte de CAPA.",
        "relacionado": ["CAPA", "accion correctiva", "prevencion"],
    },
    "prevencion": {
        "termino": "Prevención",
        "categoria": "Calidad",
        "definicion": "Conjunto de acciones proactivas para evitar que ocurran no conformidades, accidentes o desviaciones. Diferente de correccion (reactiva).",
        "relacionado": ["accion preventiva", "CAPA", "poka yoke"],
    },
    "eficacia": {
        "termino": "Eficacia",
        "categoria": "Calidad",
        "definicion": "Grado en que una accion logra el resultado esperado. En CAPA, se verifica que la accion implementada realmente elimino la causa raiz.",
        "relacionado": ["CAPA", "efectividad", "verificacion"],
    },
    "eficiencia": {
        "termino": "Eficiencia",
        "categoria": "Gestión",
        "definicion": "Relacion entre recursos utilizados y resultados obtenidos. En logistica, mide optimizacion de costos, tiempos y recursos.",
        "relacionado": ["eficacia", "KPI", "productividad"],
    },
    "efectividad": {
        "termino": "Efectividad",
        "categoria": "Gestión",
        "definicion": "Grado en que se alcanzan los objetivos planificados. Combina eficacia (lograr el resultado) y eficiencia (con recursos optimos).",
        "relacionado": ["eficacia", "eficiencia", "KPI"],
    },
    "productividad": {
        "termino": "Productividad",
        "categoria": "Gestión",
        "definicion": "Relacion entre output e input. En logistica: unidades procesadas por hora, pedidos completados por dia, etc.",
        "relacionado": ["eficiencia", "KPI", "OTIF"],
    },
    "mejora continua": {
        "termino": "Mejora Continua",
        "categoria": "Gestión",
        "definicion": "Proceso recurrente de optimizacion del sistema de gestion. Base de PDCA, Kaizen, ISO 9001. Busca mejorar productos, procesos y resultados.",
        "relacionado": ["PDCA", "kaizen", "ISO 9001"],
    },
    "competencia": {
        "termino": "Competencia (personal)",
        "categoria": "Calidad",
        "definicion": "Conocimientos, habilidades y actitudes demostradas que capacitan a una persona para realizar una tarea. Requiere formacion, evaluacion y registros.",
        "relacionado": ["formacion", "capacitacion", "GMP"],
    },
    "formacion": {
        "termino": "Formación / Capacitación",
        "categoria": "Calidad",
        "definicion": "Proceso de desarrollar competencias en el personal. En GMP/GDP, debe ser planificada, ejecutada, evaluada y registrada.",
        "relacionado": ["competencia", "GMP", "capacitacion"],
    },
    "induccion": {
        "termino": "Inducción",
        "categoria": "Gestión",
        "definicion": "Proceso de integracion de nuevo personal: presentacion de la empresa, politicas, procedimientos de seguridad y calidad.",
        "relacionado": ["formacion", "competencia", "SST"],
    },
    "reinduccion": {
        "termino": "Reinducción",
        "categoria": "Gestión",
        "definicion": "Proceso de actualizacion de conocimientos y procedimientos para personal existente cuando hay cambios significativos.",
        "relacionado": ["induccion", "formacion", "competencia"],
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
