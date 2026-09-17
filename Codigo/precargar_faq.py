"""
precargar_faq.py
================
Genera respuestas precargadas (FAQ) automaticamente usando OpenAI como
proveedor primario (igual que el chat del agente).

Uso:
    cd Codigo
    $env:OPENAI_API_KEY="..."
    $env:MISTRAL_API_KEY="..."
    python precargar_faq.py

El script:
  1. Carga GraphRAG con LLM primario = openai
  2. Recolecta ~400 preguntas desde usage_stats + plantillas de conceptos HSEQ
  3. Genera respuestas con rag.ask(pregunta, modo_rapido=True)
  4. Guarda en la tabla faq_precargadas

Requisitos:
  - OPENAI_API_KEY o MISTRAL_API_KEY configuradas
  - Indices SQLite/FAISS/ChromaDB previamente construidos
"""
import re
import time
from datetime import datetime

from graph_rag import GraphRAG

# Conceptos HSEQ/Calidad/Integr@ para generar 800+ preguntas
CONCEPTOS = [
    "no conformidad", "accion correctiva", "accion preventiva", "plan de accion",
    "plan capa", "causa raiz", "5 porques", "ishikawa", "fmea", "amef",
    "riesgo", "hallazgo de auditoria", "procedimiento", "formato", "documento externo",
    "registro", "sistema haccp", "poes", "bpf", "gmp", "trazabilidad",
    "control de temperatura", "auditoria interna", "auditoria externa", "revision gerencial",
    "estado de un procedimiento", "publicacion de procedimiento", "aprobacion de procedimientos",
    "documento obsoleto", "desviacion de calidad", "voz del cliente", "pqrs", "reclamo",
    "seguimiento a planes de accion", "garantia de calidad", "calificacion de equipos",
    "matriz de riesgos", "mejora continua", "politica de calidad", "comunicacion de cambios",
    "revision documental", "archivo de registros", "indicador de calidad", "medicion de indicadores",
    "procedimiento vigente", "consultar documento por codigo", "documento vencido",
    "validacion de proveedores", "calificacion de proveedores", "control de cambios",
    "capacitacion", "competencia del personal", "proceso", "tipo de documento",
    "elaborador", "revisor", "aprobador", "publicador", "responsable de proceso",
    "area de calidad", "auditor lider", "auditor interno", "jefe de calidad",
    "gestion de documentos", "control de versiones", "distribucion de documentos",
    "acceso a documentos", "proteccion de datos", "seguridad de la informacion",
    "control de registros", "retencion de registros", "eliminacion de registros",
    "identificacion y trazabilidad", "calibracion de equipos", "mantenimiento de equipos",
    "limpieza y saneamiento", "control de plagas", "manipulacion de producto",
    "almacenamiento de producto", "transporte de producto", "distribucion de producto",
    "devolucion de producto", "recall de producto", "retiro de producto",
    "muestreo", "inspeccion", "pruebas", "laboratorio", "control de calidad en proceso",
    "liberacion de producto", "cuarentena", "rechazo de producto", "material de empaque",
    "etiquetado", "rotulado", "cadena de frio", "punto de control critico",
    "limite critico", "monitoreo", "verificacion", "validacion",
    "accion correctiva inmediata", "accion de contingencia", "plan de contingencia",
    "simulacro", "emergencia", "incidente", "accidente",
    "salud ocupacional", "seguridad industrial", "ambiente de trabajo",
    "ergonomia", "programa de habitos de vida saludable", "consumo de alcohol",
    "sustancias psicoactivas", "programa de proteccion de datos", "datos personales",
    "habeas data", "consentimiento informado", "privacidad", "confidencialidad",
    "documentacion regulatoria", "requisitos legales", "requisitos del cliente",
    "normas aplicables", "invima", "ministerio de salud", "oms", "ops",
]

PLANTILLAS = [
    "que es {concepto}",
    "como se define {concepto}",
    "cual es el objetivo de {concepto}",
    "donde se aplica {concepto}",
    "como se gestiona {concepto}",
    "quien es responsable de {concepto}",
    "que documentos aplican para {concepto}",
    "como se evidencia {concepto}",
    "cuales son los pasos de {concepto}",
    "requisitos de {concepto}",
    "importancia de {concepto}",
    "ejemplo de {concepto}",
]

MAX_FAQS = 800


def _generar_preguntas_base() -> list[str]:
    """Genera preguntas base a partir de conceptos y plantillas."""
    preguntas = []
    for concepto in CONCEPTOS:
        for plantilla in PLANTILLAS:
            p = plantilla.format(concepto=concepto)
            preguntas.append(p)
    return preguntas


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.strip().lower())


def main():
    print("[precargar_faq] Inicializando GraphRAG con OpenAI como primario...")

    rag = GraphRAG(llm_primary="openai")

    # 0. Reparar FAQs existentes: completar metadatos de vigencia y recategorizar
    print("[precargar_faq] Reparando FAQs existentes...")
    stats_reparo = rag.reparar_faq_existentes()
    print(f"[precargar_faq] FAQs reparadas: {stats_reparo['reparadas']}/{stats_reparo['total']}")

    # 1. Preguntas frecuentes desde usage_stats
    preguntas_uso = []
    try:
        rows = rag.conn.execute("""
            SELECT question, COUNT(*) as n
            FROM usage_stats
            WHERE question IS NOT NULL AND length(question) > 5
            GROUP BY question
            ORDER BY n DESC
            LIMIT 50
        """).fetchall()
        preguntas_uso = [q for q, _ in rows]
    except Exception as e:
        print(f"[precargar_faq] No se pudieron leer preguntas de uso: {e}")

    # 2. Combinar preguntas de uso + generadas, deduplicar y limitar a 800
    base = _generar_preguntas_base()
    todas = []
    vistas = set()
    for p in preguntas_uso + base:
        n = _normalizar(p)
        if n and n not in vistas:
            vistas.add(n)
            todas.append(p)

    # Limitar a MAX_FAQS para no exceder tiempo/costo
    todas = todas[:MAX_FAQS]

    print(f"[precargar_faq] Total de FAQs unicas a generar: {len(todas)}")
    print(f"[precargar_faq] ADVERTENCIA: Generar {len(todas)} respuestas puede tardar varias horas.")

    generadas = 0
    existentes = 0
    sin_docs = 0
    fallidas = 0
    t0 = time.time()

    for i, pregunta in enumerate(todas, 1):
        n = _normalizar(pregunta)
        exists = rag.conn.execute("SELECT 1 FROM faq_precargadas WHERE pregunta = ?", (n,)).fetchone()
        if exists:
            existentes += 1
            print(f"  [{i}/{len(todas)}] Ya existe FAQ: {pregunta[:60]}")
            continue

        print(f"  [{i}/{len(todas)}] Generando respuesta para: {pregunta[:60]}")
        t_q0 = time.time()
        try:
            respuesta, resultados = rag.ask(pregunta, modo_rapido=True)
            t_q = time.time() - t_q0
            if not resultados:
                sin_docs += 1
                print(f"    -> Sin documentos vigentes recuperados (no se guarda)")
                continue
            if respuesta and len(respuesta) > 20:
                doc_list, est_dict = rag._extraer_documentos_resultados(resultados)
                rag.guardar_faq_precargada(
                    pregunta=pregunta,
                    respuesta=respuesta,
                    keywords=", ".join(re.findall(r"\b\w+\b", n)[:12]),
                    categoria="auto_generada",
                    fuente="precargar_faq.py",
                    documentos_citados=doc_list,
                    estados_documentos=est_dict,
                    tipo_contenido=rag._tipo_contenido_faq(pregunta)
                )
                generadas += 1
                print(f"    -> Guardada en {t_q:.1f}s")
            else:
                fallidas += 1
                print(f"    -> Respuesta vacia")
        except Exception as e:
            import traceback
            fallidas += 1
            print(f"    -> Error: {e}")
            traceback.print_exc()

    t_total = time.time() - t0
    print(f"\n[precargar_faq] Resumen: {generadas} generadas, {existentes} ya existian, {sin_docs} sin docs, {fallidas} fallidas")
    print(f"[precargar_faq] Tiempo total: {t_total:.1f}s")
    print(f"[precargar_faq] Ejecutado: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
