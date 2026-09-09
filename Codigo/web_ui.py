"""
Web UI del Agente de Calidad Integr@.
Interfaz web con Streamlit para que usuarios no técnicos usen el agente.

Uso:
    $env:INTEGRA_DB_SERVER="10.238.66.14"
    $env:MISTRAL_API_KEY="<tu_api_key>"
    streamlit run Codigo/web_ui.py
    # UI disponible en http://localhost:8501
"""
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import streamlit as st

# Importar GraphRAG
sys.path.insert(0, str(Path(__file__).parent))
from graph_rag import GraphRAG

# ──────────────────────────────────────────────
# Helper: icono de estado por codigo
# ──────────────────────────────────────────────

_ESTADO_ICONOS = {
    "P": "🟢",  # Publicado (Vigente)
    "O": "🔴",  # Obsoleto
    "E": "🔵",  # Elaborado
    "D": "🟠",  # Devuelto
    "R": "🟣",  # Revisado por proceso
    "Q": "🟡",  # Revisado por Calidad (QA)
    "A": "⚪",  # Aprobado gerencial
    "Z": "⚫",  # Especial / Pendiente
}

_ESTADO_DESC = {
    "P": "Publicado (Vigente)",
    "O": "Obsoleto",
    "E": "Elaborado",
    "D": "Devuelto",
    "R": "Revisado por proceso",
    "Q": "Revisado por Calidad (QA)",
    "A": "Aprobado gerencial",
    "Z": "Especial / Pendiente",
}


def estado_icon(estado: str) -> str:
    """Retorna el emoji unico para cada estado de documento."""
    return _ESTADO_ICONOS.get(estado, "❓")


def estado_label(estado: str) -> str:
    """Retorna el emoji + descripcion del estado."""
    return f"{estado_icon(estado)} {estado} - {_ESTADO_DESC.get(estado, 'Desconocido')}"


# ──────────────────────────────────────────────
# Configuración de la página
# ──────────────────────────────────────────────

st.set_page_config(
    page_title="Agente de Calidad - Integr@",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# CSS personalizado: colores, fuentes, diseno
# ──────────────────────────────────────────────

st.markdown("""
<style>
    /* Color principal y fuente */
    :root {
        --primary: #0066B1;
        --secondary: #00A3E0;
        --accent: #FF6B35;
        --dark: #1A2B3C;
        --light: #F0F4F8;
        --success: #28A745;
        --warning: #FFC107;
        --danger: #DC3545;
    }

    /* Header principal */
    .main-header {
        background: linear-gradient(135deg, #0066B1 0%, #00A3E0 100%);
        padding: 20px 30px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0, 102, 177, 0.3);
    }
    .main-header h1 {
        color: white;
        font-size: 28px;
        font-weight: 700;
        margin: 0;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.2);
    }
    .main-header p {
        color: rgba(255, 255, 255, 0.9);
        font-size: 14px;
        margin: 5px 0 0 0;
    }

    /* Tarjetas de metricas */
    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #E0E0E0;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    div[data-testid="stMetric"] label {
        color: #0066B1;
        font-weight: 600;
        font-size: 13px;
    }
    div[data-testid="stMetric"] value {
        color: #1A2B3C;
        font-size: 24px;
        font-weight: 700;
    }

    /* Botones */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #F8FAFC 0%, #E8F0F8 100%);
    }
    section[data-testid="stSidebar"] .stRadio > label {
        color: #0066B1;
        font-weight: 600;
    }

    /* Expanders */
    .streamlit-expanderHeader {
        background: linear-gradient(90deg, #0066B1 0%, #00A3E0 100%);
        color: white;
        border-radius: 8px;
        font-weight: 600;
    }
    .streamlit-expanderHeader:hover {
        background: linear-gradient(90deg, #005599 0%, #0090C0 100%);
    }

    /* Tablas */
    table {
        border-radius: 8px;
        overflow: hidden;
    }
    thead tr {
        background: #0066B1;
        color: white;
    }
    thead th {
        color: white;
        font-weight: 600;
    }
    tbody tr:nth-child(even) {
        background: #F0F4F8;
    }
    tbody tr:hover {
        background: #E0F0FF;
    }

    /* Chat messages */
    .stChatMessage {
        border-radius: 12px;
        border: 1px solid #E0E0E0;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    }

    /* Info boxes */
    div[data-testid="stAlert"] {
        border-radius: 10px;
        border-left: 4px solid #0066B1;
    }

    /* Code blocks */
    .stCodeBlock {
        border-radius: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    }

    /* Progress bar */
    .stProgress > div > div {
        background: linear-gradient(90deg, #0066B1 0%, #00A3E0 100%);
        border-radius: 10px;
    }

    /* Selectbox */
    .stSelectbox > div > div {
        border-radius: 8px;
        border: 2px solid #0066B1;
    }

    /* Caption */
    .stCaption {
        color: #666;
        font-style: italic;
    }

    /* Divider */
    hr {
        border: none;
        height: 2px;
        background: linear-gradient(90deg, transparent 0%, #0066B1 50%, transparent 100%);
        margin: 20px 0;
    }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Logo de la empresa
# ──────────────────────────────────────────────

_LOGO_PATH = Path(__file__).parent.parent / "Imagenes" / "Logo AGV.jpg"

# ──────────────────────────────────────────────
# Cargar agente (cache)
# ──────────────────────────────────────────────

@st.cache_resource
def load_rag():
    """Carga el agente Graph RAG una sola vez."""
    rag = GraphRAG()
    return rag

with st.spinner("Cargando Agente Graph RAG..."):
    rag = load_rag()

# ──────────────────────────────────────────────
# Header comun (aparece en todas las paginas)
# ──────────────────────────────────────────────

# Logo + branding
col_logo, col_brand, col_stats = st.columns([1, 3, 4])

with col_logo:
    if _LOGO_PATH.exists():
        try:
            with open(_LOGO_PATH, "rb") as f:
                logo_bytes = f.read()
            st.image(logo_bytes, width=120)
        except Exception:
            st.markdown("### Agente de Calidad")
    else:
        st.markdown("### Agente de Calidad")

with col_brand:
    st.markdown("""
    <div style="padding-top: 15px;">
        <h2 style="color: #0066B1; margin: 0; font-weight: 700;">Solistica - Integr@</h2>
        <p style="color: #666; margin: 5px 0 0 0; font-size: 14px;">Agente Graph RAG Hibrido</p>
    </div>
    """, unsafe_allow_html=True)

with col_stats:
    stats = rag.grafo_stats()
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Documentos", len(rag.docs))
    with m2:
        st.metric("Nodos", stats.get("nodos", 0))
    with m3:
        st.metric("Aristas", stats.get("aristas", 0))
    with m4:
        st.metric("Glosario", 55)

st.divider()

# ──────────────────────────────────────────────
# Navegacion por tabs centrales
# ──────────────────────────────────────────────

tab_chat, tab_est, tab_jer, tab_venc, tab_glos, tab_finops, tab_docs, tab_comp, tab_arq, tab_seg = st.tabs([
    "Chat", "Estadisticas", "Jerarquia", "Vencidos", "Glosario",
    "FinOps", "Documentos", "Comparador", "Arquitectura", "Seguridad",
])

# ──────────────────────────────────────────────
# Paginas (tabs)
# ──────────────────────────────────────────────

with tab_chat:
    # Header con gradiente
    st.markdown("""
    <div class="main-header">
        <h1>Chat con el Agente de Calidad</h1>
        <p>Graph RAG Hibrido + Governance AI + Streaming | Integr@ - Solistica</p>
    </div>
    """, unsafe_allow_html=True)

    # Inicializar historial
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "feedback_given" not in st.session_state:
        st.session_state.feedback_given = {}

    # Boton para exportar conversacion
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.session_state.messages:
            export_format = st.selectbox("Exportar", ["Markdown", "Texto plano"], key="export_fmt")
            if st.button("Descargar"):
                if export_format == "Markdown":
                    export_content = "# Conversacion - Agente de Calidad Integr@\n\n"
                    export_content += f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"
                    for msg in st.session_state.messages:
                        role = "**Usuario**" if msg["role"] == "user" else "**Agente**"
                        export_content += f"### {role}\n\n{msg['content']}\n\n"
                        if msg.get("documentos"):
                            export_content += f"**Documentos consultados:**\n"
                            for doc in msg["documentos"]:
                                export_content += f"- {doc['codigo']} - {doc['nombre']}\n"
                            export_content += "\n"
                        export_content += "---\n\n"
                    st.download_button(
                        label="Descargar .md",
                        data=export_content.encode("utf-8"),
                        file_name=f"conversacion_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                        mime="text/markdown",
                    )
                else:
                    export_content = f"Conversacion - Agente de Calidad Integr@\nFecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{'='*60}\n\n"
                    for msg in st.session_state.messages:
                        role = "Usuario" if msg["role"] == "user" else "Agente"
                        export_content += f"\n[{role}]\n{msg['content']}\n"
                        if msg.get("documentos"):
                            export_content += f"\n  Documentos: {', '.join(d['codigo'] for d in msg['documentos'])}\n"
                        export_content += f"\n{'-'*60}\n"
                    st.download_button(
                        label="Descargar .txt",
                        data=export_content.encode("utf-8"),
                        file_name=f"conversacion_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                        mime="text/plain",
                    )

    # Mostrar historial
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("documentos"):
                with st.expander(f"Documentos consultados ({len(msg['documentos'])})"):
                    for doc in msg["documentos"]:
                        icon = estado_icon(doc.get("estado", ""))
                        st.write(f"{icon} **{doc['codigo']}** - {doc['nombre']}")
                        st.caption(f"Proceso: {doc.get('proceso', 'N/A')} | Estado: {doc.get('estado', 'N/A')} | Score: {doc.get('score', 0):.3f}")

                        # Boton de previsualizacion del documento (SOLO LECTURA)
                        doc_codigo = doc.get("codigo", "")
                        preview_key = f"preview_{idx}_{doc_codigo}"
                        if st.button("Previsualizar documento", key=f"btn_{preview_key}", help=f"Ver contenido de {doc_codigo} (solo lectura)"):
                            st.session_state[preview_key] = not st.session_state.get(preview_key, False)

                        if st.session_state.get(preview_key, False):
                            with st.container():
                                st.caption("**Vista previa (solo lectura - el agente NO modifica Integr@)**")
                                doc_full = rag.get_documento(doc_codigo)
                                if doc_full:
                                    # Metadatos
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        st.write(f"**Codigo:** {doc_full.get('codigo', '')}")
                                        st.write(f"**Proceso:** {doc_full.get('proceso', 'N/A')}")
                                    with col2:
                                        st.write(f"**Estado:** {doc_full.get('estado', 'N/A')}")
                                        st.write(f"**Tipo:** {doc_full.get('tipo_documento', 'N/A')}")
                                    with col3:
                                        st.write(f"**Publicacion:** {doc_full.get('fecha_publicacion', 'N/A')}")
                                        st.write(f"**Vigencia:** {doc_full.get('vigencia_dias', 'N/A')} dias")

                                    # Resumen ejecutivo si existe
                                    if doc_full.get("resumen"):
                                        st.write("**Resumen ejecutivo:**")
                                        st.info(doc_full["resumen"])

                                    # Contenido del documento (solo lectura)
                                    texto = doc_full.get("texto", "")
                                    if texto:
                                        st.write("**Contenido del documento:**")
                                        # Mostrar en scrollable text area (solo lectura)
                                        st.text_area(
                                            "Contenido",
                                            value=texto,
                                            height=400,
                                            key=f"ta_{preview_key}",
                                            label_visibility="collapsed",
                                        )
                                        st.caption(f"Longitud: {len(texto):,} caracteres | Este contenido es de solo lectura")
                                    else:
                                        st.warning("No hay contenido de texto disponible para este documento.")

                                    # Documentos relacionados
                                    if doc_full.get("docs_relacionados"):
                                        st.write("**Documentos relacionados:**")
                                        for rd in doc_full["docs_relacionados"][:5]:
                                            rd_icon = estado_icon(rd.get("estado", ""))
                                            st.write(f"  {rd_icon} {rd.get('codigo', '')} - {rd.get('nombre', '')[:60]}")
                                else:
                                    st.error(f"No se encontro el documento {doc_codigo}")

                                if st.button("Cerrar previsualizacion", key=f"close_{preview_key}"):
                                    st.session_state[preview_key] = False
                                    st.rerun()

            # Feedback: thumbs up/down solo para respuestas del agente
            if msg["role"] == "assistant":
                fb_key = f"fb_{idx}"
                if fb_key not in st.session_state.feedback_given:
                    col_pos, col_neg = st.columns([1, 1])
                    with col_pos:
                        if st.button("Util", key=f"pos_{idx}"):
                            rag.guardar_feedback(
                                pregunta=st.session_state.messages[idx-1]["content"] if idx > 0 else "",
                                respuesta=msg["content"],
                                feedback="positive",
                            )
                            st.session_state.feedback_given[fb_key] = "positive"
                            st.rerun()
                    with col_neg:
                        if st.button("No util", key=f"neg_{idx}"):
                            rag.guardar_feedback(
                                pregunta=st.session_state.messages[idx-1]["content"] if idx > 0 else "",
                                respuesta=msg["content"],
                                feedback="negative",
                            )
                            st.session_state.feedback_given[fb_key] = "negative"
                            st.rerun()
                else:
                    fb = st.session_state.feedback_given[fb_key]
                    if fb == "positive":
                        st.caption("Gracias por tu feedback: Util")
                    else:
                        st.caption("Gracias por tu feedback: No util")

    # ─── Sugerencias dinamicas (storytelling) ───
    # Las sugerencias cambian segun el historial de conversacion

    def generar_sugerencias(messages: list[dict]) -> list[str]:
        """Genera sugerencias contextuales basadas en el historial del chat.
        - Sin historial: preguntas iniciales generales
        - Con historial: preguntas de seguimiento relacionadas con la ultima consulta
        """
        if not messages:
            return [
                "Cual es el procedimiento de control de temperatura en cuartos frios?",
                "Como se gestiona una no conformidad?",
                "Que procedimientos existen para recepcion de mercancia?",
                "Como se realiza la calificacion de equipos IQ OQ PQ?",
                "Que documentos estan por vencer?",
            ]

        # Analizar ultimo mensaje del usuario y respuesta del agente
        ultimo_user = ""
        ultimo_assistant = ""
        docs_ultimos = []
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "assistant" and not ultimo_assistant:
                ultimo_assistant = messages[i]["content"]
                docs_ultimos = messages[i].get("documentos", [])
            elif messages[i]["role"] == "user" and not ultimo_user:
                ultimo_user = messages[i]["content"]

        # Detectar tema principal de la ultima consulta
        texto_analizar = (ultimo_user + " " + ultimo_assistant).lower()
        procesos_detectados = set()
        codigos_detectados = set()

        # Extraer codigos de documentos de la respuesta
        import re as _re
        codigos = _re.findall(r"\b[A-Z]{2,5}[-_]\d{2,}[-_]\d{1,}\b", ultimo_assistant)
        codigos_detectados = set(codigos[:3])

        # Extraer procesos de los documentos consultados
        for doc in docs_ultimos:
            proc = doc.get("proceso", "")
            if proc:
                procesos_detectados.add(proc)

        # Mapeo de temas a sugerencias de seguimiento
        sugerencias = []

        # 1. Si detectamos documentos consultados, sugerir profundizar
        if docs_ultimos:
            doc_principal = docs_ultimos[0]
            codigo = doc_principal.get("codigo", "")
            nombre = doc_principal.get("nombre", "")
            proceso = doc_principal.get("proceso", "")

            if codigo:
                sugerencias.append(f"Que resumen ejecutivo tienes del documento {codigo}?")
                sugerencias.append(f"Cuales son los puntos criticos del procedimiento {codigo}?")

            if proceso:
                sugerencias.append(f"Que otros procedimientos existen en el proceso {proceso}?")
                sugerencias.append(f"Hay documentos vencidos en el proceso {proceso}?")

        # 2. Sugerencias por tema detectado
        if "no conformidad" in texto_analizar or "no conforme" in texto_analizar or "nc " in texto_analizar:
            sugerencias.append("Como hacer un analisis de causa raiz con 5 porques?")
            sugerencias.append("Cual es el formato para registrar un plan de accion CAPA?")

        if "capa" in texto_analizar or "accion correctiva" in texto_analizar or "accion preventiva" in texto_analizar:
            sugerencias.append("Como se verifica la eficacia de una accion correctiva?")
            sugerencias.append("Cual es el procedimiento de acciones correctivas y preventivas?")

        if "auditor" in texto_analizar or "auditoria" in texto_analizar:
            sugerencias.append("Como preparo una auditoria interna de calidad?")
            sugerencias.append("Cual es el checklist de auditoria para almacenamiento?")

        if "temperatura" in texto_analizar or "cadena de frio" in texto_analizar or "frio" in texto_analizar:
            sugerencias.append("Que hago si hay una desviacion de temperatura en un cuarto frio?")
            sugerencias.append("Cuales son los criterios de aceptacion para cadena de frio?")

        if "recepcion" in texto_analizar or "mercancia" in texto_analizar:
            sugerencias.append("Cuales son los criterios de rechazo en recepcion de mercancia?")
            sugerencias.append("Como se registra una devolucion en recepcion?")

        if "calificacion" in texto_analizar or "iq oq pq" in texto_analizar or "equipos" in texto_analizar:
            sugerencias.append("Cual es el formato de protocolo de calificacion IQ?")
            sugerencias.append("Como se mantiene la calificacion de equipos criticos?")

        if "vencim" in texto_analizar or "vigencia" in texto_analizar or "obsolet" in texto_analizar:
            sugerencias.append("Que documentos estan por vencer en los proximos 30 dias?")
            sugerencias.append("Como se gestiona la renovacion de un procedimiento vencido?")

        if "merma" in texto_analizar or "perdida" in texto_analizar or "desperdicio" in texto_analizar:
            sugerencias.append("Cuales son los KPIs de merma en el CEDI?")
            sugerencias.append("Como se calcula el porcentaje de merma permitido?")

        if "wms" in texto_analizar or "sistema" in texto_analizar:
            sugerencias.append("Como se integra el WMS con el control de calidad?")
            sugerencias.append("Cuales son los puntos de control del WMS?")

        if "mermaid" in texto_analizar or "diagrama" in texto_analizar or "flujo" in texto_analizar:
            sugerencias.append("Genera un diagrama Ishikawa para esta no conformidad")
            sugerencias.append("Crea un flujograma del proceso de recepcion")

        if "ishikawa" in texto_analizar or "5 porques" in texto_analizar or "causa raiz" in texto_analizar:
            sugerencias.append("Como aplico el metodo 6M al analisis de causa raiz?")
            sugerencias.append("Cual es la diferencia entre FMEA y AMEF?")

        if "invima" in texto_analizar or "regulatorio" in texto_analizar or "regulacion" in texto_analizar:
            sugerencias.append("Cuales son los requisitos Invima para cadena de frio?")
            sugerencias.append("Como se prepara una respuesta a una observacion del Invima?")

        if "sst" in texto_analizar or "seguridad y salud" in texto_analizar or "epp" in texto_analizar:
            sugerencias.append("Cuales son los EPP requeridos para operaciones en cuartos frios?")
            sugerencias.append("Como se integra SST con el plan de calidad HSEQ?")

        # 3. Si detectamos un proceso especifico, sugerir explorar mas
        if procesos_detectados and len(sugerencias) < 4:
            proc = list(proces_detectados)[0]
            sugerencias.append(f"Que temas se agrupan en el proceso {proc}?")

        # 4. Sugerencias generales de seguimiento si faltan
        if len(sugerencias) < 5:
            # Contar preguntas del usuario en el historial
            num_preguntas = sum(1 for m in messages if m["role"] == "user")
            if num_preguntas == 1:
                sugerencias.extend([
                    "Que otros procesos de calidad existen en Integr@?",
                    "Puedes hacerme un resumen de los documentos mas consultados?",
                ])
            elif num_preguntas == 2:
                sugerencias.extend([
                    "Hay alguna relacion entre los documentos que hemos consultado?",
                    "Que documentos estan por vencer?",
                ])
            else:
                sugerencias.extend([
                    "Puedes comparar dos versiones de un procedimiento?",
                    "Cuales son los hallazgos mas comunes en auditorias internas?",
                ])

        # 5. Si hay codigos detectados, sugerir comparar versiones
        if len(codigos_detectados) >= 2 and len(sugerencias) < 5:
            codigos_lista = list(codigos_detectados)
            sugerencias.append(f"Puedes comparar las versiones {codigos_lista[0]} y {codigos_lista[1]}?")

        # Limitar a 5 sugerencias y eliminar duplicados
        sugerencias_unicas = []
        vistos = set()
        for s in sugerencias:
            s_lower = s.lower().strip()
            if s_lower not in vistos:
                sugerencias_unicas.append(s)
                vistos.add(s_lower)
            if len(sugerencias_unicas) >= 5:
                break

        return sugerencias_unicas

    # Generar sugerencias dinamicas
    sugerencias = generar_sugerencias(st.session_state.messages)

    # Etiqueta segun contexto
    if not st.session_state.messages:
        st.info("**Ejemplos de preguntas (click para consultar):**")
    else:
        st.info("**Preguntas de seguimiento sugeridas (click para consultar):**")

    cols_ej = st.columns(min(len(sugerencias), 5))
    for i, ej in enumerate(sugerencias):
        with cols_ej[i]:
            if st.button(ej[:45], key=f"ej_{i}_{hash(ej) % 10000}", help=ej, use_container_width=True):
                st.session_state.pending_question = ej
                st.rerun()

    st.divider()

    # Input
    if "pending_question" in st.session_state:
        prompt = st.session_state.pending_question
        del st.session_state.pending_question
    else:
        prompt = st.chat_input("Escribe tu pregunta...")

    if prompt:
        # Mostrar pregunta
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generar respuesta con streaming
        with st.chat_message("assistant"):
            t_start = time.time()
            try:
                # Streaming: mostrar tokens en vivo
                stream = rag.ask_stream(prompt)
                # Primer yield: resultados de recuperacion
                _, _, resultados = next(stream)

                # Mostrar documentos recuperados inmediatamente
                docs = [
                    {
                        "codigo": r["codigo"],
                        "nombre": r["nombre"],
                        "proceso": r.get("proceso", ""),
                        "estado": r.get("estado", ""),
                        "score": r.get("score_total", 0),
                    }
                    for r in resultados
                ]

                if docs:
                    with st.expander(f"Documentos consultados ({len(docs)})"):
                        for doc in docs:
                            icon = estado_icon(doc.get("estado", ""))
                            st.write(f"{icon} **{doc['codigo']}** - {doc['nombre']}")
                            st.caption(f"Proceso: {doc.get('proceso', 'N/A')} | Estado: {doc.get('estado', 'N/A')} | Score: {doc.get('score', 0):.3f}")

                # Streaming de la respuesta
                full_answer = ""
                provider_used = ""
                with st.spinner("Generando respuesta..."):
                    for token, provider, _ in stream:
                        if token is None:
                            # Senal de fin
                            provider_used = provider
                            break
                        full_answer += token

                t_elapsed = time.time() - t_start
                st.markdown(full_answer)
                st.caption(f"Tiempo: {t_elapsed:.1f}s | Documentos: {len(resultados)} | LLM: {provider_used}")

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_answer,
                    "documentos": docs,
                })

            except Exception as e:
                st.error(f"Error: {e}")

with tab_est:
    st.markdown("""
    <div class="main-header">
        <h1>Estadisticas del Grafo de Conocimiento</h1>
        <p>Documentos, procesos, temas y estados de Integr@</p>
    </div>
    """, unsafe_allow_html=True)

    # ─── 1. Nodos por tipo ───
    st.subheader("Nodos por tipo")
    tipos = stats.get("tipos", {})
    if tipos:
        tipos_data = [{"tipo": t, "cantidad": c} for t, c in sorted(tipos.items(), key=lambda x: -x[1])]
        col1, col2 = st.columns([2, 3])
        with col1:
            st.table(tipos_data)
        with col2:
            st.bar_chart(tipos_data, x="tipo", y="cantidad")

    st.divider()

    # ─── 2. Documentos por estado ───
    st.subheader("Documentos por estado")

    estados_significado = {
        "O": {"desc": "Obsoleto", "icono": "🔴",
              "detalle": "Documento declarado obsoleto. No vigente. Excluido automaticamente por el agente."},
        "P": {"desc": "Publicado (Vigente)", "icono": "🟢",
              "detalle": "Documento publicado y vigente. Version oficial autorizada para uso operativo."},
        "E": {"desc": "Elaborado", "icono": "🔵",
              "detalle": "Documento creado por el responsable. Fase inicial del flujo de aprobacion. No vigente."},
        "Z": {"desc": "Especial / Pendiente", "icono": "⚫",
              "detalle": "Estado especial o transitorio. Requiere confirmacion con el administrador de Integr@."},
        "D": {"desc": "Devuelto", "icono": "🟠",
              "detalle": "Devuelto con observaciones por el revisor. El elaborador debe corregir y reenviar."},
        "R": {"desc": "Revisado por proceso", "icono": "🟣",
              "detalle": "Revisado y validado por el responsable del proceso. Pendiente de revision por Calidad (Q)."},
        "Q": {"desc": "Revisado por Calidad (QA)", "icono": "🟡",
              "detalle": "Revisado y aprobado por el area de Calidad. Pendiente de aprobacion gerencial (A)."},
        "A": {"desc": "Aprobado gerencial", "icono": "⚪",
              "detalle": "Aprobado por gerencia. Pendiente de publicacion (P). No vigente aun."},
    }

    estados = {}
    for doc in rag.docs.values():
        estado = doc.get("estado", "N/A")
        estados[estado] = estados.get(estado, 0) + 1

    estado_rows = []
    for estado, count in sorted(estados.items(), key=lambda x: -x[1]):
        info = estados_significado.get(estado, {"desc": "Desconocido", "icono": "⚪", "detalle": "Estado no reconocido."})
        estado_rows.append({
            "Estado": f"{info['icono']} {estado}",
            "Significado": info["desc"],
            "Documentos": count,
            "Vigente": "Si" if estado == "P" else "No",
            "Detalle": info["detalle"],
        })
    st.table(estado_rows)

    # Grafico de documentos por estado
    est_data = [{"estado": f"{estados_significado.get(e, {}).get('icono', '')} {e}", "cantidad": c}
                for e, c in sorted(estados.items(), key=lambda x: -x[1])]
    st.bar_chart(est_data, x="estado", y="cantidad")

    with st.expander("Ver flujo de aprobacion completo"):
        st.code(
            "  FLUJO DE APROBACION DE DOCUMENTOS EN INTEGRA\n"
            "  =============================================\n\n"
            "  E (Elaborado)\n"
            "    |\n"
            "    v\n"
            "  R (Revisado por responsable de proceso)\n"
            "    |\n"
            "    +---> D (Devuelto con observaciones) ---> vuelve a E\n"
            "    |\n"
            "    v\n"
            "  Q (Revisado por Calidad / QA)\n"
            "    |\n"
            "    +---> D (Devuelto con observaciones) ---> vuelve a E\n"
            "    |\n"
            "    v\n"
            "  A (Aprobado gerencial)\n"
            "    |\n"
            "    v\n"
            "  P (Publicado / Vigente)  <-- unico estado vigente\n"
            "    |\n"
            "    v\n"
            "  O (Obsoleto)  <-- excluido automaticamente por el agente\n\n"
            "  Z (Especial / Pendiente)  <-- estado transitorio\n",
            language="text"
        )
        st.info("**Solo los documentos con estado P (Publicado) son vigentes y se usan en operaciones.** "
                "El agente excluye automaticamente los documentos con estado O (Obsoleto).")

    st.divider()

    # ─── 3. Documentos por proceso (agrupados por estado) ───
    st.subheader("Documentos por proceso (agrupados por estado)")
    proc_est_rows = rag.conn.execute("""
        SELECT proceso_nom, estado, COUNT(*) as count
        FROM procedimientos
        WHERE proceso_nom IS NOT NULL
        GROUP BY proceso_nom, estado
        ORDER BY proceso_nom, estado
    """).fetchall()

    # Construir datos pivotados: una columna por estado
    estados_list = sorted(set(r[1] for r in proc_est_rows if r[1]))
    proc_nombres = sorted(set(r[0] for r in proc_est_rows))
    proc_pivot = {}
    for nombre in proc_nombres:
        proc_pivot[nombre] = {"proceso": nombre}
        for est in estados_list:
            proc_pivot[nombre][est] = 0
    for r in proc_est_rows:
        proc_pivot[r[0]][r[1]] = r[2]

    # Total por proceso para ordenar
    proc_totals = {p: sum(proc_pivot[p][e] for e in estados_list) for p in proc_nombres}
    proc_nombres_sorted = sorted(proc_nombres, key=lambda p: -proc_totals[p])

    # Tabla con numeros por estado
    tabla_proc = []
    for p in proc_nombres_sorted:
        row = {"Proceso": p}
        total = 0
        for est in estados_list:
            count = proc_pivot[p][est]
            icon = _ESTADO_ICONOS.get(est, "")
            row[f"{icon} {est}"] = count
            total += count
        row["Total"] = total
        tabla_proc.append(row)
    st.table(tabla_proc)

    # Bar chart apilado por estado
    chart_proc = []
    for p in proc_nombres_sorted:
        row = {"proceso": p[:30]}
        for est in estados_list:
            row[f"{_ESTADO_ICONOS.get(est, '')} {est}"] = proc_pivot[p][est]
        chart_proc.append(row)
    st.bar_chart(chart_proc, x="proceso")

    st.divider()

    # ─── 4. Documentos por tipo (agrupados por estado) ───
    st.subheader("Documentos por tipo (agrupados por estado)")
    tipo_est_rows = rag.conn.execute("""
        SELECT tipo_documento, estado, COUNT(*) as count
        FROM procedimientos
        GROUP BY tipo_documento, estado
        ORDER BY tipo_documento, estado
    """).fetchall()

    tipos_nombres = sorted(set(r[0] for r in tipo_est_rows if r[0]))
    tipo_pivot = {}
    for nombre in tipos_nombres:
        tipo_pivot[nombre] = {"tipo": nombre}
        for est in estados_list:
            tipo_pivot[nombre][est] = 0
    for r in tipo_est_rows:
        if r[0] and r[1]:
            tipo_pivot[r[0]][r[1]] = r[2]

    # Tabla con numeros por estado
    tabla_tipo = []
    for t in tipos_nombres:
        row = {"Tipo": t}
        total = 0
        for est in estados_list:
            count = tipo_pivot[t][est]
            icon = _ESTADO_ICONOS.get(est, "")
            row[f"{icon} {est}"] = count
            total += count
        row["Total"] = total
        tabla_tipo.append(row)
    st.table(tabla_tipo)

    # Bar chart apilado por estado
    chart_tipo = []
    for t in tipos_nombres:
        row = {"tipo": t}
        for est in estados_list:
            row[f"{_ESTADO_ICONOS.get(est, '')} {est}"] = tipo_pivot[t][est]
        chart_tipo.append(row)
    st.bar_chart(chart_tipo, x="tipo")

    st.divider()

    # ─── 5. Documentos por año de elaboracion (lineas por estado) ───
    st.subheader("Documentos por año de elaboracion (lineas por estado)")
    ano_est_rows = rag.conn.execute("""
        SELECT strftime('%Y', fecha_elaboracion) as ano, estado, COUNT(*) as count
        FROM procedimientos
        WHERE fecha_elaboracion IS NOT NULL
        GROUP BY ano, estado
        ORDER BY ano, estado
    """).fetchall()

    anos_list = sorted(set(r[0] for r in ano_est_rows if r[0]))
    anos_pivot = {}
    for ano in anos_list:
        anos_pivot[ano] = {"ano": ano}
        for est in estados_list:
            anos_pivot[ano][est] = 0
    for r in ano_est_rows:
        if r[0] and r[1]:
            anos_pivot[r[0]][r[1]] = r[2]

    # Line chart con una linea por estado
    chart_ano = []
    for ano in anos_list:
        row = {"ano": ano}
        for est in estados_list:
            row[f"{_ESTADO_ICONOS.get(est, '')} {est}"] = anos_pivot[ano][est]
        chart_ano.append(row)
    st.line_chart(chart_ano, x="ano")

    st.divider()

    # ─── 6. Temas detectados por clustering ───
    st.subheader("Temas detectados (clustering K-Means)")
    tema_rows = rag.conn.execute("""
        SELECT nombre, num_docs FROM temas ORDER BY num_docs DESC
    """).fetchall()
    tema_data = [{"tema": r[0][:40], "documentos": r[1]} for r in tema_rows]
    col1, col2 = st.columns([2, 3])
    with col1:
        st.table(tema_data)
    with col2:
        st.bar_chart(tema_data, x="tema", y="documentos")

    st.divider()

    # ─── 7. Longitud de documentos ───
    st.subheader("Longitud de documentos (caracteres)")
    long_stats = rag.conn.execute("""
        SELECT
            COUNT(*) as total,
            AVG(texto_length) as promedio,
            MIN(texto_length) as minimo,
            MAX(texto_length) as maximo,
            SUM(texto_length) as total_chars
        FROM procedimientos
    """).fetchone()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Promedio", f"{long_stats[1]:.0f}" if long_stats[1] else "0")
    with col2:
        st.metric("Minimo", long_stats[2] or 0)
    with col3:
        st.metric("Maximo", long_stats[3] or 0)
    with col4:
        st.metric("Total caracteres", f"{long_stats[4]:,}" if long_stats[4] else "0")

    st.divider()

    # ─── 8. Top elaboradores ───
    st.subheader("Top 10 elaboradores")
    elab_rows = rag.conn.execute("""
        SELECT elaborador, COUNT(*) as count
        FROM procedimientos
        WHERE elaborador IS NOT NULL AND elaborador != ''
        GROUP BY elaborador
        ORDER BY count DESC
        LIMIT 10
    """).fetchall()
    elab_data = [{"elaborador": r[0], "documentos": r[1]} for r in elab_rows]
    col1, col2 = st.columns([2, 3])
    with col1:
        st.table(elab_data)
    with col2:
        st.bar_chart(elab_data, x="elaborador", y="documentos")

    st.divider()

    # ─── 9. Vigencia de documentos ───
    st.subheader("Vigencia de documentos (dias)")
    vig_stats = rag.conn.execute("""
        SELECT
            AVG(vigencia_dias) as promedio,
            MIN(vigencia_dias) as minimo,
            MAX(vigencia_dias) as maximo
        FROM procedimientos
        WHERE vigencia_dias IS NOT NULL AND vigencia_dias > 0
    """).fetchone()
    if vig_stats and vig_stats[0]:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Promedio (dias)", f"{vig_stats[0]:.0f}")
        with col2:
            st.metric("Minimo (dias)", vig_stats[1])
        with col3:
            st.metric("Maximo (dias)", vig_stats[2])

    st.divider()

    # ─── 10. Aristas del grafo por tipo de relacion ───
    st.subheader("Aristas del grafo por tipo de relacion")
    arista_rows = rag.conn.execute("""
        SELECT tipo_relacion, COUNT(*) as count
        FROM grafo_aristas
        GROUP BY tipo_relacion
        ORDER BY count DESC
    """).fetchall()
    arista_data = [{"relacion": r[0] or "N/A", "cantidad": r[1]} for r in arista_rows]
    col1, col2 = st.columns([2, 3])
    with col1:
        st.table(arista_data)
    with col2:
        st.bar_chart(arista_data, x="relacion", y="cantidad")

with tab_jer:
    st.markdown("""
    <div class="main-header">
        <h1>Tabla Jerarquica de Documentos</h1>
        <p>Procesos → Tipos de documento → Documentos</p>
    </div>
    """, unsafe_allow_html=True)

    # Leyenda de iconos por estado
    st.write("**Leyenda de estados:**")
    leyenda_cols = st.columns(8)
    estados_leyenda = [
        ("🟢", "P", "Vigente"),
        ("🔴", "O", "Obsoleto"),
        ("🔵", "E", "Elaborado"),
        ("🟠", "D", "Devuelto"),
        ("🟣", "R", "Revisado"),
        ("🟡", "Q", "Calidad"),
        ("⚪", "A", "Aprobado"),
        ("⚫", "Z", "Especial"),
    ]
    for i, (icon, cod, desc) in enumerate(estados_leyenda):
        with leyenda_cols[i]:
            st.write(f"{icon} **{cod}**")
            st.caption(desc)
    st.divider()

    jerarquia = rag.tabla_jerarquica()
    if "error" in jerarquia:
        st.warning(jerarquia["error"])
    else:
        for proc_key, proc_data in sorted(jerarquia.items(), key=lambda x: -x[1]["total_docs"]):
            with st.expander(f"{proc_data['nombre']} ({proc_data['total_docs']} docs)"):
                for tipo, tipo_data in sorted(proc_data["tipos"].items(), key=lambda x: -x[1]["total"]):
                    st.write(f"**{tipo}** ({tipo_data['total']})")
                    for doc in tipo_data["documentos"]:
                        icon = estado_icon(doc.get("estado", ""))
                        st.write(f"  {icon} {doc['codigo']} - {doc['nombre'][:60]}")
                    st.write("")

with tab_venc:
    st.markdown("""
    <div class="main-header">
        <h1>Alertas de Vencimiento</h1>
        <p>Documentos vencidos y por vencer - control de vigencia documental</p>
    </div>
    """, unsafe_allow_html=True)

    alertas = rag.alertas_vencimiento(solo_vencidos=True)
    if not alertas:
        st.success("No hay documentos vencidos ni por vencer.")
    else:
        st.warning(f"{len(alertas)} documentos requieren atencion.")

        for a in alertas:
            icono = "🔴" if a["estado_alerta"] == "VENCIDO" else "🟡"
            dias = a["dias_restantes"]
            dias_str = f"vencido hace {abs(dias)} días" if dias < 0 else f"vence en {dias} días"

            with st.expander(f"{icono} {a['codigo']} - {a['nombre'][:50]} ({dias_str})"):
                st.write(f"**Código:** {a['codigo']}")
                st.write(f"**Nombre:** {a['nombre']}")
                st.write(f"**Proceso:** {a.get('proceso', 'N/A')}")
                st.write(f"**Fecha publicación:** {a.get('fecha_publicacion', 'N/A')}")
                st.write(f"**Vigencia:** {a.get('vigencia_dias', 'N/A')} días")
                st.write(f"**Fecha vencimiento:** {a.get('fecha_vencimiento', 'N/A')}")
                st.write(f"**Estado:** {a['estado_alerta']}")

with tab_glos:
    st.markdown("""
    <div class="main-header">
        <h1>Glosario de Calidad y Logistica</h1>
        <p>55 terminos de calidad HSEQ, logistica farmaceutica y estados Integr@</p>
    </div>
    """, unsafe_allow_html=True)

    termino = st.text_input("Buscar término:", placeholder="Ej: IQ, OQ, PQ, CAPA, cadena de frío...")

    if termino:
        from glosario import buscar_termino
        resultados = buscar_termino(termino)
        if not resultados:
            st.info(f"No se encontraron términos para '{termino}'")
        else:
            for t in resultados:
                st.subheader(t["termino"])
                st.caption(f"Categoría: {t['categoria']}")
                st.write(t["definicion"])
                if t.get("relacionado"):
                    st.write(f"**Relacionado:** {', '.join(t['relacionado'])}")
                st.divider()
    else:
        # Mostrar todos
        from glosario import GLOSARIO
        st.info(f"{len(GLOSARIO)} terminos disponibles. Escribe para buscar.")
        for clave, info in sorted(GLOSARIO.items(), key=lambda x: x[1]["categoria"]):
            with st.expander(f"{info['termino']} ({info['categoria']})"):
                st.write(info["definicion"])
                if info.get("relacionado"):
                    st.write(f"**Relacionado:** {', '.join(info['relacionado'])}")

with tab_finops:
    st.markdown("""
    <div class="main-header">
        <h1>Dashboard FinOps y Metricas en Tiempo Real</h1>
        <p>Tokens, costo, latencia, feedback y trazas del agente</p>
    </div>
    """, unsafe_allow_html=True)

    # Obtener metricas detalladas
    metricas = rag.dashboard_metricas()
    dashboard = rag.obs.dashboard()

    # Metricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total traces", dashboard["total_traces"])
    with col2:
        st.metric("Total tokens", f"{dashboard['total_tokens']:,}")
    with col3:
        st.metric("Costo USD", f"${dashboard['total_costo_usd']:.4f}")
    with col4:
        st.metric("Latencia prom", f"{dashboard['avg_latencia']:.2f}s")
    with col5:
        fb = metricas["feedback"]
        st.metric("Satisfaccion", f"{fb['positive']}/{fb['total']}" if fb["total"] > 0 else "N/A")

    st.divider()

    # --- Graficos interactivos ---

    # 1. Traces y tokens por dia
    if metricas["traces_por_dia"]:
        st.subheader("Actividad por dia")
        col1, col2 = st.columns(2)

        with col1:
            st.write("**Traces por dia**")
            traces_data = [
                {"fecha": d["fecha"], "traces": d["traces"]}
                for d in metricas["traces_por_dia"]
            ]
            st.bar_chart(traces_data, x="fecha", y="traces")

        with col2:
            st.write("**Tokens por dia**")
            tokens_data = [
                {"fecha": d["fecha"], "tokens": d["tokens"]}
                for d in metricas["traces_por_dia"]
            ]
            st.bar_chart(tokens_data, x="fecha", y="tokens")

    # 2. Latencia: recuperacion vs LLM vs total
    if metricas["traces_por_dia"]:
        st.subheader("Latencia por dia (segundos)")
        latencia_data = [
            {
                "fecha": d["fecha"],
                "Recuperacion": d["latencia_rec"],
                "LLM": d["latencia_llm"],
                "Total": d["latencia_avg"],
            }
            for d in metricas["traces_por_dia"]
        ]
        st.line_chart(latencia_data, x="fecha")

    # 3. Costo por dia
    if metricas["traces_por_dia"]:
        st.subheader("Costo por dia (USD)")
        costo_data = [
            {"fecha": d["fecha"], "costo_usd": d["costo"]}
            for d in metricas["traces_por_dia"]
        ]
        st.bar_chart(costo_data, x="fecha", y="costo_usd")

    st.divider()

    # 4. Por modelo
    if metricas["por_modelo"]:
        st.subheader("Uso por modelo LLM")
        col1, col2 = st.columns(2)

        with col1:
            st.write("**Llamadas por modelo**")
            modelo_data = [
                {"modelo": m["modelo"], "llamadas": m["llamadas"]}
                for m in metricas["por_modelo"]
            ]
            st.bar_chart(modelo_data, x="modelo", y="llamadas")

        with col2:
            st.write("**Tokens por modelo**")
            modelo_tokens = [
                {"modelo": m["modelo"], "tokens": m["total_tokens"]}
                for m in metricas["por_modelo"]
            ]
            st.bar_chart(modelo_tokens, x="modelo", y="tokens")

        # Tabla detallada por modelo
        st.write("**Detalle por modelo:**")
        st.table([
            {
                "Modelo": m["modelo"],
                "Llamadas": m["llamadas"],
                "Prompt tokens": m["prompt_tokens"],
                "Completion tokens": m["completion_tokens"],
                "Total tokens": m["total_tokens"],
                "Costo USD": f"${m['costo']:.4f}",
                "Latencia avg": f"{m['latencia_avg']:.2f}s",
            }
            for m in metricas["por_modelo"]
        ])

    st.divider()

    # 5. Distribucion de latencia
    if metricas["latencia_dist"]:
        st.subheader("Distribucion de latencia")
        lat_dist_data = [
            {"rango": d["rango"], "count": d["count"]}
            for d in metricas["latencia_dist"]
        ]
        st.bar_chart(lat_dist_data, x="rango", y="count")

    # 6. Tokens prompt vs completion
    if metricas["tokens_por_dia"]:
        st.subheader("Prompt vs Completion tokens por dia")
        tok_split = [
            {
                "fecha": d["fecha"],
                "Prompt": d["prompt"],
                "Completion": d["completion"],
            }
            for d in metricas["tokens_por_dia"]
        ]
        st.line_chart(tok_split, x="fecha")

    st.divider()

    # 7. Feedback del usuario
    st.subheader("Feedback del usuario")
    fb_stats = metricas["feedback"]
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Utiles", fb_stats["positive"])
    with col2:
        st.metric("No utiles", fb_stats["negative"])
    with col3:
        st.metric("Total", fb_stats["total"])
    if fb_stats["total"] > 0:
        pct = (fb_stats["positive"] / fb_stats["total"]) * 100
        st.progress(pct / 100, text=f"Satisfaccion: {pct:.0f}%")
    else:
        st.info("Aun no hay feedback. Usa los botones Util / No util en el Chat.")

    st.divider()

    # 8. Traces recientes
    if metricas["traces_recientes"]:
        st.subheader("Traces recientes (ultimas 20)")
        st.table([
            {
                "Timestamp": t["timestamp"][:19],
                "Pregunta": t["pregunta"],
                "Modelo": t["modelo"],
                "Tokens": t["tokens"],
                "Costo": f"${t['costo']:.4f}",
                "Latencia": f"{t['latencia']:.1f}s",
                "Docs": t["documentos"],
                "Skills": t["skills"],
            }
            for t in metricas["traces_recientes"]
        ])

    if dashboard["total_traces"] == 0:
        st.info("No hay datos FinOps aun. Haz preguntas al agente para generar trazas.")

with tab_docs:
    st.markdown("""
    <div class="main-header">
        <h1>Visor de Documentos</h1>
        <p>Consulta documentos completos con metadatos de Integr@</p>
    </div>
    """, unsafe_allow_html=True)

    # Busqueda
    col1, col2 = st.columns([3, 1])
    with col1:
        busqueda = st.text_input("Buscar por codigo, nombre o proceso:", placeholder="Ej: PGC-11, temperatura, almacenamiento...")
    with col2:
        limite = st.selectbox("Resultados:", [20, 50, 100, 200], index=0)

    # Buscar documentos
    docs_lista = rag.buscar_documentos(busqueda, top_k=limite)

    st.caption(f"{len(docs_lista)} documentos encontrados")

    if docs_lista:
        # Selector de documento
        opciones = [f"{d['codigo']} - {d['nombre'][:60]}" for d in docs_lista]
        seleccion = st.selectbox("Selecciona un documento para verlo completo:", opciones)

        if seleccion:
            codigo_sel = seleccion.split(" - ")[0]
            doc = rag.get_documento(codigo_sel)

            if doc:
                st.divider()

                # Encabezado
                st.subheader(f"{doc['codigo']} - {doc['nombre']}")

                # Metricas principales
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    estado = doc.get("estado", "N/A")
                    icon = estado_icon(estado)
                    st.metric("Estado", f"{icon} {estado} - {_ESTADO_DESC.get(estado, 'N/A')}")
                with col2:
                    st.metric("Proceso", doc.get("proceso", "N/A"))
                with col3:
                    st.metric("Tipo", doc.get("tipo_documento", "N/A"))
                with col4:
                    st.metric("Vigencia (dias)", doc.get("vigencia_dias", "N/A"))

                # Fechas
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"Fecha publicacion: {doc.get('fecha_publicacion', 'N/A')}")
                with col2:
                    if doc.get("fecha_vencimiento"):
                        dias = doc.get("dias_restantes", 0)
                        alerta = doc.get("estado_alerta", "")
                        if alerta == "VENCIDO":
                            st.caption(f"Fecha vencimiento: {doc['fecha_vencimiento']} (vencido hace {abs(dias)} dias)")
                        elif dias is not None and dias <= 30:
                            st.caption(f"Fecha vencimiento: {doc['fecha_vencimiento']} (vence en {dias} dias)")
                        else:
                            st.caption(f"Fecha vencimiento: {doc['fecha_vencimiento']}")

                st.divider()

                # Resumen ejecutivo
                if doc.get("resumen"):
                    st.subheader("Resumen Ejecutivo")
                    st.write(doc["resumen"])

                    col1, col2 = st.columns(2)
                    with col1:
                        if doc.get("proposito"):
                            st.write(f"**Proposito:** {doc['proposito']}")
                    with col2:
                        if doc.get("alcance"):
                            st.write(f"**Alcance:** {doc['alcance']}")
                    if doc.get("palabras_clave"):
                        st.caption(f"Palabras clave: {doc['palabras_clave']}")
                    st.divider()

                # Contexto del grafo
                if doc.get("grafo_procesos") or doc.get("grafo_temas") or doc.get("docs_relacionados"):
                    st.subheader("Contexto del Grafo")
                    col1, col2 = st.columns(2)
                    with col1:
                        if doc.get("grafo_procesos"):
                            st.write(f"**Procesos:** {', '.join(doc['grafo_procesos'])}")
                        if doc.get("grafo_temas"):
                            st.write(f"**Temas:** {', '.join(doc['grafo_temas'])}")
                    with col2:
                        if doc.get("grafo_usuarios"):
                            usuarios_str = ", ".join([f"{u['nombre']} ({u['rol']})" for u in doc['grafo_usuarios']])
                            st.write(f"**Usuarios:** {usuarios_str}")

                    if doc.get("docs_relacionados"):
                        st.write("**Documentos relacionados:**")
                        for d in doc["docs_relacionados"]:
                            st.write(f"  - {d['codigo']} - {d['nombre'][:50]} ({d['relation']})")
                    st.divider()

                # Texto completo
                st.subheader("Contenido del Documento")
                texto = doc.get("texto", "")
                if texto:
                    # Mostrar en un area expandible
                    with st.expander("Ver texto completo", expanded=True):
                        st.text_area("Texto", texto, height=500, key=f"texto_{codigo_sel}")
                else:
                    st.warning("No hay texto disponible para este documento.")

                # Boton para copiar codigo
                st.caption(f"Codigo del documento: {doc['codigo']}")
            else:
                st.error(f"No se encontro el documento {codigo_sel}")

with tab_comp:
    st.markdown("""
    <div class="main-header">
        <h1>Comparador de Versiones de Documentos</h1>
        <p>Compara dos versiones de un procedimiento para ver que cambio</p>
    </div>
    """, unsafe_allow_html=True)
    st.write("Compara dos versiones de un procedimiento para ver que cambio.")

    # Buscar grupos de versiones
    if "grupos_versiones" not in st.session_state:
        with st.spinner("Buscando versiones..."):
            st.session_state.grupos_versiones = rag.buscar_versiones()

    grupos = st.session_state.grupos_versiones

    if not grupos:
        st.info("No se encontraron documentos con multiples versiones.")
    else:
        st.write(f"**{len(grupos)}** documentos con multiples versiones encontrados.")

        # Seleccionar grupo
        opciones_grupos = [
            f"{g['nombre'][:60]} ({g['num_versiones']} versiones)"
            for g in grupos
        ]
        grupo_sel_idx = st.selectbox(
            "Selecciona un documento:",
            range(len(opciones_grupos)),
            format_func=lambda i: opciones_grupos[i],
        )

        grupo_sel = grupos[grupo_sel_idx]
        st.divider()

        # Mostrar versiones disponibles
        st.subheader(f"Versiones de: {grupo_sel['nombre']}")
        versiones = grupo_sel["versiones"]

        # Tabla de versiones
        st.table([
            {
                "Codigo": v["codigo"],
                "Estado": v["estado_desc"] or v["estado"],
                "Fecha elaboracion": v["fecha_elaboracion"] or "N/A",
                "Fecha publicacion": v["fecha_publicacion"] or "N/A",
                "Longitud texto": v["texto_length"] or 0,
            }
            for v in versiones
        ])

        # Seleccionar dos versiones para comparar
        col1, col2 = st.columns(2)
        with col1:
            codigos = [v["codigo"] for v in versiones]
            codigo1 = st.selectbox("Version A (original):", codigos, index=0)
        with col2:
            codigo2 = st.selectbox("Version B (nueva):", codigos, index=min(1, len(codigos)-1))

        if codigo1 and codigo2 and codigo1 != codigo2:
            if st.button("Comparar", type="primary"):
                with st.spinner("Comparando documentos..."):
                    resultado = rag.comparar_documentos(codigo1, codigo2)

                if "error" in resultado:
                    st.error(resultado["error"])
                else:
                    st.divider()

                    # Metricas de comparacion
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        sim_pct = resultado["similitud"] * 100
                        st.metric("Similitud", f"{sim_pct:.1f}%")
                    with col2:
                        st.metric("Lineas agregadas", resultado["lineas_agregadas"])
                    with col3:
                        st.metric("Lineas eliminadas", resultado["lineas_eliminadas"])
                    with col4:
                        st.metric("Lineas modificadas", resultado["lineas_modificadas"])

                    # Barra de similitud
                    st.progress(resultado["similitud"], text=f"Similitud: {sim_pct:.1f}%")

                    # Informacion de los documentos
                    st.divider()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Version A: {resultado['doc1']['codigo']}**")
                        st.write(f"Estado: {resultado['doc1']['estado']}")
                        st.write(f"Fecha: {resultado['doc1']['fecha_publicacion'] or 'N/A'}")
                        st.write(f"Longitud: {resultado['doc1']['texto_length']} chars")
                    with col2:
                        st.write(f"**Version B: {resultado['doc2']['codigo']}**")
                        st.write(f"Estado: {resultado['doc2']['estado']}")
                        st.write(f"Fecha: {resultado['doc2']['fecha_publicacion'] or 'N/A'}")
                        st.write(f"Longitud: {resultado['doc2']['texto_length']} chars")

                    # Diff lado a lado
                    st.divider()
                    st.subheader("Diferencias linea por linea")

                    diff_lado = resultado["diff_lado_a_lado"]
                    if not diff_lado:
                        st.info("Los documentos son identicos.")
                    else:
                        # Mostrar diff con colores
                        diff_html = []
                        for linea in diff_lado[:500]:  # Limitar a 500 lineas
                            tipo = linea["tipo"]
                            texto = linea["linea"]
                            if tipo == "igual":
                                diff_html.append(f"  {texto}")
                            elif tipo == "agregada":
                                diff_html.append(f"+ {texto}")
                            elif tipo == "eliminada":
                                diff_html.append(f"- {texto}")

                        # Mostrar como codigo con colores
                        for linea in diff_lado[:500]:
                            tipo = linea["tipo"]
                            texto = linea["linea"][:200]
                            if tipo == "igual":
                                st.text(f"  {texto}")
                            elif tipo == "agregada":
                                st.markdown(f":green[+ {texto}]")
                            elif tipo == "eliminada":
                                st.markdown(f":red[- {texto}]")

                        if len(diff_lado) > 500:
                            st.caption(f"... y {len(diff_lado) - 500} lineas mas.")

                    # Diff unificado descargable
                    st.divider()
                    st.download_button(
                        label="Descargar diff unificado (.diff)",
                        data=resultado["diff_unificado"].encode("utf-8"),
                        file_name=f"diff_{codigo1}_vs_{codigo2}.diff",
                        mime="text/plain",
                    )
        elif codigo1 == codigo2:
            st.warning("Selecciona dos versiones diferentes para comparar.")

with tab_arq:
    st.markdown("""
    <div class="main-header">
        <h1>Arquitectura del Agente de Calidad</h1>
        <p>Vistas por tipo: empresarial, negocio, soluciones, datos, ciberseguridad y mas</p>
    </div>
    """, unsafe_allow_html=True)

    tipos_arquitectura = [
        "Empresarial", "Negocio", "Soluciones", "Datos",
        "Ciberseguridad", "Integraciones", "Aplicacion", "Infraestructura",
    ]
    tipo_sel = st.selectbox("Selecciona el tipo de arquitectura:", tipos_arquitectura)
    st.divider()

    if tipo_sel == "Empresarial":
        st.subheader("Arquitectura Empresarial")
        st.write("Como el agente se integra en la organizacion de Solistica.")
        st.code(
            "  +---------------------+\n"
            "  |   SOLISTICA (AGV)   |\n"
            "  |   Operador logistico|\n"
            "  +----------+----------+\n"
            "             |\n"
            "  +----------+----------+\n"
            "  |  DIRECCION CALIDAD   |\n"
            "  |  HSEQ / QA           |\n"
            "  +----------+----------+\n"
            "             |\n"
            "  +----------+----------+\n"
            "  |  PLATAFORMA INTEGRA  |\n"
            "  |  (SQL Server)        |\n"
            "  |  132 tablas dbo      |\n"
            "  +----------+----------+\n"
            "             |\n"
            "  +----------+----------+\n"
            "  |  AGENTE DE CALIDAD   |\n"
            "  |  (Graph RAG + LLM)   |\n"
            "  +----------+----------+\n"
            "             |\n"
            "  +----------+----------+\n"
            "  |  USUARIOS FINALES    |\n"
            "  |  - Auditores         |\n"
            "  |  - Asoc. calidad     |\n"
            "  |  - Coordinadores     |\n"
            "  |  - Gerencia          |\n"
            "  +---------------------+\n",
            language="text"
        )
        st.write("**Dominios cubiertos:**")
        st.write("- Gestion documental (SOPs, procedimientos, formatos)")
        st.write("- Gestion de no conformidades (NC, CAPA, planes de accion)")
        st.write("- Auditorias (Invima, ISO, internas)")
        st.write("- Control de vigencia documental")
        st.write("- Estandarizacion documental")
        st.write("- Comparacion de versiones de documentos")
        st.write("- Gobernanza AI (guardrails, PII, moderation)")
        st.write("- Observabilidad y FinOps (dashboard, metricas)")

    elif tipo_sel == "Negocio":
        st.subheader("Arquitectura de Negocio")
        st.write("Procesos de negocio soportados por el agente.")
        st.code(
            "  PROCESOS DE NEGOCIO SOPORTADOS\n"
            "  ================================\n\n"
            "  1. GESTION DOCUMENTAL\n"
            "     - Consulta de procedimientos vigentes\n"
            "     - Busqueda semantica por tema/proceso\n"
            "     - Control de versiones y obsoletos\n"
            "     - Alertas de vencimiento\n"
            "     - Comparador de versiones (diff)\n"
            "     - Visor de documentos completos\n\n"
            "  2. GESTION DE NO CONFORMIDADES\n"
            "     - Elementos de una NC\n"
            "     - Correccion inmediata\n"
            "     - Analisis de causa raiz (5 porques, Ishikawa)\n"
            "     - Planes de accion (CAPA)\n"
            "     - Verificacion de eficacia\n\n"
            "  3. AUDITORIAS\n"
            "     - Simulacion de auditorias\n"
            "     - Checklist Invima/ISO\n"
            "     - Hallazgos y desviaciones\n\n"
            "  4. CALIFICACION DE EQUIPOS\n"
            "     - IQ / OQ / PQ\n"
            "     - Protocolos y reportes\n\n"
            "  5. CADENA DE FRIO\n"
            "     - Control de temperatura\n"
            "     - Cuartos frios, neveras\n"
            "     - Monitoreo y desviaciones\n\n"
            "  6. RECEPCION DE MERCANCIA\n"
            "     - Inspeccion de entrada\n"
            "     - Documentacion requerida\n"
            "     - Criterios de aceptacion/rechazo\n\n"
            "  7. GOBERNANZA Y CUMPLIMIENTO\n"
            "     - Governance AI (guardrails)\n"
            "     - PII filter (11 tipos)\n"
            "     - Prompt injection (30+ patrones)\n"
            "     - Content moderation\n"
            "     - Auditoria completa\n\n"
            "  8. OBSERVABILIDAD Y FINOPS\n"
            "     - Dashboard interactivo\n"
            "     - Metricas en tiempo real\n"
            "     - Feedback del usuario\n"
            "     - Exportar conversaciones",
            language="text"
        )
        st.write("**Metricas de impacto:**")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Documentos indexados", "2805")
        with col2:
            st.metric("Procesos cubiertos", "24")
        with col3:
            st.metric("Temas detectados", "15")
        with col4:
            st.metric("Terminos glosario", "55")

    elif tipo_sel == "Soluciones":
        st.subheader("Arquitectura de Soluciones")
        st.write("Componentes tecnicos de la solucion Graph RAG avanzado.")
        st.code(
            "  +--------------------------------------------------+ \n"
            "  |              AGENTE GRAPH RAG                     | \n"
            "  +--------------------------------------------------+ \n"
            "  |                                                    | \n"
            "  |  0. GUARDRAILS DE ENTRADA                          | \n"
            "  |  +-------+   +-------+   +-------+                | \n"
            "  |  |Govern.|   |Modera.|   |Cache  |                | \n"
            "  |  |(PII,  |   |(Toxic.|   |(Seman.|                | \n"
            "  |  |Inject)|   | Hate) |   | 0.85) |                | \n"
            "  |  +---+---+   +---+---+   +---+---+                | \n"
            "  |      |           |           |                    | \n"
            "  |  1. HyDE + MULTI-QUERY                            | \n"
            "  |  +-------+   +-------+                            | \n"
            "  |  |HyDE   |   |Multi  |                            | \n"
            "  |  |(doc   |   |query  |                            | \n"
            "  |  |hipot.)|   |(3 var)|                            | \n"
            "  |  +---+---+   +---+---+                            | \n"
            "  |      |           |                                | \n"
            "  |  2. RECUPERACION HIBRIDA (multi-vector)           | \n"
            "  |  +-------+   +-------+   +-------+                | \n"
            "  |  |BM25   |   |FAISS  |   |GRAFO  |                | \n"
            "  |  |(lexico|   |(seman |   |(relac |                | \n"
            "  |  |  +vars|   |  +HyDE|   |  BFS  |                | \n"
            "  |  +---+---+   +---+---+   +---+---+                | \n"
            "  |      +-----+-----+-----+-----+                    | \n"
            "  |            |               |                      | \n"
            "  |  3. CRAG (evaluar calidad)                        | \n"
            "  |  +-------+   +-------+   +-------+                | \n"
            "  |  | good  |   | ambig.|   | poor  |                | \n"
            "  |  |(proce.|   |(proce.|   |(expan.|                | \n"
            "  |  |  der) |   |  der) |   |  dir) |                | \n"
            "  |  +---+---+   +---+---+   +---+---+                | \n"
            "  |            |               |                      | \n"
            "  |  4. CROSS-ENCODER + PARENT-CHILD                  | \n"
            "  |  +-------+   +-------+                            | \n"
            "  |  |Cross  |   |Parent |                            | \n"
            "  |  |encoder|   |child  |                            | \n"
            "  |  |(rerank|   |(sec   |                            | \n"
            "  |  | local)|   |ciones)|                            | \n"
            "  |  +---+---+   +---+---+                            | \n"
            "  |            |               |                      | \n"
            "  |  5. CONTEXT + LLM (streaming)                     | \n"
            "  |  +-------+   +-------+   +-------+                | \n"
            "  |  |Skills |   |Glosar.|   |Resumen|                | \n"
            "  |  |(6)    |   |(55)   |   |(ejec.)|                | \n"
            "  |  +---+---+   +---+---+   +---+---+                | \n"
            "  |            |               |                      | \n"
            "  |  6. GUARDRAILS DE SALIDA                           | \n"
            "  |  +-------+   +-------+   +-------+                | \n"
            "  |  |PII    |   |Modera.|   |Cache  |                | \n"
            "  |  |filter |   |(salida|   |(set)  |                | \n"
            "  |  +-------+   +-------+   +-------+                | \n"
            "  +--------------------------------------------------+ \n",
            language="text"
        )
        st.write("**Flujo de una consulta:**")
        st.write("1. Governance valida entrada (prompt injection, SQL, tópicos)")
        st.write("2. Content moderation verifica entrada (toxicidad, hate speech)")
        st.write("3. Cache semántico: si ya respondimos, devolver cache")
        st.write("4. HyDE: LLM genera documento hipotético (mejora recall)")
        st.write("5. Multi-query: 3 variantes de la pregunta (mejora recall)")
        st.write("6. BM25 + FAISS + Grafo recuperan candidatos (multi-vector fusion)")
        st.write("7. CRAG: evalúa calidad (good/ambiguous/poor), expande si es poor")
        st.write("8. Cross-encoder rerankea + parent-child obtiene secciones relevantes")
        st.write("9. Se construye contexto con glosario, resumenes y skills")
        st.write("10. LLM genera respuesta en streaming (tokens en vivo)")
        st.write("11. Governance filtra PII y valida salida")
        st.write("12. Content moderation verifica salida")
        st.write("13. Cache set: guarda respuesta para futuras consultas")

    elif tipo_sel == "Datos":
        st.subheader("Arquitectura de Datos")
        st.write("Flujo de datos desde Integr@ hasta el usuario.")
        st.code(
            "  +-------------------+     +-------------------+ \n"
            "  | SQL SERVER INTEGRA|     |   SQLITE LOCAL    | \n"
            "  | 10.238.66.14      |     | indice_procedim   | \n"
            "  | 132 tablas dbo    | --> | .db (27 tablas)   | \n"
            "  |                   |     |                   | \n"
            "  | PROCEDIMIENTOS    |     | DATOS:            | \n"
            "  | ProcedimientoEst  |     |  procedimientos   | \n"
            "  | NoConformidad     |     |  embeddings       | \n"
            "  | PlanesAccionNC    |     |  temas            | \n"
            "  | Proceso           |     |  documento_tema   | \n"
            "  | TipoDocumento     |     |  glosario (55)    | \n"
            "  | USUARIOT          |     |  diccionario_datos| \n"
            "  | Formatos          |     |  resumenes        | \n"
            "  | DocumenExternos   |     |  tabla_jerarquica | \n"
            "  +-------------------+     |  alertas_vencim   | \n"
            "                            |  inventario_meta   | \n"
            "  +-------------------+     |  grafo_nodos      | \n"
            "  |   CHROMADB        |     |  grafo_aristas    | \n"
            "  |   chroma_db/      |     |  doc_secciones    | \n"
            "  |   2805 docs       |     | FINOPS:           | \n"
            "  +-------------------+     |  finops_traces    | \n"
            "                            |  finops_llm_calls | \n"
            "  +-------------------+     |  finops_daily_sum | \n"
            "  |   EMBEDDINGS      | --> | GOVERNANCE:       | \n"
            "  |   Mistral 1024d   |     |  auditoria        | \n"
            "  |   + cache queries |     |  moderation_log   | \n"
            "  +-------------------+     |  rate_limits      | \n"
            "                            | MEMORIA:          | \n"
            "  +-------------------+     |  cache_respuestas | \n"
            "  |   FAISS INDEX     |     |  sesiones         | \n"
            "  | faiss_index.bin   |     |  mensajes         | \n"
            "  | 2805 vectores     |     |  knowledge_facts  | \n"
            "  +-------------------+     |  checkpoints      | \n"
            "                            |  context_summaries| \n"
            "                            |  topic_history    | \n"
            "                            | FEEDBACK:         | \n"
            "                            |  feedback_usuario | \n"
            "                            +-------------------+ \n",
            language="text"
        )
        st.write("**Tablas SQLite (27 tablas):**")
        tablas = [
            ("procedimientos", "Documentos + texto extraido", "2805"),
            ("embeddings", "Backup de embeddings", "2805"),
            ("temas", "Temas detectados por clustering", "15"),
            ("documento_tema", "Relacion documento-tema", "2805"),
            ("documento_secciones", "Secciones chunked por documento", "variable"),
            ("glosario", "Terminos de calidad+logistica+estados", "55"),
            ("diccionario_datos", "Campos de Integra explicados", "132"),
            ("resumenes", "Resumenes ejecutivos", "variable"),
            ("tabla_jerarquica", "Estructura Proceso-Tipo-Doc", "24 procesos"),
            ("alertas_vencimiento", "Docs vencidos/por vencer", "variable"),
            ("inventario_metadatos", "Inventario por categoria", "variable"),
            ("grafo_nodos", "Nodos del grafo persistente", "3333"),
            ("grafo_aristas", "Aristas del grafo", "17899"),
            ("finops_traces", "Trazas de cada consulta", "variable"),
            ("finops_llm_calls", "Llamadas LLM individuales", "variable"),
            ("finops_daily_summary", "Resumen diario FinOps", "variable"),
            ("cache_respuestas", "Cache semantico de respuestas", "variable"),
            ("sesiones", "Sesiones persistentes", "variable"),
            ("mensajes", "Mensajes de sesiones", "variable"),
            ("knowledge_facts", "Hechos estructurados", "variable"),
            ("checkpoints", "Estado de tareas largas", "variable"),
            ("context_summaries", "Resumenes de contexto", "variable"),
            ("topic_history", "Historial de temas", "variable"),
            ("auditoria", "Log de auditoria governance", "variable"),
            ("moderation_log", "Log de content moderation", "variable"),
            ("rate_limits", "Contadores de rate limiting", "variable"),
            ("feedback_usuario", "Feedback thumbs up/down", "variable"),
        ]
        st.table([{"Tabla": t[0], "Contenido": t[1], "Registros": t[2]} for t in tablas])

    elif tipo_sel == "Ciberseguridad":
        st.subheader("Arquitectura de Ciberseguridad")
        st.write("Capas de seguridad del agente (integradas en graph_rag.py y agente_integra.py).")
        st.code(
            "  CAPAS DE SEGURIDAD (GOVERNANCE AI)\n"
            "  ===================================\n\n"
            "  Capa 1: GUARDRAILS DE ENTRADA (governance.py)\n"
            "  +----------------------------------+\n"
            "  | - Prompt injection (30+ patrones)|\n"
            "  |   ES: ignora instrucciones,      |\n"
            "  |       modo desarrollador, DAN... |\n"
            "  |   EN: ignore previous, override, |\n"
            "  |       reveal system prompt...    |\n"
            "  | - Encoding sospechoso (b64/hex)  |\n"
            "  | - SQL peligroso (DELETE/DROP)    |\n"
            "  | - Topicos prohibidos             |\n"
            "  | - Rate limiting (100h / 500d)    |\n"
            "  | - Longitud maxima                |\n"
            "  +----------------------------------+\n\n"
            "  Capa 2: CONTENT MODERATION (entrada)\n"
            "  +----------------------------------+\n"
            "  | - Toxicidad / hate speech        |\n"
            "  | - Acoso / autolesion             |\n"
            "  | - Spam / URLs sospechosas        |\n"
            "  | - Whitelist terminos calidad     |\n"
            "  +----------------------------------+\n\n"
            "  Capa 3: SQL SERVER (read-only)\n"
            "  +----------------------------------+\n"
            "  | - Conexion solo lectura          |\n"
            "  | - Solo SELECT, no DML/DDL        |\n"
            "  | - Validacion antes de ejecutar   |\n"
            "  +----------------------------------+\n\n"
            "  Capa 4: GUARDRAILS DE SALIDA (governance.py)\n"
            "  +----------------------------------+\n"
            "  | - PII filter:                    |\n"
            "  |   email, telefono, cedula,       |\n"
            "  |   tarjeta, IBAN, direccion,      |\n"
            "  |   placa, salario, password       |\n"
            "  | - Credenciales (sk-, gsk_, AIza) |\n"
            "  | - Whitelist: codigos Integra     |\n"
            "  +----------------------------------+\n\n"
            "  Capa 5: CONTENT MODERATION (salida)\n"
            "  +----------------------------------+\n"
            "  | - Verifica respuesta segura      |\n"
            "  | - Filtra contenido inapropiado   |\n"
            "  +----------------------------------+\n\n"
            "  Capa 6: AUDITORIA (governance.py)\n"
            "  +----------------------------------+\n"
            "  | - user_id, pregunta, respuesta   |\n"
            "  | - modelo, tokens, costo, latency |\n"
            "  | - rechazada? razon? tool_used?   |\n"
            "  | - SQLite + LangFuse (opcional)   |\n"
            "  +----------------------------------+\n",
            language="text"
        )
        st.write("**Integracion en graph_rag.py (Streamlit):**")
        st.write("- Entrada: `governance.validate_input()` + `moderation.moderate()`")
        st.write("- Salida: `governance.validate_output()` + `governance._filter_pii()` + `moderation.moderate()`")
        st.write("**Principios de seguridad:**")
        st.write("- Acceso a Integr@: solo lectura (read-only)")
        st.write("- API keys: nunca en codigo fuente ni respuestas")
        st.write("- SQL: solo SELECT validado antes de ejecutar")
        st.write("- PII: filtrado automatico en salida")
        st.write("- Auditoria: todas las interacciones se registran")
        st.write("- Defense in depth: 6 capas de seguridad")

    elif tipo_sel == "Integraciones":
        st.subheader("Arquitectura de Integraciones")
        st.write("Sistemas externos con los que se integra el agente.")
        st.code(
            "  +-------------------+ \n"
            "  |   AGENTE RAG      | \n"
            "  +---+---+---+---+---+ \n"
            "      |   |   |   |    \n"
            "      v   v   v   v    \n"
            "  +---+---+---+---+---+ \n"
            "  |   |   |   |   |    \n"
            "  v   v   v   v   v    \n"
            "  SQL  LLM EMB OBS WEB \n"
            "  Srv  API API SER IT \n"
            "  |    |   |   |   |   \n"
            "  v    v   v   v   v   \n"
            "  +----+---+---+---+--+\n"
            "  |SQL |LLM|EMB|OBS|UI|\n"
            "  |Srv |   |   |   |   |\n"
            "  |Int |   |   |   |   |\n"
            "  |egra|   |   |   |   |\n"
            "  +----+---+---+---+---+\n",
            language="text"
        )
        st.write("**Sistemas integrados:**")
        integraciones = [
            ("SQL Server Integr@", "10.238.66.14", "pyodbc", "Solo lectura", "Documentos, NC, CAPA"),
            ("OpenAI API", "api.openai.com", "openai SDK", "HTTPS", "Chat + embeddings (bloqueado por firewall)"),
            ("Mistral API", "api.mistral.ai", "openai SDK", "HTTPS", "Chat + embeddings"),
            ("Ollama", "localhost:11434", "openai SDK", "HTTP local", "Chat local (fallback)"),
            ("Groq API", "api.groq.com", "openai SDK", "HTTPS", "Chat (fallback rapido)"),
            ("Gemini API", "googleapis.com", "openai SDK", "HTTPS", "Chat (fallback)"),
            ("LangFuse", "cloud.langfuse.com", "langfuse SDK", "HTTPS", "Observabilidad (opcional)"),
            ("Streamlit", "localhost:8501", "streamlit", "HTTP local", "Interfaz web"),
            ("FastAPI", "localhost:8000", "uvicorn", "HTTP local", "API REST"),
        ]
        st.table([{
            "Sistema": i[0], "Endpoint": i[1], "SDK": i[2],
            "Protocolo": i[3], "Funcion": i[4]
        } for i in integraciones])

    elif tipo_sel == "Aplicacion":
        st.subheader("Arquitectura de Aplicacion")
        st.write("Modulos y componentes del agente.")
        st.code(
            "  MODULOS PRINCIPALES\n"
            "  ===================\n\n"
            "  graph_rag.py (nucleo)\n"
            "  ├── llm_providers.py    (fallback LLM + streaming)\n"
            "  ├── governance.py       (guardrails entrada/salida)\n"
            "  ├── content_moderation.py (moderacion entrada/salida)\n"
            "  ├── memoria.py          (cache semantico + sesiones)\n"
            "  ├── context_manager.py  (gestion contexto)\n"
            "  ├── observabilidad.py   (trazas + FinOps)\n"
            "  ├── glosario.py         (55 terminos + estados)\n"
            "  ├── skills/             (6 skills dinamicos)\n"
            "  │   ├── mermaid.md\n"
            "  │   ├── capa.md\n"
            "  │   ├── no_conformidad.md\n"
            "  │   ├── auditoria.md\n"
            "  │   ├── checklists.md\n"
            "  │   └── refactoring_sops.md\n"
            "  ├── system_prompt.md    (prompt consultor)\n"
            "  └── integra_db_client.py (SQL Server)\n\n"
            "  TECNICAS RAG AVANZADAS\n"
            "  ├── HyDE               (documento hipotetico)\n"
            "  ├── Multi-query         (3 variantes de query)\n"
            "  ├── BM25               (lexical, rank_bm25)\n"
            "  ├── FAISS              (semantico, 2805 vectores)\n"
            "  ├── Graph BFS          (NetworkX, 2 hops)\n"
            "  ├── CRAG               (good/ambiguous/poor)\n"
            "  ├── Cross-encoder      (ms-marco-MiniLM-L-6-v2)\n"
            "  ├── Parent-child       (secciones relevantes)\n"
            "  ├── Cache semantico    (exacto + similarity 0.85)\n"
            "  ├── Cache embeddings   (max 500 queries)\n"
            "  └── Streaming          (tokens en vivo)\n\n"
            "  INTERFACES\n"
            "  ├── web_ui.py           (Streamlit, 9 paginas)\n"
            "  │   ├── Chat            (streaming + feedback + export)\n"
            "  │   ├── Estadisticas    (grafo)\n"
            "  │   ├── Jerarquia       (procesos)\n"
            "  │   ├── Vencidos        (alertas)\n"
            "  │   ├── Glosario        (55 terminos)\n"
            "  │   ├── FinOps          (dashboard interactivo)\n"
            "  │   ├── Documentos      (visor)\n"
            "  │   ├── Comparador      (diff versiones)\n"
            "  │   └── Arquitectura    (8 vistas)\n"
            "  ├── api_rest.py         (FastAPI)\n"
            "  └── graph_rag.py        (CLI interactivo)\n\n"
            "  PIPELINE DE DATOS (8 pasos)\n"
            "  ├── build_document_index.py  (Paso 1)\n"
            "  ├── generate_embeddings.py   (Paso 2)\n"
            "  ├── cluster_temas.py         (Paso 3)\n"
            "  ├── glosario.py              (Paso 4)\n"
            "  ├── diccionario_datos.py     (Paso 5)\n"
            "  ├── generar_resumenes.py     (Paso 6)\n"
            "  ├── inventario_metadatos.py  (Paso 7)\n"
            "  └── graph_rag.py             (Paso 8)\n",
            language="text"
        )
        st.write("**Skills dinamicos (6):**")
        skills = [
            ("Mermaid", "Flujos, diagramas, Ishikawa, arboles de decision"),
            ("CAPA", "Causa raiz, 5 porques, FMEA, AMEF, 6M, NPR"),
            ("No Conformidad", "NC, hallazgos, desviaciones, planes de accion"),
            ("Auditoria", "Simular auditoria, roleplay, Invima/ISO"),
            ("Checklists", "Formatos, checklists, WMS, Power Apps"),
            ("Refactoring SOPs", "Revisar borradores, auditar calidad documental"),
        ]
        st.table([{"Skill": s[0], "Se activa con": s[1]} for s in skills])

        st.write("**Tecnicas RAG implementadas (11):**")
        tecnicas = [
            ("HyDE", "LLM genera doc hipotetico", "+10-15% recall"),
            ("Multi-query", "3 variantes de la query", "+10% recall"),
            ("BM25", "Lexical con saturacion", "Reemplaza TF-IDF"),
            ("FAISS", "Semantico ultra-rapido", "2805 vectores"),
            ("Graph BFS", "Expansion por grafo", "2 hops, 3333 nodos"),
            ("CRAG", "Evalua calidad retrieval", "good/ambig/poor"),
            ("Cross-encoder", "Reranking local", "MiniLM-L-6-v2"),
            ("Parent-child", "Secciones relevantes", "BM25 dentro doc"),
            ("Cache semantico", "Respuestas cacheadas", "exacto + 0.85"),
            ("Cache embeddings", "Embeddings de query", "max 500 en RAM"),
            ("Streaming", "Tokens en vivo", "st.write_stream"),
        ]
        st.table([{"Tecnica": t[0], "Descripcion": t[1], "Beneficio": t[2]} for t in tecnicas])

    elif tipo_sel == "Infraestructura":
        st.subheader("Arquitectura de Infraestructura")
        st.write("Infraestructura fisica y de red.")
        st.code(
            "  +---------------------+ \n"
            "  |  EQUIPO USUARIO     | \n"
            "  |  Windows 11         | \n"
            "  |  Python 3.14        | \n"
            "  |  Ollama (local)     | \n"
            "  +----------+----------+ \n"
            "             |            \n"
            "  +----------+----------+ \n"
            "  |  RED CORPORATIVA    | \n"
            "  |  Gateway 172.16.240 | \n"
            "  |  DNS 10.238.66.63   | \n"
            "  +---+--------+--------+ \n"
            "      |        |          \n"
            "      v        v          \n"
            "  +---+---+ +--+------+   \n"
            "  |SQL Srv| |Internet |   \n"
            "  |Integra| |         |   \n"
            "  |10.238 | | Mistral |   \n"
            "  |.66.14 | | Groq    |   \n"
            "  |(read  | | Gemini  |   \n"
            "  | only) | | Ollama  |   \n"
            "  +-------+ +---------+   \n",
            language="text"
        )
        st.write("**Componentes de infraestructura:**")
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Local:**")
            st.write("- Python 3.14 + dependencias")
            st.write("- SQLite (indice_procedimientos.db, 27 tablas)")
            st.write("- ChromaDB (chroma_db/)")
            st.write("- FAISS (faiss_index.bin)")
            st.write("- Cross-encoder (ms-marco-MiniLM-L-6-v2)")
            st.write("- Ollama (qwen2.5:7b local)")
            st.write("- Streamlit (puerto 8501, 9 paginas)")
            st.write("- FastAPI (puerto 8000)")
        with col2:
            st.write("**Red corporativa:**")
            st.write("- Gateway: 172.16.240.1")
            st.write("- DNS: 10.238.66.63")
            st.write("- SQL Server: 10.238.66.14")
            st.write("- Firewall: bloquea OpenAI")
            st.write("- Permite: Mistral, Groq, Gemini")
        st.write("**Almacenamiento:**")
        st.write("- indice_procedimientos.db: ~500 MB (SQLite, 27 tablas)")
        st.write("- chroma_db/: ~200 MB (ChromaDB)")
        st.write("- faiss_index.bin: ~50 MB (FAISS)")
        st.write("- cross-encoder model: ~120 MB (cache HuggingFace)")
        st.write("- Total: ~870 MB de datos indexados + modelos")

# ──────────────────────────────────────────────
# Tab: Seguridad
# ──────────────────────────────────────────────

with tab_seg:
    st.markdown("""
    <div class="main-header">
        <h1>Seguridad y Gobernanza del Agente</h1>
        <p>Guardrails, moderation, PII, prompt injection, rate limiting y auditoria</p>
    </div>
    """, unsafe_allow_html=True)

    # Estado general de seguridad
    st.subheader("Estado general")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if rag.governance:
            st.metric("Governance", "Activo")
        else:
            st.metric("Governance", "Inactivo")
    with col2:
        if rag.moderation:
            st.metric("Moderation", "Activo")
        else:
            st.metric("Moderation", "Inactivo")
    with col3:
        if rag.memoria:
            st.metric("Cache", "Activo")
        else:
            st.metric("Cache", "Inactivo")
    with col4:
        st.metric("Proveedores LLM", "5")

    st.divider()

    # Governance AI
    st.subheader("Governance AI (guardrails)")
    st.write("""
    El agente aplica guardrails en **entrada y salida** de cada consulta:
    """)
    gov_features = [
        ("Prompt injection", "30+ patrones de deteccion de inyeccion de prompts"),
        ("PII filter", "11 tipos de PII (email, telefono, cedula, tarjeta, etc.)"),
        ("Suspicious encoding", "Deteccion de codificaciones sospechosas (base64, hex, unicode)"),
        ("Dangerous SQL", "Bloqueo de DROP, DELETE, UPDATE, INSERT, ALTER, etc."),
        ("Forbidden topics", "Filtrado de temas prohibidos por politica"),
        ("Rate limiting", "Limite de consultas por ventana de tiempo"),
        ("Input validation", "Validacion de longitud y contenido de entrada"),
        ("Output validation", "Validacion de respuestas antes de enviar al usuario"),
        ("Credential detection", "Deteccion de API keys, tokens, passwords en texto"),
        ("Audit logging", "Registro completo en tabla auditoria de SQLite"),
    ]
    st.table([{"Control": g[0], "Descripcion": g[1]} for g in gov_features])

    st.divider()

    # Content Moderation
    st.subheader("Content Moderation")
    st.write("""
    Moderacion de contenido en **entrada y salida** del agente:
    """)
    mod_features = [
        ("Toxicidad", "Deteccion de lenguaje toxico o agresivo"),
        ("Hate speech", "Deteccion de discurso de odio"),
        ("Acoso", "Deteccion de contenido de acoso"),
        ("Autolesion", "Deteccion de contenido de autolesion"),
        ("Contenido sexual", "Deteccion de contenido sexual explicito"),
        ("Spam", "Deteccion de spam o contenido repetitivo"),
    ]
    st.table([{"Control": m[0], "Descripcion": m[1]} for m in mod_features])

    st.divider()

    # Configuracion de proveedores LLM
    st.subheader("Proveedores LLM (fallback)")
    st.write("""
    Orden de fallback cuando un proveedor falla (ej: rate limit 429):
    """)
    st.code(
        "  1. OpenAI    (bloqueado por firewall corporativo)\n"
        "  2. Mistral   (proveedor principal)\n"
        "  3. Ollama    (local, sin internet)\n"
        "  4. Groq      (alternativa cloud)\n"
        "  5. Gemini    (alternativa cloud)\n",
        language="text",
    )

    st.divider()

    # Reglas del agente
    st.subheader("Reglas del agente")
    reglas = [
        "Fuente primaria: SQL Server de Integr@ (no SharePoint, no Excel sueltos)",
        "Exclusion de obsoletos: estado O se excluye automaticamente",
        "Solo documentos vigentes: estado P (Publicado) por defecto",
        "Respuestas en espanol con citas al codigo del documento",
        "Skills dinamicos: se cargan solo cuando son relevantes (ahorro de tokens)",
        "Glosario automatico: se incluye en el contexto cuando hay terminos relevantes",
        "Resumenes enriquecidos: se incluyen en el contexto de cada documento",
        "Grafo persistente: se carga desde SQLite, no se reconstruye cada vez",
        "Solo operaciones SQL de lectura (SELECT) permitidas",
    ]
    for r in reglas:
        st.write(f"- {r}")

    st.divider()

    # Auditoria
    st.subheader("Registro de auditoria")
    st.write("Ultimos eventos de auditoria registrados en SQLite:")
    try:
        audit_rows = rag.conn.execute("""
            SELECT timestamp, question, rejected, rejection_reason, model
            FROM auditoria
            ORDER BY id DESC
            LIMIT 20
        """).fetchall()
        if audit_rows:
            st.table([
                {"Timestamp": r[0][:19] if r[0] else "", "Pregunta": (r[1] or "")[:60], "Rechazado": "Si" if r[2] else "No", "Razon": r[3] or "", "Modelo": r[4] or ""}
                for r in audit_rows
            ])
        else:
            st.info("No hay eventos de auditoria registrados aun.")
    except Exception as e:
        st.info(f"Tabla de auditoria no disponible: {e}")

    st.divider()

    # Moderation log
    st.subheader("Registro de moderacion")
    st.write("Ultimos eventos de moderacion de contenido:")
    try:
        mod_rows = rag.conn.execute("""
            SELECT timestamp, category, severity, action, matched_terms
            FROM moderation_log
            ORDER BY id DESC
            LIMIT 20
        """).fetchall()
        if mod_rows:
            st.table([
                {"Timestamp": r[0][:19] if r[0] else "", "Categoria": r[1] or "", "Severidad": r[2] or "", "Accion": r[3] or "", "Terminos": (r[4] or "")[:80]}
                for r in mod_rows
            ])
        else:
            st.info("No hay eventos de moderacion registrados aun.")
    except Exception as e:
        st.info(f"Tabla de moderacion no disponible: {e}")

    st.divider()

    # Rate limits
    st.subheader("Rate limiting")
    st.write("Contadores de rate limiting activos:")
    try:
        rl_rows = rag.conn.execute("""
            SELECT user_id, window_start, count
            FROM rate_limits
            ORDER BY window_start DESC
            LIMIT 20
        """).fetchall()
        if rl_rows:
            st.table([
                {"Usuario": r[0] or "", "Inicio ventana": (r[1] or "")[:19], "Contador": r[2] or 0}
                for r in rl_rows
            ])
        else:
            st.info("No hay contadores de rate limiting activos.")
    except Exception as e:
        st.info(f"Tabla de rate limits no disponible: {e}")
