"""
Diccionario bilingue Español/Ingles para el Agente de Calidad Integr@.

Traduce terminos de calidad HSEQ entre español e ingles.
Util para documentos de clientes internacionales y soporte multilingue.

Uso:
    from diccionario_bilingue import DiccionarioBilingue
    db = DiccionarioBilingue()
    db.traducir("Buenas Practicas de Manufactura", "es", "en")
    # -> "Good Manufacturing Practices"
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"


class DiccionarioBilingue:
    """Diccionario bilingue Español/Ingles de terminos HSEQ."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_table()
        self._poblar_si_vacio()

    def _init_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS diccionario_bilingue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                termino_es TEXT,
                termino_en TEXT,
                categoria TEXT,
                definicion_es TEXT,
                definicion_en TEXT,
                UNIQUE(termino_es, termino_en)
            )
        """)
        self.conn.commit()

    def _poblar_si_vacio(self):
        count = self.conn.execute("SELECT COUNT(*) FROM diccionario_bilingue").fetchone()[0]
        if count == 0:
            self._poblar_diccionario()

    def _poblar_diccionario(self):
        """Puebla el diccionario con terminos HSEQ base."""
        terminos = [
            # Calidad
            ("Calidad", "Quality", "Calidad", "Grado en que un conjunto de caracteristicas cumple requisitos.", "Degree to which a set of characteristics fulfills requirements."),
            ("Aseguramiento de Calidad", "Quality Assurance (QA)", "Calidad", "Actividades preventivas para garantizar calidad.", "Preventive activities to ensure quality."),
            ("Control de Calidad", "Quality Control (QC)", "Calidad", "Actividades tecnicas para verificar calidad.", "Technical activities to verify quality."),
            ("No Conformidad", "Non-Conformity (NC)", "Calidad", "Incumplimiento de un requisito.", "Non-fulfillment of a requirement."),
            ("Accion Correctiva", "Corrective Action", "Calidad", "Accion para eliminar causa de NC detectada.", "Action to eliminate detected NC cause."),
            ("Accion Preventiva", "Preventive Action", "Calidad", "Accion para eliminar causa de NC potencial.", "Action to eliminate potential NC cause."),
            ("CAPA", "CAPA (Corrective and Preventive Action)", "Calidad", "Acciones correctivas y preventivas.", "Corrective and preventive actions."),
            ("Hallazgo", "Finding", "Calidad", "Resultado de una auditoria.", "Result of an audit."),
            ("Auditoria", "Audit", "Calidad", "Evaluacion sistematica e independiente.", "Systematic and independent evaluation."),
            ("Auditor", "Auditor", "Calidad", "Persona calificada para conducir auditorias.", "Person qualified to conduct audits."),
            ("Auditor Lead", "Lead Auditor", "Calidad", "Auditor principal a cargo de la auditoria.", "Principal auditor in charge of the audit."),
            ("Desviacion", "Deviation", "Calidad", "Salida de un procedimiento aprobado.", "Departure from an approved procedure."),
            ("Investigacion", "Investigation", "Calidad", "Proceso para identificar causa raiz.", "Process to identify root cause."),
            ("Causa Raiz", "Root Cause", "Calidad", "Causa fundamental de un problema.", "Fundamental cause of a problem."),
            ("Mejora Continua", "Continuous Improvement", "Calidad", "Optimizacion recurrente del sistema.", "Recurrent system optimization."),

            # Regulatorio
            ("Buenas Practicas de Manufactura", "Good Manufacturing Practices (GMP)", "Regulatorio", "Normas de fabricacion de productos.", "Product manufacturing standards."),
            ("Buenas Practicas de Distribucion", "Good Distribution Practices (GDP)", "Regulatorio", "Normas de distribucion de productos.", "Product distribution standards."),
            ("Buenas Practicas de Laboratorio", "Good Laboratory Practices (GLP)", "Regulatorio", "Normas para laboratorios.", "Laboratory standards."),
            ("Buenas Practicas Clinicas", "Good Clinical Practices (GCP)", "Regulatorio", "Normas para ensayos clinicos.", "Clinical trial standards."),
            ("Cadena de Frio", "Cold Chain", "Logistica", "Transporte a temperatura controlada.", "Temperature-controlled transport."),
            ("Temperatura Controlada", "Controlled Temperature", "Logistica", "Mantenimiento de rango de temperatura.", "Maintaining temperature range."),
            ("Trazabilidad", "Traceability", "Regulatorio", "Seguimiento de producto en la cadena.", "Product tracking in the chain."),
            ("Lote", "Batch / Lot", "Regulatorio", "Cantidad definida de producto.", "Defined quantity of product."),
            ("Caducidad", "Expiration Date / Expiry", "Regulatorio", "Fecha de vencimiento del producto.", "Product expiration date."),
            ("Vencimiento", "Expiration / Expiry", "Regulatorio", "Fin de vida util del producto.", "End of product shelf life."),
            ("Recall", "Recall / Product Withdrawal", "Regulatorio", "Retiro de producto del mercado.", "Product withdrawal from market."),
            ("Estabilidad", "Stability", "Regulatorio", "Mantenimiento de caracteristicas en el tiempo.", "Characteristics maintenance over time."),
            ("Especificacion", "Specification", "Calidad", "Requisitos que debe cumplir un producto.", "Requirements a product must meet."),
            ("Protocolo", "Protocol", "Calidad", "Documento de metodologia de una actividad.", "Activity methodology document."),
            ("Informe", "Report", "Calidad", "Documento de resultados.", "Results document."),
            ("Muestreo", "Sampling", "Calidad", "Seleccion de muestras representativas.", "Selection of representative samples."),
            ("Inspeccion", "Inspection", "Calidad", "Verificacion contra criterios.", "Verification against criteria."),
            ("Validacion", "Validation", "Calidad", "Evidencia documentada de que un proceso funciona.", "Documented evidence a process works."),
            ("Calificacion", "Qualification", "Calidad", "Demuestra que equipo/sistema cumple requisitos.", "Demonstrates equipment meets requirements."),
            ("Calificacion de Instalacion", "Installation Qualification (IQ)", "Calidad", "Verifica instalacion correcta.", "Verifies correct installation."),
            ("Calificacion Operacional", "Operational Qualification (OQ)", "Calidad", "Verifica operacion correcta.", "Verifies correct operation."),
            ("Calificacion de Desempeno", "Performance Qualification (PQ)", "Calidad", "Verifica desempeno consistente.", "Verifies consistent performance."),

            # Logistica
            ("Picking", "Picking / Order Picking", "Logistica", "Seleccion de productos para pedido.", "Selecting products for order."),
            ("Packing", "Packing / Packaging", "Logistica", "Empaque de productos.", "Product packaging."),
            ("Despacho", "Dispatch / Shipping", "Logistica", "Salida de productos del almacen.", "Products leaving warehouse."),
            ("Recepcion", "Receiving / Goods Receipt", "Logistica", "Ingreso de productos al almacen.", "Products entering warehouse."),
            ("Almacenamiento", "Storage / Warehousing", "Logistica", "Guarda de productos.", "Product storage."),
            ("Inventario", "Inventory / Stock", "Logistica", "Cantidad de productos en almacen.", "Products in warehouse."),
            ("Primeras Entradas Primeras Salidas", "First In First Out (FIFO)", "Logistica", "Rotacion FIFO.", "FIFO rotation."),
            ("Primeras Vencimientos Primeras Salidas", "First Expired First Out (FEFO)", "Logistica", "Rotacion FEFO.", "FEFO rotation."),
            ("Ultimas Entradas Primeras Salidas", "Last In First Out (LIFO)", "Logistica", "Rotacion LIFO.", "LIFO rotation."),
            ("A Tiempo y Completo", "On Time In Full (OTIF)", "Logistica", "Entrega a tiempo y completa.", "On time and complete delivery."),
            ("Nivel de Servicio", "Service Level", "Logistica", "Porcentaje de pedidos cumplidos.", "Percentage of fulfilled orders."),
            ("Acuerdo de Nivel de Servicio", "Service Level Agreement (SLA)", "Gestion", "Acuerdo formal de servicio.", "Formal service agreement."),

            # Seguridad
            ("Seguridad y Salud en el Trabajo", "Occupational Health and Safety (OHS)", "Seguridad", "Prevencion de riesgos laborales.", "Workplace risk prevention."),
            ("Accidente Laboral", "Workplace Accident", "Seguridad", "Evento que causa lesion en trabajo.", "Event causing injury at work."),
            ("Incidente", "Incident / Near Miss", "Seguridad", "Evento que pudo causar dano.", "Event that could cause harm."),
            ("Evaluacion de Riesgos", "Risk Assessment", "Seguridad", "Identificacion y analisis de riesgos.", "Risk identification and analysis."),
            ("Matriz de Riesgo", "Risk Matrix", "Seguridad", "Clasificacion de riesgos.", "Risk classification."),
            ("Peligro", "Hazard", "Seguridad", "Fuente de dano potencial.", "Source of potential harm."),
            ("Riesgo", "Risk", "Seguridad", "Combinacion de probabilidad y severidad.", "Combination of probability and severity."),

            # Gestion
            ("Indicador Clave de Desempeno", "Key Performance Indicator (KPI)", "Gestion", "Metrica de cumplimiento de objetivos.", "Objective fulfillment metric."),
            ("Plan-Do-Check-Act", "Plan-Do-Check-Act (PDCA)", "Gestion", "Ciclo de mejora continua.", "Continuous improvement cycle."),
            ("Diagrama de Ishikawa", "Ishikawa Diagram / Fishbone Diagram", "Calidad", "Diagrama causa-efecto.", "Cause-effect diagram."),
            ("5 Porques", "5 Whys", "Calidad", "Tecnica de analisis de causa raiz.", "Root cause analysis technique."),
            ("Analisis de Pareto", "Pareto Analysis", "Calidad", "Regla 80/20.", "80/20 rule."),
            ("Poka-Yoke", "Poka-Yoke / Mistake Proofing", "Calidad", "A prueba de errores.", "Mistake proofing."),
            ("Kaizen", "Kaizen", "Calidad", "Mejora continua japonesa.", "Japanese continuous improvement."),
            ("FMEA", "Failure Mode and Effects Analysis (FMEA)", "Calidad", "Analisis de modos de falla.", "Failure mode analysis."),
            ("Numero de Prioridad de Riesgo", "Risk Priority Number (RPN)", "Calidad", "Prob x Sev x Det en FMEA.", "Prob x Sev x Det in FMEA."),

            # Normas
            ("Sistema de Gestion de Calidad", "Quality Management System (QMS)", "Normas", "ISO 9001.", "ISO 9001."),
            ("Sistema de Gestion Ambiental", "Environmental Management System (EMS)", "Normas", "ISO 14001.", "ISO 14001."),
            ("Sistema de Gestion SST", "Occupational Health and Safety Management System", "Normas", "ISO 45001.", "ISO 45001."),
            ("Auditoria Interna", "Internal Audit", "Calidad", "Auditoria por personal de la org.", "Audit by organization staff."),
            ("Auditoria Externa", "External Audit", "Calidad", "Auditoria por terceros.", "Audit by third parties."),

            # Documentos
            ("Procedimiento", "Procedure", "Documentos", "Documento que describe como hacer una actividad.", "Document describing how to do an activity."),
            ("Formato", "Form / Template", "Documentos", "Documento para registrar datos.", "Document to record data."),
            ("Manual", "Manual", "Documentos", "Documento de referencia.", "Reference document."),
            ("Instructivo", "Instruction / Work Instruction", "Documentos", "Documento operativo detallado.", "Detailed operational document."),
            ("Politica", "Policy", "Documentos", "Documento de directrices.", "Guidelines document."),
            ("Plan", "Plan", "Documentos", "Documento de planificacion.", "Planning document."),
            ("Reglamento", "Regulation", "Documentos", "Documento normativo.", "Regulatory document."),

            # Roles
            ("Responsable", "Responsible", "Roles", "Persona que ejecuta.", "Person who executes."),
            ("Aprobador", "Approver / Accountable", "Roles", "Persona que aprueba.", "Person who approves."),
            ("Revisor", "Reviewer", "Roles", "Persona que revisa.", "Person who reviews."),
            ("Elaborador", "Author / Preparer", "Roles", "Persona que elabora.", "Person who prepares."),
            ("Consultado", "Consulted", "Roles", "Persona consultada (RACI).", "Person consulted (RACI)."),
            ("Informado", "Informed", "Roles", "Persona informada (RACI).", "Person informed (RACI)."),

            # Estados Integr@
            ("Elaborado", "Drafted / Elaborated", "Estados", "Estado E en Integr@.", "Status E in Integra."),
            ("Devuelto", "Returned / Rejected", "Estados", "Estado D en Integr@.", "Status D in Integra."),
            ("Revisado", "Reviewed", "Estados", "Estado R en Integr@.", "Status R in Integra."),
            ("Aprobado", "Approved", "Estados", "Estado A en Integr@.", "Status A in Integra."),
            ("Publicado", "Published / Effective", "Estados", "Estado P en Integr@ (vigente).", "Status P in Integra (current)."),
            ("Obsoleto", "Obsolete", "Estados", "Estado O en Integr@.", "Status O in Integra."),
        ]

        for termino_es, termino_en, categoria, def_es, def_en in terminos:
            self.conn.execute("""
                INSERT OR IGNORE INTO diccionario_bilingue
                (termino_es, termino_en, categoria, definicion_es, definicion_en)
                VALUES (?, ?, ?, ?, ?)
            """, (termino_es, termino_en, categoria, def_es, def_en))

        self.conn.commit()

    def traducir(self, termino: str, origen: str = "es", destino: str = "en") -> str:
        """Traduce un termino entre español e ingles.
        origen: 'es' (español) o 'en' (ingles)
        destino: 'en' (ingles) o 'es' (español)
        """
        termino_lower = termino.lower().strip()

        if origen == "es" and destino == "en":
            row = self.conn.execute(
                "SELECT termino_en FROM diccionario_bilingue WHERE LOWER(termino_es) = ?",
                (termino_lower,)
            ).fetchone()
        elif origen == "en" and destino == "es":
            row = self.conn.execute(
                "SELECT termino_es FROM diccionario_bilingue WHERE LOWER(termino_en) = ?",
                (termino_lower,)
            ).fetchone()
        else:
            return termino

        return row[0] if row else termino

    def buscar(self, termino: str) -> list[dict]:
        """Busca terminos que contengan el texto (en español o ingles)."""
        termino_lower = f"%{termino.lower()}%"
        rows = self.conn.execute("""
            SELECT termino_es, termino_en, categoria, definicion_es, definicion_en
            FROM diccionario_bilingue
            WHERE LOWER(termino_es) LIKE ? OR LOWER(termino_en) LIKE ?
            ORDER BY categoria, termino_es
        """, (termino_lower, termino_lower)).fetchall()

        return [
            {"termino_es": r[0], "termino_en": r[1], "categoria": r[2],
             "definicion_es": r[3], "definicion_en": r[4]}
            for r in rows
        ]

    def listar_por_categoria(self, categoria: str = "") -> list[dict]:
        """Lista terminos por categoria."""
        if categoria:
            rows = self.conn.execute(
                "SELECT termino_es, termino_en, categoria FROM diccionario_bilingue WHERE categoria = ? ORDER BY termino_es",
                (categoria,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT termino_es, termino_en, categoria FROM diccionario_bilingue ORDER BY categoria, termino_es"
            ).fetchall()

        return [
            {"termino_es": r[0], "termino_en": r[1], "categoria": r[2]}
            for r in rows
        ]

    def categorias(self) -> list[str]:
        """Lista categorias disponibles."""
        rows = self.conn.execute(
            "SELECT DISTINCT categoria FROM diccionario_bilingue ORDER BY categoria"
        ).fetchall()
        return [r[0] for r in rows]

    def total(self) -> int:
        """Total de terminos en el diccionario."""
        return self.conn.execute("SELECT COUNT(*) FROM diccionario_bilingue").fetchone()[0]
