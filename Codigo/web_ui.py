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

# Cargar .env si existe (para INTEGRA_DB_SERVER, API keys, etc.)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

import streamlit as st
import streamlit.components.v1 as components

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
    import sys
    print("\n" + "="*60, file=sys.stderr, flush=True)
    print("[RELOAD] Inicializando GraphRAG desde SQLite...", file=sys.stderr, flush=True)
    rag = GraphRAG()
    try:
        total_docs = rag.conn.execute("SELECT COUNT(*) FROM procedimientos").fetchone()[0]
        total_emb = rag.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        total_res = rag.conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
        total_nodos = rag.conn.execute("SELECT COUNT(*) FROM grafo_nodos").fetchone()[0]
        print(f"[RELOAD] Agente cargado: {total_docs} docs, {total_emb} embeddings, {total_res} resumenes, {total_nodos} nodos", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[RELOAD] Agente cargado (stats no disponibles: {e})", file=sys.stderr, flush=True)
    print("="*60 + "\n", file=sys.stderr, flush=True)
    return rag

with st.spinner("Cargando Agente Graph RAG..."):
    rag = load_rag()

# ──────────────────────────────────────────────
# Autenticacion de usuarios
# ──────────────────────────────────────────────
from auth import AuthManager
auth = AuthManager()

if "auth_token" not in st.session_state:
    st.session_state.auth_token = None
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
if "last_activity" not in st.session_state:
    st.session_state.last_activity = time.time()

# Verificar session timeout (30 min de inactividad)
if st.session_state.auth_token:
    if not auth.check_session_timeout(st.session_state.auth_token, st.session_state.last_activity):
        st.session_state.auth_token = None
        st.session_state.auth_user = None
        st.toast("Sesion cerrada por inactividad (30 min)")
    else:
        st.session_state.last_activity = time.time()

# Verificar sesion existente
if st.session_state.auth_token:
    user = auth.verify_session(st.session_state.auth_token)
    if not user:
        st.session_state.auth_token = None
        st.session_state.auth_user = None
    else:
        st.session_state.auth_user = user

# Mostrar login si no autenticado
if not st.session_state.auth_user:
    st.markdown("""
    <div class="main-header">
        <h1>Agente de Calidad Integr@ - Solistica</h1>
        <p>Inicia sesion para acceder al agente</p>
    </div>
    """, unsafe_allow_html=True)

    col_login, col_info = st.columns([2, 3])
    with col_login:
        with st.form("login_form"):
            st.subheader("Iniciar sesion")
            username = st.text_input("Usuario", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            submit = st.form_submit_button("Entrar")
            if submit:
                result = auth.login(username, password)
                if result["ok"]:
                    st.session_state.auth_token = result["token"]
                    st.session_state.auth_user = result["user"]
                    st.success(f"Bienvenido, {result['user']['nombre'] or result['user']['username']}!")
                    st.rerun()
                else:
                    st.error(f"Error: {result['mensaje']}")
        st.caption("Usuario por defecto: admin | Password: admin123 (cambiar despues)")
    with col_info:
        st.info("""
        **Agente de Calidad Integr@**

        Agente conversacional en español para consultas de calidad HSEQ sobre la plataforma Integr@.

        Funcionalidades:
        - Graph RAG Hibrido (BM25 + FAISS + Grafo + Cross-encoder)
        - Governance AI (guardrails, PII, moderation)
        - Sincronizacion con Integr@ (SQL Server)
        - Audit trail completo
        - Multi-usuario con roles
        """)

    st.stop()

# ──────────────────────────────────────────────
# Header comun (aparece en todas las paginas)
# ──────────────────────────────────────────────

# Logo + branding + user info
col_logo, col_brand, col_user = st.columns([1, 4, 2])

with col_logo:
    if _LOGO_PATH.exists():
        try:
            with open(_LOGO_PATH, "rb") as f:
                logo_bytes = f.read()
            st.image(logo_bytes, width=100)
        except Exception:
            st.markdown("### Agente de Calidad")
    else:
        st.markdown("### Agente de Calidad")

with col_brand:
    st.markdown("""
    <div style="padding-top: 10px;">
        <h2 style="color: #0066B1; margin: 0; font-weight: 700;">Solistica - Integr@</h2>
        <p style="color: #666; margin: 5px 0 0 0; font-size: 14px;">Agente Graph RAG Hibrido + Governance AI</p>
    </div>
    """, unsafe_allow_html=True)

# Info de usuario en el header
with col_user:
    user = st.session_state.auth_user
    if user:
        st.markdown(f"""
        <div style="padding-top: 10px; text-align: right;">
            <p style="color: #0066B1; margin: 0; font-weight: 600;">{user.get('nombre') or user.get('username', '')}</p>
            <p style="color: #666; margin: 5px 0 0 0; font-size: 12px;">Rol: {user.get('rol', 'usuario')}</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Cerrar sesion", key="logout_btn"):
            auth.logout(st.session_state.auth_token)
            st.session_state.auth_token = None
            st.session_state.auth_user = None
            st.rerun()

# ─── Metricas en tarjetas visuales ───
stats = rag.grafo_stats()
try:
    alertas = rag.alertas_vencimiento(solo_vencidos=False) if hasattr(rag, "alertas_vencimiento") else []
    n_vencidos = sum(1 for a in alertas if a.get("estado_alerta") == "VENCIDO")
    n_por_vencer = sum(1 for a in alertas if a.get("estado_alerta") == "POR_VENCER")
except Exception:
    n_vencidos = 0
    n_por_vencer = 0

# Glosario: contar terminos reales
try:
    n_glosario = rag.conn.execute("SELECT COUNT(*) FROM glosario").fetchone()[0]
except Exception:
    n_glosario = 118

# Tarjetas con CSS personalizado
st.markdown("""
<style>
.metric-card {
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    border-radius: 10px;
    padding: 15px;
    text-align: center;
    border-left: 4px solid #0066B1;
    margin-bottom: 10px;
}
.metric-card-alert {
    background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
    border-radius: 10px;
    padding: 15px;
    text-align: center;
    border-left: 4px solid #f39c12;
    margin-bottom: 10px;
}
.metric-card-danger {
    background: linear-gradient(135deg, #f8d7da 0%, #fab1a0 100%);
    border-radius: 10px;
    padding: 15px;
    text-align: center;
    border-left: 4px solid #e74c3c;
    margin-bottom: 10px;
}
.metric-value {
    font-size: 28px;
    font-weight: 700;
    color: #0066B1;
    margin: 0;
}
.metric-value-alert {
    font-size: 28px;
    font-weight: 700;
    color: #f39c12;
    margin: 0;
}
.metric-value-danger {
    font-size: 28px;
    font-weight: 700;
    color: #e74c3c;
    margin: 0;
}
.metric-label {
    font-size: 12px;
    color: #666;
    margin: 5px 0 0 0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
</style>
""", unsafe_allow_html=True)

# 6 tarjetas en 2 filas de 3
col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
    st.markdown(f"""
    <div class="metric-card">
        <p class="metric-value">{len(rag.docs):,}</p>
        <p class="metric-label">Documentos</p>
    </div>
    """, unsafe_allow_html=True)
with col_m2:
    st.markdown(f"""
    <div class="metric-card">
        <p class="metric-value">{stats.get('nodos', 0):,}</p>
        <p class="metric-label">Nodos del Grafo</p>
    </div>
    """, unsafe_allow_html=True)
with col_m3:
    st.markdown(f"""
    <div class="metric-card">
        <p class="metric-value">{stats.get('aristas', 0):,}</p>
        <p class="metric-label">Aristas del Grafo</p>
    </div>
    """, unsafe_allow_html=True)

col_m4, col_m5, col_m6 = st.columns(3)
with col_m4:
    st.markdown(f"""
    <div class="metric-card">
        <p class="metric-value">{n_glosario}</p>
        <p class="metric-label">Terminos del Glosario</p>
    </div>
    """, unsafe_allow_html=True)
with col_m5:
    if n_vencidos > 0:
        st.markdown(f"""
        <div class="metric-card-danger">
            <p class="metric-value-danger">{n_vencidos}</p>
            <p class="metric-label">Documentos Vencidos</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value">{n_vencidos}</p>
            <p class="metric-label">Documentos Vencidos</p>
        </div>
        """, unsafe_allow_html=True)
with col_m6:
    if n_por_vencer > 0:
        st.markdown(f"""
        <div class="metric-card-alert">
            <p class="metric-value-alert">{n_por_vencer}</p>
            <p class="metric-label">Por Vencer (30 dias)</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="metric-card">
            <p class="metric-value">{n_por_vencer}</p>
            <p class="metric-label">Por Vencer (30 dias)</p>
        </div>
        """, unsafe_allow_html=True)

# Banner de alerta si hay documentos vencidos o por vencer
if n_vencidos > 0 or n_por_vencer > 0:
    alert_msg = []
    if n_vencidos > 0:
        alert_msg.append(f"**{n_vencidos} documentos VENCIDOS**")
    if n_por_vencer > 0:
        alert_msg.append(f"**{n_por_vencer} documentos por vencer** en 30 dias")
    st.warning("Atencion: " + " | ".join(alert_msg) + ". Ve al tab 'Vencidos' para mas detalles.")

st.divider()

# ──────────────────────────────────────────────
# Navegacion por tabs centrales
# ──────────────────────────────────────────────

# RBAC: permisos del usuario actual
_user_rol = st.session_state.auth_user.get("rol", "usuario") if st.session_state.auth_user else "usuario"
_user_perms = auth.get_permissions(_user_rol)

def can_access(permiso: str) -> bool:
    """Verifica si el usuario actual tiene permiso para acceder a un tab."""
    return permiso in _user_perms

tab_chat, tab_est, tab_jer, tab_venc, tab_glos, tab_finops, tab_docs, tab_comp, tab_arq, tab_seg, tab_sync, tab_salud, tab_audit, tab_nc, tab_gestion, tab_bilingue = st.tabs([
    "Chat", "Estadisticas", "Jerarquia", "Vencidos", "Glosario",
    "FinOps", "Documentos", "Comparador", "Arquitectura", "Seguridad", "Sincronizacion", "Salud del Sistema", "Auditoria", "No Conformidades", "Gestion Calidad", "Diccionario Bilingue",
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
    if "session_id" not in st.session_state:
        import uuid
        st.session_state.session_id = str(uuid.uuid4())[:8]
    if "chat_auto_loaded" not in st.session_state:
        st.session_state.chat_auto_loaded = False

    # ─── Auto-cargar ultima sesion al recargar ───
    if not st.session_state.chat_auto_loaded and not st.session_state.messages:
        if hasattr(rag, "listar_sesiones_chat"):
            sesiones = rag.listar_sesiones_chat(limit=1)
            if sesiones:
                ultima = sesiones[0]
                historial = rag.cargar_historial_chat(ultima["session_id"])
                if historial:
                    st.session_state.messages = [
                        {"role": m["role"], "content": m["content"],
                         "documentos": m.get("documentos", [])}
                        for m in historial
                    ]
                    st.session_state.session_id = ultima["session_id"]
                    st.toast(f"Sesion anterior cargada: {ultima['primera_pregunta'][:50]}...")
        st.session_state.chat_auto_loaded = True

    # ─── Cargar sesion previa (selector manual) ───
    sesiones_previas = rag.listar_sesiones_chat() if hasattr(rag, "listar_sesiones_chat") else []
    if sesiones_previas and len(sesiones_previas) > 1:
        with st.expander(f"Sesiones anteriores ({len(sesiones_previas)})"):
            for s in sesiones_previas[:10]:
                col1, col2, col3, col4 = st.columns([5, 2, 1, 1])
                with col1:
                    st.write(f"**{s['primera_pregunta'] or 'Sin pregunta'}**")
                    st.caption(f"ID: {s['session_id']} | {s['msg_count']} mensajes")
                with col2:
                    st.caption(f"Ultima: {s['ultima']}")
                with col3:
                    if st.button("Cargar", key=f"load_{s['session_id']}"):
                        historial = rag.cargar_historial_chat(s["session_id"])
                        st.session_state.messages = [
                            {"role": m["role"], "content": m["content"],
                             "documentos": m.get("documentos", [])}
                            for m in historial
                        ]
                        st.session_state.session_id = s["session_id"]
                        st.session_state.feedback_given = {}
                        st.rerun()
                with col4:
                    if st.button("Eliminar", key=f"del_{s['session_id']}"):
                        rag.eliminar_sesion_chat(s["session_id"])
                        st.rerun()

    # Boton nueva conversacion
    col_new, col_export = st.columns([6, 1])
    with col_new:
        if st.button("Nueva conversacion") and st.session_state.messages:
            st.session_state.messages = []
            import uuid
            st.session_state.session_id = str(uuid.uuid4())[:8]
            st.session_state.feedback_given = {}
            st.rerun()
    with col_export:
        if st.session_state.messages:
            export_format = st.selectbox("Exportar", ["Markdown", "Texto plano", "JSON"], key="export_fmt")
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
                elif export_format == "JSON":
                    import json as _json
                    export_content = _json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)
                    st.download_button(
                        label="Descargar .json",
                        data=export_content.encode("utf-8"),
                        file_name=f"conversacion_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        mime="application/json",
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

    # ─── Importar conversacion ───
    with st.expander("Importar conversacion"):
        uploaded = st.file_uploader("Subir archivo .json de conversacion", type=["json"], key="import_chat")
        if uploaded is not None:
            try:
                import json as _json
                imported = _json.loads(uploaded.read().decode("utf-8"))
                if isinstance(imported, list) and all("role" in m and "content" in m for m in imported):
                    st.session_state.messages = [
                        {"role": m["role"], "content": m["content"], "documentos": m.get("documentos", [])}
                        for m in imported
                    ]
                    st.session_state.feedback_given = {}
                    st.success(f"Conversacion importada: {len(imported)} mensajes")
                    st.rerun()
                else:
                    st.error("Formato invalido. El archivo debe ser una lista de mensajes con 'role' y 'content'.")
            except Exception as e:
                st.error(f"Error importando: {e}")

    # ─── Sugerencias proactivas por rol ───
    try:
        if hasattr(rag, "proactivity") and rag.proactivity:
            sugerencias = rag.proactivity.get_suggestions(
                user_id=st.session_state.auth_user.get("username", "default") if st.session_state.auth_user else "default",
                role=_user_rol,
            )
            if sugerencias:
                with st.expander(f"Sugerencias para ti ({_user_rol})", expanded=True):
                    for s in sugerencias:
                        prioridad_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.get("priority", "low"), "🔵")
                        st.info(f"{prioridad_color} **{s.get('message', '')}**\n\n{s.get('action', '')}")
    except Exception as e:
        st.caption(f"Sugerencias no disponibles: {e}")

    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            # Citation linking: enriquecer respuesta con citas clickeables
            content_display = msg["content"]
            if msg["role"] == "assistant" and msg.get("documentos"):
                content_display = rag.enriquecer_citas(msg["content"], msg["documentos"]) if hasattr(rag, "enriquecer_citas") else msg["content"]
            st.markdown(content_display)

            # Badge de confidence y hallucination
            if msg["role"] == "assistant" and msg.get("confidence"):
                conf = msg["confidence"]
                conf_emoji = {"alto": "🟢", "medio": "🟡", "bajo": "🔴"}.get(conf.get("nivel", ""), "⚪")
                st.caption(f"{conf_emoji} Confianza: {conf.get('nivel', 'N/A')} (score: {conf.get('score', 0):.2f})")

            if msg.get("documentos"):
                with st.expander(f"Documentos consultados ({len(msg['documentos'])})"):
                    for doc in msg["documentos"]:
                        icon = estado_icon(doc.get("estado", ""))
                        # Citation linking: codigo clickeable que abre preview
                        doc_codigo = doc.get("codigo", "")
                        st.write(f"{icon} **{doc['codigo']}** - {doc['nombre']}")
                        st.caption(f"Proceso: {doc.get('proceso', 'N/A')} | Estado: {doc.get('estado', 'N/A')} | Score: {doc.get('score', 0):.3f}")
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
                                resultados=msg.get("resultados"),
                                fuente=msg.get("provider", "chat"),
                            )
                            st.session_state.feedback_given[fb_key] = "positive"
                            st.rerun()
                    with col_neg:
                        if st.button("No util", key=f"neg_{idx}"):
                            rag.guardar_feedback(
                                pregunta=st.session_state.messages[idx-1]["content"] if idx > 0 else "",
                                respuesta=msg["content"],
                                feedback="negative",
                                resultados=msg.get("resultados"),
                                fuente=msg.get("provider", "chat"),
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
            if st.button(ej[:45], key=f"ej_{i}_{hash(ej) % 10000}", help=ej, width="stretch"):
                st.session_state.pending_question = ej
                st.rerun()

    st.divider()

    # Toggle de modo rapido para reducir latencia
    if "modo_rapido" not in st.session_state:
        st.session_state.modo_rapido = True
    col_modo, _ = st.columns([1, 3])
    with col_modo:
        st.session_state.modo_rapido = st.toggle(
            "Modo rapido",
            value=st.session_state.modo_rapido,
            help="Desactiva HyDE, multi-query y RAPTOR para preguntas simples. Mas rapido pero menos profundo."
        )

    # Input
    if "pending_question" in st.session_state:
        prompt = st.session_state.pending_question
        del st.session_state.pending_question
    else:
        prompt = st.chat_input("Escribe tu pregunta...")

    if prompt:
        # ─── Deteccion de anomalias (anti-abuso) ───
        _user = st.session_state.auth_user or {"id": 0, "username": "anon"}
        anomalia = auth.detectar_anomalia(_user.get("id", 0), _user.get("username", "anon"))
        if anomalia.get("anomalia"):
            st.warning(f"Anomalia detectada: {anomalia['descripcion']}. Se notificara al administrador.")

        # Guardar pregunta en historial persistente
        session_id = st.session_state.get("session_id", "default")
        rag.guardar_mensaje_chat(session_id, "user", prompt) if hasattr(rag, "guardar_mensaje_chat") else None

        # Mostrar pregunta
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generar respuesta con streaming
        with st.chat_message("assistant"):
            # Establecer contexto de usuario para tracking
            rag._current_username = _user.get("username", "anon")
            rag._current_role = _user_rol
            rag._current_area = _user.get("area", "")
            rag._current_session_id = session_id

            t_start = time.time()
            try:
                # Streaming: mostrar tokens en vivo
                stream = rag.ask_stream(prompt, modo_rapido=st.session_state.modo_rapido)
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

                # ─── Evaluacion automatica (RAGAS-like) ───
                eval_result = None
                if resultados and hasattr(rag, "evaluar_respuesta"):
                    eval_result = rag.evaluar_respuesta(prompt, full_answer, resultados)

                # ─── Confidence score ───
                confidence = rag._calculate_confidence(resultados) if hasattr(rag, "_calculate_confidence") else None

                # ─── Hallucination detection ───
                hallucination = None
                if resultados and hasattr(rag, "_detect_hallucination"):
                    hallucination = rag._detect_hallucination(full_answer, resultados)

                # Citation linking en la respuesta mostrada
                answer_display = full_answer
                if docs and hasattr(rag, "enriquecer_citas"):
                    answer_display = rag.enriquecer_citas(full_answer, docs)
                st.markdown(answer_display)

                # Badges de confianza y evaluacion
                badge_parts = [f"Tiempo: {t_elapsed:.1f}s", f"Documentos: {len(resultados)}", f"LLM: {provider_used}"]
                if confidence:
                    conf_emoji = {"alto": "🟢", "medio": "🟡", "bajo": "🔴"}.get(confidence.get("nivel", ""), "⚪")
                    badge_parts.append(f"{conf_emoji} Confianza: {confidence['nivel']}")
                if eval_result:
                    badge_parts.append(f"Eval: {eval_result['evaluacion']} ({eval_result['score_total']:.2f})")
                if hallucination and hallucination.get("hallucination"):
                    badge_parts.append("⚠️ Hallucination detectada")
                st.caption(" | ".join(badge_parts))

                # ─── Feedback: thumbs up/down para la respuesta actual ───
                fb_key_new = f"fb_{len(st.session_state.messages)}"
                if fb_key_new not in st.session_state.feedback_given:
                    col_pos, col_neg = st.columns([1, 1])
                    with col_pos:
                        if st.button("Util", key=f"pos_{fb_key_new}"):
                            rag.guardar_feedback(
                                pregunta=prompt,
                                respuesta=full_answer,
                                feedback="positive",
                                resultados=resultados,
                                fuente=provider_used,
                            )
                            st.session_state.feedback_given[fb_key_new] = "positive"
                            st.rerun()
                    with col_neg:
                        if st.button("No util", key=f"neg_{fb_key_new}"):
                            rag.guardar_feedback(
                                pregunta=prompt,
                                respuesta=full_answer,
                                feedback="negative",
                                resultados=resultados,
                                fuente=provider_used,
                            )
                            st.session_state.feedback_given[fb_key_new] = "negative"
                            st.rerun()
                else:
                    fb_val = st.session_state.feedback_given[fb_key_new]
                    if fb_val == "positive":
                        st.caption("Gracias por tu feedback: Util")
                    else:
                        st.caption("Gracias por tu feedback: No util")

                # ─── Watermarking de respuesta (trazabilidad) ───
                _user = st.session_state.auth_user or {"id": 0, "username": "anon"}
                full_answer_watermarked = auth.watermark_response(
                    full_answer, _user.get("id", 0), _user.get("username", "anon")
                ) if hasattr(auth, "watermark_response") else full_answer

                # ─── Guardar respuesta en historial persistente ───
                if hasattr(rag, "guardar_mensaje_chat"):
                    rag.guardar_mensaje_chat(
                        session_id, "assistant", full_answer_watermarked,
                        documentos=docs, provider=provider_used,
                        confidence=confidence, hallucination=hallucination,
                    )

                # ─── Audit trail completo ───
                if hasattr(rag, "log_audit"):
                    rag.log_audit(
                        session_id=session_id,
                        pregunta=prompt, respuesta=full_answer_watermarked,
                        documentos=resultados, provider=provider_used,
                        confidence=confidence, hallucination=hallucination,
                        total_time=t_elapsed,
                    )

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_answer,
                    "documentos": docs,
                    "resultados": resultados,
                    "provider": provider_used,
                    "confidence": confidence,
                    "evaluacion": eval_result,
                    "hallucination": hallucination,
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

    # ─── Observabilidad Avanzada (modulo observabilidad_avanzada.py) ───
    st.divider()
    st.subheader("Observabilidad Avanzada")
    st.caption("OpenTelemetry + Sentry + Latency percentiles + Cost alerts + Quality dashboards")

    try:
        from observabilidad_avanzada import (
            get_latency_percentiles, get_cost_summary,
            get_quality_dashboard, check_cost_alerts,
            get_latency_by_operation,
        )

        col_ot, col_sentry = st.columns(2)
        with col_ot:
            try:
                from observabilidad_avanzada import _HAS_OTEL
                st.metric("OpenTelemetry", "Activo" if _HAS_OTEL else "Fallback local")
            except Exception:
                st.metric("OpenTelemetry", "Fallback local")
        with col_sentry:
            try:
                from observabilidad_avanzada import _HAS_SENTRY
                st.metric("Sentry", "Activo" if _HAS_SENTRY else "No instalado")
            except Exception:
                st.metric("Sentry", "No instalado")

        # Latency percentiles P50/P95/P99
        st.write("**Latency percentiles (P50/P95/P99)**")
        try:
            # Obtener operaciones disponibles
            lat_by_op = get_latency_by_operation(rag.conn, hours=24)
            if lat_by_op and any(v for v in lat_by_op.values()):
                # Para cada operacion, calcular percentiles
                pct_data = []
                for op_name in lat_by_op.keys():
                    pct = get_latency_percentiles(rag.conn, operation=op_name, hours=24)
                    if pct and pct.get("count", 0) > 0:
                        pct_data.append({
                            "Operacion": op_name,
                            "P50 (ms)": round(pct["p50"], 1) if pct["p50"] else 0,
                            "P95 (ms)": round(pct["p95"], 1) if pct["p95"] else 0,
                            "P99 (ms)": round(pct["p99"], 1) if pct["p99"] else 0,
                            "Count": pct["count"],
                        })
                if pct_data:
                    st.table(pct_data)
                    st.bar_chart(
                        [{"Operacion": d["Operacion"],
                          "P50": d["P50 (ms)"], "P95": d["P95 (ms)"], "P99": d["P99 (ms)"]}
                         for d in pct_data],
                        x="Operacion",
                    )
                else:
                    st.info("Aun no hay datos de latency suficientes para percentiles.")
            else:
                st.info("Aun no hay datos de latency. Haz preguntas al agente para generar mediciones.")
        except Exception as e:
            st.warning(f"Latency percentiles no disponibles: {e}")

        # Cost summary y alerts
        st.write("**Cost summary y alerts**")
        try:
            cost_data = get_cost_summary(rag.conn)
            if cost_data and cost_data.get("total_cost", 0) > 0:
                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    st.metric("Costo total", f"${cost_data['total_cost']:.4f}")
                with col_c2:
                    st.metric("Costo hoy", f"${cost_data.get('today_cost', 0):.4f}")
                with col_c3:
                    st.metric("Promedio diario", f"${cost_data.get('avg_daily', 0):.4f}")

                # Cost alerts
                alerts = check_cost_alerts(rag.conn)
                if alerts:
                    for alert in alerts:
                        st.error(f"ALERTA: {alert}")
                else:
                    st.success("Sin alertas de costo")

                # Costo por modelo
                if cost_data.get("by_model"):
                    st.write("**Costo por modelo:**")
                    st.table([
                        {"Modelo": m["model"], "Costo": f"${m['cost']:.4f}",
                         "Queries": m["queries"], "Avg cost": f"${m['avg_cost']:.6f}"}
                        for m in cost_data["by_model"]
                    ])
            else:
                st.info("Aun no hay datos de costo. Haz preguntas al agente para generar trazas.")
        except Exception as e:
            st.warning(f"Cost summary no disponible: {e}")

        # Quality dashboard (7 metricas)
        st.write("**Quality Dashboard (7 metricas)**")
        try:
            # Leer directamente de tablas existentes
            q_data = []

            # 1. Calidad respuesta (de evaluaciones si existe)
            try:
                eval_avg = rag.conn.execute(
                    "SELECT AVG(score_total) FROM evaluaciones"
                ).fetchone()[0]
                q_data.append({"Metrica": "Calidad respuesta", "Valor": str(round(eval_avg, 2)) if eval_avg else "N/A"})
            except Exception:
                q_data.append({"Metrica": "Calidad respuesta", "Valor": "N/A"})

            # 2. Latencia promedio (de finops_traces)
            try:
                lat_avg = rag.conn.execute(
                    "SELECT AVG(latencia_total) FROM finops_traces"
                ).fetchone()[0]
                q_data.append({"Metrica": "Latencia promedio (s)", "Valor": str(round(lat_avg, 2)) if lat_avg else "N/A"})
            except Exception:
                q_data.append({"Metrica": "Latencia promedio (s)", "Valor": "N/A"})

            # 3. Costo total (de finops_traces)
            try:
                cost_total = rag.conn.execute(
                    "SELECT SUM(costo_usd) FROM finops_traces"
                ).fetchone()[0]
                q_data.append({"Metrica": "Costo total (USD)", "Valor": str(round(cost_total, 4)) if cost_total else "0"})
            except Exception:
                q_data.append({"Metrica": "Costo total (USD)", "Valor": "0"})

            # 4. Errores (de auditoria, preguntas rechazadas)
            try:
                errors = rag.conn.execute(
                    "SELECT COUNT(*) FROM auditoria WHERE rejected = 1"
                ).fetchone()[0]
                q_data.append({"Metrica": "Preguntas bloqueadas", "Valor": str(errors or 0)})
            except Exception:
                q_data.append({"Metrica": "Preguntas bloqueadas", "Valor": "0"})

            # 5. Hallucinations (de auditoria)
            try:
                hall = rag.conn.execute(
                    "SELECT COUNT(*) FROM auditoria WHERE hallucination_score < 1"
                ).fetchone()[0]
                q_data.append({"Metrica": "Hallucinations", "Valor": str(hall or 0)})
            except Exception:
                q_data.append({"Metrica": "Hallucinations", "Valor": "0"})

            # 6. DLP detecciones (de bias_checks si existe, sino 0)
            try:
                dlp = rag.conn.execute(
                    "SELECT COUNT(*) FROM bias_checks WHERE has_bias = 1"
                ).fetchone()[0]
                q_data.append({"Metrica": "Respuestas con bias", "Valor": str(dlp or 0)})
            except Exception:
                q_data.append({"Metrica": "Respuestas con bias", "Valor": "0"})

            # 7. Feedback negativo (de feedback_usuario)
            try:
                fb_neg = rag.conn.execute(
                    "SELECT COUNT(*) FROM feedback_usuario WHERE feedback = 'negative'"
                ).fetchone()[0]
                q_data.append({"Metrica": "Feedback negativo", "Valor": str(fb_neg or 0)})
            except Exception:
                q_data.append({"Metrica": "Feedback negativo", "Valor": "0"})

            st.table(q_data)
        except Exception as e:
            st.warning(f"Quality dashboard no disponible: {e}")

        # ─── Calidad RAG (recall@k, precision, MRR + RAGAS) ───
        st.write("**Calidad RAG**")
        try:
            # Promedios RAGAS
            ragas_avg = rag.conn.execute("""
                SELECT
                    AVG(faithfulness),
                    AVG(answer_relevancy),
                    AVG(context_precision),
                    AVG(context_recall)
                FROM ragas_metrics
            """).fetchone()

            if ragas_avg and any(v is not None for v in ragas_avg):
                st.table([
                    {"Metrica": "Faithfulness", "Valor": f"{ragas_avg[0]:.2f}" if ragas_avg[0] else "N/A"},
                    {"Metrica": "Answer Relevancy", "Valor": f"{ragas_avg[1]:.2f}" if ragas_avg[1] else "N/A"},
                    {"Metrica": "Context Precision", "Valor": f"{ragas_avg[2]:.2f}" if ragas_avg[2] else "N/A"},
                    {"Metrica": "Context Recall", "Valor": f"{ragas_avg[3]:.2f}" if ragas_avg[3] else "N/A"},
                ])
            else:
                st.info("Aun no hay metricas RAGAS. Haz preguntas al agente para generar evaluaciones.")

            # Boton para ejecutar evaluacion con golden questions
            if st.button("Ejecutar evaluacion RAG con golden questions", key="eval_rag_btn"):
                with st.spinner("Evaluando retrieval con 5 preguntas de prueba..."):
                    try:
                        preguntas = [
                            {"pregunta": "¿cuál es el procedimiento de control de temperatura en cuartos fríos?", "esperados": ["WH"]},
                            {"pregunta": "¿cómo se gestiona una no conformidad?", "esperados": ["GC"]},
                            {"pregunta": "¿qué procedimientos existen para recepción de mercancía?", "esperados": ["WH"]},
                            {"pregunta": "¿cómo se realiza el despacho de productos?", "esperados": ["WH"]},
                            {"pregunta": "¿qué procedimientos hay de seguridad y salud en el trabajo?", "esperados": ["ST", "SR"]},
                        ]
                        resultados = []
                        for pq in preguntas:
                            try:
                                resultados_raw = rag.retrieve(pq["pregunta"], top_k=5, use_reranking=False)
                                procesos_recuperados = set()
                                for r in resultados_raw:
                                    proc = (r.get("proceso") or "").upper()
                                    if proc:
                                        procesos_recuperados.add(proc)
                                esperados = pq["esperados"]
                                relevantes = sum(1 for p in procesos_recuperados if any(e in p for e in esperados))
                                precision = relevantes / len(procesos_recuperados) if procesos_recuperados else 0
                                recall = sum(1 for e in esperados if any(e in p for p in procesos_recuperados)) / len(esperados)
                                mrr = 0
                                for idx, r in enumerate(resultados_raw):
                                    proc = (r.get("proceso") or "").upper()
                                    if any(e in proc for e in esperados):
                                        mrr = 1 / (idx + 1)
                                        break
                                resultados.append({"precision": precision, "recall": recall, "mrr": mrr})
                            except Exception as e:
                                st.warning(f"Error evaluando '{pq['pregunta'][:40]}': {e}")

                        if resultados:
                            avg_p = sum(r["precision"] for r in resultados) / len(resultados)
                            avg_r = sum(r["recall"] for r in resultados) / len(resultados)
                            avg_m = sum(r["mrr"] for r in resultados) / len(resultados)
                            st.success("Evaluacion completada")
                            st.table([
                                {"Metrica": "Precision@K", "Valor": f"{avg_p:.2f}"},
                                {"Metrica": "Recall@K", "Valor": f"{avg_r:.2f}"},
                                {"Metrica": "MRR", "Valor": f"{avg_m:.2f}"},
                                {"Metrica": "Preguntas evaluadas", "Valor": str(len(resultados))},
                            ])
                            rag.conn.execute("""
                                CREATE TABLE IF NOT EXISTS rag_eval_summary (
                                    fecha TEXT,
                                    recall REAL,
                                    precision REAL,
                                    mrr REAL,
                                    total INTEGER
                                )
                            """)
                            rag.conn.execute("""
                                INSERT INTO rag_eval_summary (fecha, recall, precision, mrr, total)
                                VALUES (?, ?, ?, ?, ?)
                            """, (datetime.now().isoformat(), avg_r, avg_p, avg_m, len(resultados)))
                            rag.conn.commit()
                    except Exception as e:
                        st.error(f"Error en evaluacion: {e}")

            # Mostrar ultima evaluacion guardada
            ult_eval = rag.conn.execute("""
                SELECT fecha, recall, precision, mrr, total
                FROM rag_eval_summary
                ORDER BY fecha DESC LIMIT 1
            """).fetchone()
            if ult_eval:
                st.caption(f"Ultima evaluacion: {ult_eval[0]} | Recall={ult_eval[1]:.2f} Precision={ult_eval[2]:.2f} MRR={ult_eval[3]:.2f} ({ult_eval[4]} preguntas)")

            # ─── Programacion automatica del pipeline de evaluacion ───
            with st.expander("Programar evaluacion automatica (golden questions + RAGAS)"):
                st.write("""
                Ejecuta `evaluar_rag.py` periodicamente para actualizar el dashboard de calidad.

                **Opcion 1 - Windows Task Scheduler:**
                1. Abre Task Scheduler
                2. Crear tarea basica -> Nombre: `EvalRAG`
                3. Desencadenador: Diariamente a las 3:00 AM
                4. Accion: Iniciar programa
                5. Programa: `python`
                6. Argumentos: `Codigo/evaluar_rag.py`
                7. Iniciar en: `C:\\Users\\1121871773\\OneDrive - agvco\\Documentos\\Agente Calidad Codigo`

                **Opcion 2 - PowerShell (como administrador):**
                """)
                st.code("""
$action = New-ScheduledTaskAction -Execute "python" -Argument "Codigo/evaluar_rag.py" `
    -WorkingDirectory "C:\\Users\\1121871773\\OneDrive - agvco\\Documentos\\Agente Calidad Codigo"
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
Register-ScheduledTask -TaskName "EvalRAG" -Action $action -Trigger $trigger -Settings $settings
                """.strip(), language="powershell")
                st.info("Requiere MISTRAL_API_KEY u OPENAI_API_KEY configurada en el entorno del sistema.")
        except Exception as e:
            st.warning(f"Calidad RAG no disponible: {e}")

        # ─── Indicadores de uso por usuario, area y proceso ───
        st.write("**Uso del agente**")
        try:
            uso = rag.get_usage_stats()
            if uso.get("total", 0) == 0:
                st.info("Aun no hay datos de uso. Haz preguntas al agente para generar estadisticas.")
            else:
                st.metric("Total consultas", uso["total"])
                c1, c2 = st.columns(2)
                with c1:
                    st.write("Por usuario")
                    st.table(uso["por_usuario"])
                with c2:
                    st.write("Por rol")
                    st.table(uso["por_rol"])
                st.write("Por proceso")
                st.table(uso["por_proceso"])
                if any(a["Consultas"] for a in uso["por_area"]):
                    st.write("Por area")
                    st.table(uso["por_area"])
        except Exception as e:
            st.warning(f"Indicadores de uso no disponibles: {e}")

        # Latency by operation (ultimas 24h)
        st.write("**Latency por operacion (ultimas 24h)**")
        try:
            lat_by_op = get_latency_by_operation(rag.conn, hours=24)
            if lat_by_op and any(v for v in lat_by_op.values()):
                st.table([
                    {"Operacion": k, "Latencia avg (ms)": round(v, 1) if v else 0}
                    for k, v in lat_by_op.items() if v
                ])
            else:
                st.info("Aun no hay datos de latency por operacion.")
        except Exception as e:
            st.warning(f"Latency by operation no disponible: {e}")

    except ImportError:
        st.warning("Modulo observabilidad_avanzada no disponible. Instala dependencias: pip install opentelemetry-api opentelemetry-sdk sentry-sdk")

    # ─── Human-in-the-Loop (mejoras_extras.py) ───
    st.divider()
    st.subheader("Human-in-the-Loop (feedback estructurado)")
    st.caption("Feedback tipado de usuarios + dataset de fine-tuning exportable")

    try:
        from mejoras_extras import get_feedback_stats, get_training_dataset, export_training_dataset
        hitl_stats = get_feedback_stats(rag.conn)
        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        with col_h1:
            st.metric("Total feedback", hitl_stats.get("total", 0))
        with col_h2:
            st.metric("Rating promedio", f"{hitl_stats.get('avg_rating', 0):.1f}/3")
        with col_h3:
            st.metric("Correcciones", hitl_stats.get("corrections_provided", 0))
        with col_h4:
            st.metric("Satisfaccion", f"{hitl_stats.get('satisfaction_rate', 0):.1%}")

        if hitl_stats.get("by_type"):
            st.write("**Feedback por tipo:**")
            st.table([
                {"Tipo": k, "Cantidad": v}
                for k, v in hitl_stats["by_type"].items()
            ])

        # Dataset de fine-tuning
        dataset = get_training_dataset(rag.conn)
        if dataset:
            st.write(f"**Dataset de fine-tuning:** {len(dataset)} pares aprobados")
            st.table([
                {"Pregunta": d.get("question", "")[:50],
                 "Respuesta original": d.get("answer", "")[:50],
                 "Respuesta corregida": d.get("corrected_answer", "")[:50],
                 "Rating": d.get("rating", ""),
                 "Tipo": d.get("feedback_type", "")}
                for d in dataset[:20]
            ])

            # Exportar dataset
            import tempfile
            if st.button("Exportar dataset (JSONL)"):
                try:
                    output_path = Path(tempfile.gettempdir()) / "finetune_dataset.jsonl"
                    result = export_training_dataset(rag.conn, output_path)
                    st.success(f"Dataset exportado: {result.get('total_exported', 0)} pares en {output_path}")
                except Exception as e:
                    st.error(f"Error exportando: {e}")
        else:
            st.info("Aun no hay dataset de fine-tuning. Los usuarios deben dar feedback con correcciones.")
    except ImportError:
        st.warning("Modulo mejoras_extras no disponible.")

    # ─── Tabla de Cambios (mejoras_extras.py) ───
    st.divider()
    st.subheader("Tabla de Cambios (change log de documentos)")
    st.caption("Historial de cambios de documentos: creacion, revision, aprobacion, publicacion, obsoleto")

    try:
        from mejoras_extras import get_change_log_stats, obtener_historial_cambios
        change_stats = get_change_log_stats(rag.conn)
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.metric("Total cambios", change_stats.get("total_cambios", 0))
        with col_c2:
            st.metric("Docs modificados", change_stats.get("documentos_modificados", 0))
        with col_c3:
            st.metric("Top autores", len(change_stats.get("top_autores", [])))

        if change_stats.get("by_type"):
            st.write("**Cambios por tipo:**")
            st.table([
                {"Tipo": k, "Cantidad": v}
                for k, v in change_stats["by_type"].items()
            ])

        if change_stats.get("top_autores"):
            st.write("**Top autores de cambios:**")
            st.table([
                {"Autor": a["autor"], "Cambios": a["cambios"]}
                for a in change_stats["top_autores"][:10]
            ])

        # Buscar historial por codigo
        st.write("**Buscar historial de un documento:**")
        doc_codigo = st.text_input("Codigo del documento:", key="change_log_codigo",
                                    placeholder="Ej: PGC-16-15")
        if doc_codigo:
            historial = obtener_historial_cambios(rag.conn, doc_codigo)
            if historial:
                st.success(f"{len(historial)} cambios encontrados para {doc_codigo}")
                st.table([
                    {"Fecha": h.get("timestamp", "")[:19],
                     "Tipo": h.get("tipo", ""),
                     "v Anterior": h.get("version_anterior", ""),
                     "v Nueva": h.get("version_nueva", ""),
                     "Autor": h.get("autor", ""),
                     "Descripcion": (h.get("descripcion") or "")[:80]}
                    for h in historial
                ])
            else:
                st.info(f"No hay cambios registrados para {doc_codigo}.")
    except ImportError:
        st.warning("Modulo mejoras_extras no disponible.")

with tab_docs:
    st.markdown("""
    <div class="main-header">
        <h1>Visor de Documentos</h1>
        <p>Consulta documentos completos con metadatos de Integr@</p>
    </div>
    """, unsafe_allow_html=True)

    # ─── Buscador global ───
    st.subheader("Busqueda global")
    busqueda = st.text_input(
        "Buscar por codigo, nombre, proceso o contenido:",
        placeholder="Ej: PGC-11, temperatura, almacenamiento, recepcion...",
        key="global_search"
    )

    # ─── Filtros avanzados ───
    with st.expander("Filtros avanzados", expanded=False):
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)

        # Obtener valores unicos para los filtros
        try:
            procesos_lista = rag.conn.execute(
                "SELECT DISTINCT proceso_nom FROM procedimientos WHERE proceso_nom IS NOT NULL ORDER BY proceso_nom"
            ).fetchall()
            procesos_opciones = ["Todos"] + [p[0] for p in procesos_lista]
        except Exception:
            procesos_opciones = ["Todos"]

        try:
            tipos_lista = rag.conn.execute(
                "SELECT DISTINCT tipo_documento FROM procedimientos WHERE tipo_documento IS NOT NULL ORDER BY tipo_documento"
            ).fetchall()
            tipos_opciones = ["Todos"] + [t[0] for t in tipos_lista]
        except Exception:
            tipos_opciones = ["Todos"]

        estados_opciones = ["Todos", "P", "E", "D", "R", "Q", "A", "O", "Z"]
        vigencia_opciones = ["Todas", "Vigentes", "Vencidos", "Por vencer (30 dias)"]

        # Responsables (cualquiera de los 5 roles)
        try:
            resp_list = rag.conn.execute("""
                SELECT DISTINCT TRIM(elaborador) FROM procedimientos WHERE elaborador IS NOT NULL AND elaborador != ''
                UNION
                SELECT DISTINCT TRIM(revisor_proceso) FROM procedimientos WHERE revisor_proceso IS NOT NULL AND revisor_proceso != ''
                UNION
                SELECT DISTINCT TRIM(revisor_calidad) FROM procedimientos WHERE revisor_calidad IS NOT NULL AND revisor_calidad != ''
                UNION
                SELECT DISTINCT TRIM(aprobador_gerencia) FROM procedimientos WHERE aprobador_gerencia IS NOT NULL AND aprobador_gerencia != ''
                UNION
                SELECT DISTINCT TRIM(publicador) FROM procedimientos WHERE publicador IS NOT NULL AND publicador != ''
                ORDER BY 1
            """).fetchall()
            resp_opciones = ["Todos"] + [r[0] for r in resp_list if r[0]]
        except Exception:
            resp_opciones = ["Todos"]

        with col_f1:
            filtro_proceso = st.selectbox("Proceso", procesos_opciones, key="filtro_proc")
        with col_f2:
            filtro_estado = st.selectbox("Estado", estados_opciones, key="filtro_est")
        with col_f3:
            filtro_tipo = st.selectbox("Tipo", tipos_opciones, key="filtro_tipo")
        with col_f4:
            filtro_vigencia = st.selectbox("Vigencia", vigencia_opciones, key="filtro_vig")

        # Filtro de responsable y fecha
        col_f5, col_f6 = st.columns(2)
        with col_f5:
            filtro_responsable = st.selectbox("Responsable", resp_opciones, key="filtro_resp")
        with col_f6:
            st.write("")

        # Filtro de fecha
        col_f7, col_f8 = st.columns(2)
        with col_f7:
            fecha_desde = st.date_input("Publicado desde", value=None, key="filtro_desde")
        with col_f8:
            fecha_hasta = st.date_input("Publicado hasta", value=None, key="filtro_hasta")

    limite = st.selectbox("Resultados:", [20, 50, 100, 200], index=0, key="docs_limit")

    # ─── Construir query con filtros ───
    query_sql = "SELECT codigo, nombre, proceso_nom, estado, estado_desc, tipo_documento, fecha_publicacion, vigencia_dias FROM procedimientos WHERE 1=1"
    params = []

    if busqueda:
        query_sql += " AND (codigo LIKE ? OR nombre LIKE ? OR proceso_nom LIKE ? OR contenido_texto LIKE ?)"
        like_term = f"%{busqueda}%"
        params.extend([like_term, like_term, like_term, like_term])

    if filtro_proceso != "Todos":
        query_sql += " AND proceso_nom = ?"
        params.append(filtro_proceso)

    if filtro_estado != "Todos":
        query_sql += " AND estado = ?"
        params.append(filtro_estado)

    if filtro_tipo != "Todos":
        query_sql += " AND tipo_documento = ?"
        params.append(filtro_tipo)

    if filtro_vigencia == "Vigentes":
        query_sql += " AND estado = 'P'"
    elif filtro_vigencia == "Vencidos":
        query_sql += " AND vigencia_dias IS NOT NULL AND vigencia_dias < 0"
    elif filtro_vigencia == "Por vencer (30 dias)":
        query_sql += " AND vigencia_dias IS NOT NULL AND vigencia_dias >= 0 AND vigencia_dias <= 30"

    if filtro_responsable != "Todos":
        query_sql += """ AND (
            TRIM(elaborador) = ? OR
            TRIM(revisor_proceso) = ? OR
            TRIM(revisor_calidad) = ? OR
            TRIM(aprobador_gerencia) = ? OR
            TRIM(publicador) = ?
        )"""
        params.extend([filtro_responsable] * 5)

    if fecha_desde:
        query_sql += " AND fecha_publicacion >= ?"
        params.append(fecha_desde.strftime("%Y-%m-%d"))

    if fecha_hasta:
        query_sql += " AND fecha_publicacion <= ?"
        params.append(fecha_hasta.strftime("%Y-%m-%d"))

    query_sql += " ORDER BY nombre LIMIT ?"
    params.append(limite)

    try:
        docs_filtrados = rag.conn.execute(query_sql, params).fetchall()
        docs_lista = [
            {"codigo": r[0], "nombre": r[1], "proceso": r[2], "estado": r[3],
             "estado_desc": r[4], "tipo_documento": r[5], "fecha_publicacion": r[6],
             "vigencia_dias": r[7]}
            for r in docs_filtrados
        ]
    except Exception as e:
        st.warning(f"Error en busqueda con filtros, usando busqueda simple: {e}")
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

                # ─── Botones de descarga ───
                col_dl1, col_dl2, col_dl3 = st.columns(3)
                with col_dl1:
                    if st.button("Descargar como TXT", key=f"dl_txt_{codigo_sel}"):
                        texto_completo = f"Documento: {doc['codigo']}\nNombre: {doc['nombre']}\nEstado: {doc.get('estado', '')}\nProceso: {doc.get('proceso', '')}\nTipo: {doc.get('tipo_documento', '')}\nFecha publicacion: {doc.get('fecha_publicacion', '')}\n\n{'='*60}\n\n{doc.get('texto', 'Sin contenido')}"
                        st.download_button(
                            label="Descargar .txt",
                            data=texto_completo.encode("utf-8"),
                            file_name=f"{codigo_sel}.txt",
                            mime="text/plain",
                        )
                with col_dl2:
                    if st.button("Descargar como Markdown", key=f"dl_md_{codigo_sel}"):
                        md_content = f"# {doc['codigo']} - {doc['nombre']}\n\n"
                        md_content += f"- **Estado:** {doc.get('estado', '')}\n"
                        md_content += f"- **Proceso:** {doc.get('proceso', '')}\n"
                        md_content += f"- **Tipo:** {doc.get('tipo_documento', '')}\n"
                        md_content += f"- **Fecha publicacion:** {doc.get('fecha_publicacion', '')}\n\n"
                        if doc.get("resumen"):
                            md_content += f"## Resumen Ejecutivo\n\n{doc['resumen']}\n\n"
                        md_content += f"## Contenido\n\n{doc.get('texto', 'Sin contenido')}\n"
                        st.download_button(
                            label="Descargar .md",
                            data=md_content.encode("utf-8"),
                            file_name=f"{codigo_sel}.md",
                            mime="text/markdown",
                        )
                with col_dl3:
                    if st.button("Descargar como PDF (HTML)", key=f"dl_pdf_{codigo_sel}"):
                        html_content = f"""<html><head><meta charset="utf-8"><title>{doc['codigo']}</title>
                        <style>body {{ font-family: Arial, sans-serif; margin: 40px; }}
                        h1 {{ color: #0066B1; }} table {{ border-collapse: collapse; }}
                        td, th {{ border: 1px solid #ddd; padding: 8px; }}</style></head>
                        <body><h1>{doc['codigo']} - {doc['nombre']}</h1>
                        <table><tr><th>Estado</th><td>{doc.get('estado', '')}</td></tr>
                        <tr><th>Proceso</th><td>{doc.get('proceso', '')}</td></tr>
                        <tr><th>Tipo</th><td>{doc.get('tipo_documento', '')}</td></tr>
                        <tr><th>Fecha publicacion</th><td>{doc.get('fecha_publicacion', '')}</td></tr></table>
                        <h2>Contenido</h2><pre>{doc.get('texto', 'Sin contenido')}</pre></body></html>"""
                        st.download_button(
                            label="Descargar .html",
                            data=html_content.encode("utf-8"),
                            file_name=f"{codigo_sel}.html",
                            mime="text/html",
                        )

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
                    with st.expander("Ver texto completo", expanded=True):
                        st.text_area("Texto", texto, height=500, key=f"texto_{codigo_sel}")
                else:
                    st.warning("No hay texto disponible para este documento.")

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
        "Seguridad RBAC", "RAG Avanzado", "Grafo de Conocimiento",
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
            "  |  |(PII,  |   |(Toxic.|   |(Embed.|                | \n"
            "  |  |Inject)|   | Hate) |   |0.92)  |                | \n"
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
            "  |  5. CHUNKING AVANZADO                             | \n"
            "  |  +-------+   +-------+   +-------+                | \n"
            "  |  |Late   |   |Jerar.|   |Semant.|                | \n"
            "  |  |chun.  |   |quico  |   |ico    |                | \n"
            "  |  +---+---+   +---+---+   +---+---+                | \n"
            "  |            |               |                      | \n"
            "  |  6. CONTEXT + LLM (streaming)                     | \n"
            "  |  +-------+   +-------+   +-------+                | \n"
            "  |  |Skills |   |Glosar.|   |Resumen|                | \n"
            "  |  |(6)    |   |(55)   |   |(ejec.)|                | \n"
            "  |  +---+---+   +---+---+   +---+---+                | \n"
            "  |            |               |                      | \n"
            "  |  7. GUARDRAILS DE SALIDA                           | \n"
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
        st.write("3. FAQ precargada: match exacto, keywords o embedding (respuesta < 1s)")
        st.write("4. Cache semántico con embeddings reales (coseno > 0.92)")
        st.write("5. HyDE: LLM genera documento hipotético (mejora recall)")
        st.write("6. Multi-query: 3 variantes de la pregunta (mejora recall)")
        st.write("7. BM25 + FAISS + Grafo recuperan candidatos (multi-vector fusion)")
        st.write("8. CRAG: evalúa calidad (good/ambiguous/poor), expande si es poor")
        st.write("9. Cross-encoder rerankea + parent-child obtiene secciones relevantes")
        st.write("10. Chunking avanzado: late, jerárquico y semántico")
        st.write("11. Se construye contexto con glosario, resúmenes y skills")
        st.write("12. LLM genera respuesta en streaming (tokens en vivo)")
        st.write("13. Governance filtra PII y valida salida")
        st.write("14. Content moderation verifica salida")
        st.write("15. Cache set: guarda respuesta con embedding")
        st.write("16. Registro de uso para indicadores (usuario, área, proceso)")
        st.write("17. Evaluación LLM-as-judge + RAGAS (feedback continuo)")

        st.info("**Modo rápido (toggle en chat):** omite HyDE, multi-query, RAPTOR y ColBERT cuando la pregunta es corta, contiene un código de documento, es definitoria o tiene alto score semántico directo. Reduce latencia de 150s a ~10-20s.")

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
            "  |   2805 docs       |     | USO + CACHE:      | \n"
            "  +-------------------+     |  cache_semantico  | \n"
            "                            |  usage_stats      | \n"
            "  +-------------------+     |  chat_historial   | \n"
            "  |   EMBEDDINGS      | --> | EVALUACION:       | \n"
            "  |   Mistral 1024d   |     |  pipeline_eval    | \n"
            "  |   + cache queries |     |  rag_eval_summary | \n"
            "  +-------------------+     |  ragas_metrics    | \n"
            "                            | BACKUP:           | \n"
            "  +-------------------+     |  backups/*.zip    | \n"
            "  |   FAISS INDEX     |     | MEMORIA:          | \n"
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
            ("cache_semantico", "Cache semantico con embeddings reales", "variable"),
            ("usage_stats", "Metricas de uso usuario/area/proceso", "variable"),
            ("chat_historial", "Historial de conversaciones persistente", "variable"),
            ("pipeline_eval", "Resultados golden questions + RAGAS", "variable"),
            ("rag_eval_summary", "Resumen de evaluaciones RAG", "variable"),
            ("ragas_metrics", "Metricas RAGAS por respuesta", "variable"),
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
            "  ├── skills/             (10 skills dinamicos)\n"
            "  │   ├── mermaid.md\n"
            "  │   ├── capa.md\n"
            "  │   ├── no_conformidad.md\n"
            "  │   ├── auditoria.md\n"
            "  │   ├── checklists.md\n"
            "  │   ├── refactoring_sops.md\n"
            "  │   ├── busqueda_filtros.md\n"
            "  │   ├── comparador_versiones.md\n"
            "  │   ├── detector_duplicados.md\n"
            "  │   └── exportar.md\n"
            "  ├── system_prompt.md    (prompt consultor + guardrail dominio)\n"
            "  ├── integra_db_client.py (SQL Server solo lectura)\n"
            "  ├── sync_incremental.py  (sync on-demand + reporte)\n"
            "  └── sync_diario.py       (sync diaria automatica + .env)\n\n"
            "  TECNICAS RAG AVANZADAS\n"
            "  ├── HyDE               (documento hipotetico)\n"
            "  ├── Multi-query         (3 variantes de query)\n"
            "  ├── BM25               (lexical, rank_bm25)\n"
            "  ├── FAISS              (semantico, 2805 vectores)\n"
            "  ├── Graph BFS          (NetworkX, 2 hops)\n"
            "  ├── CRAG               (good/ambiguous/poor)\n"
            "  ├── Cross-encoder      (ms-marco-MiniLM-L-6-v2)\n"
            "  ├── Parent-child       (secciones relevantes)\n"
            "  ├── Cache semantico    (embeddings reales, coseno > 0.92)\n"
            "  ├── Cache embeddings   (cache por query, persistente)\n"
            "  ├── Chunking avanzado  (late + jerarquico + semantico)\n"
            "  ├── Modo rapido        (adaptive retrieval segun pregunta)\n"
            "  ├── FAQ precargadas    (respuestas instantaneas frecuentes)\n"
            "  └── Streaming          (tokens en vivo)\n\n"
            "  INTERFACES\n"
            "  ├── web_ui.py           (Streamlit, 16+ tabs)\n"
            "  │   ├── Chat            (streaming + feedback + sugerencias por rol)\n"
            "  │   ├── Estadisticas    (grafos + filtros avanzados)\n"
            "  │   ├── Jerarquia       (procesos)\n"
            "  │   ├── Vencidos        (alertas)\n"
            "  │   ├── Glosario        (terminos)\n"
            "  │   ├── FinOps          (uso, calidad RAG, latency, costos)\n"
            "  │   ├── Documentos      (visor + filtros)\n"
            "  │   ├── Comparador      (diff versiones)\n"
            "  │   ├── Arquitectura    (8 vistas)\n"
            "  │   ├── Seguridad       (auditoria + moderacion + rate limit)\n"
            "  │   ├── Sincronizacion  (sync + backup/restore + reintentos embeddings)\n"
            "  │   ├── Salud del Sistema  (SQL/SQLite/Chroma/FAISS/LLM)\n"
            "  │   ├── Auditoria       (logs + watermarking)\n"
            "  │   ├── No Conformidades (NCs abiertas)\n"
            "  │   ├── Gestion Calidad  (BPMN, KPIs, RACI)\n"
            "  │   └── Diccionario Bilingue (ES/EN)\n"
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
            "  ├── sync_incremental.py      (sync cambios)\n"
            "  ├── sync_diario.py           (sync diaria + .env)\n"
            "  ├── evaluar_rag.py           (golden questions + RAGAS)\n"
            "  ├── sync_vector_stores.py    (repara Chroma/FAISS/SQLite)\n"
            "  └── backup_indices()         (ZIP SQLite + ChromaDB + FAISS)\n",
            language="text"
        )
        st.write("**Skills dinamicos (10):**")
        skills = [
            ("Mermaid", "Flujos, diagramas, Ishikawa, arboles de decision"),
            ("CAPA", "Causa raiz, 5 porques, FMEA, AMEF, 6M, NPR"),
            ("No Conformidad", "NC, hallazgos, desviaciones, planes de accion"),
            ("Auditoria", "Simular auditoria, roleplay, Invima/ISO"),
            ("Checklists", "Formatos, checklists, WMS, Power Apps"),
            ("Refactoring SOPs", "Revisar borradores, auditar calidad documental"),
            ("Busqueda Filtros", "Filtrar por proceso, estado, tipo, fecha"),
            ("Comparador Versiones", "Diff lado a lado, similitud, descarga .diff"),
            ("Detector Duplicados", "FAISS para encontrar docs casi identicos"),
            ("Exportar", "PDF, Word, Excel con la respuesta del agente"),
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
            ("Cache semantico", "Respuestas cacheadas", "embeddings reales, coseno > 0.92"),
            ("Cache embeddings", "Embeddings de query", "persistente en SQLite"),
            ("Chunking avanzado", "Late + jerarquico + semantico", "segun tamano de doc"),
            ("Modo rapido", "Adaptive retrieval automatico", "10-20s en lugar de 150s"),
            ("FAQ precargadas", "Respuestas instantaneas", "match exacto + keywords + embeddings"),
            ("Evaluacion RAG", "Golden questions + RAGAS", "pipeline automatico"),
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
            st.write("- SQLite (indice_procedimientos.db, 27+ tablas)")
            st.write("- ChromaDB (chroma_db/)")
            st.write("- FAISS (faiss_index.bin)")
            st.write("- Cross-encoder (ms-marco-MiniLM-L-6-v2)")
            st.write("- Ollama (qwen2.5:7b local)")
            st.write("- Streamlit (puerto 8501, 16+ tabs)")
            st.write("- FastAPI (puerto 8000)")
            st.write("- Backups (carpeta backups/ con ZIPs)")
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

    elif tipo_sel == "Seguridad RBAC":
        st.subheader("Arquitectura de Seguridad y RBAC")
        st.write("Seguridad granular por roles + watermarking + deteccion de anomalias.")
        st.code(
            "  +---------------------------+\n"
            "  |  USUARIO (login)          |\n"
            "  |  usuario + password       |\n"
            "  |  hash sha256 + salt       |\n"
            "  +-------------+-------------+\n"
            "                |\n"
            "  +-------------+-------------+\n"
            "  |  RBAC (5 roles)           |\n"
            "  |  admin    -> todo         |\n"
            "  |  calidad  -> casi todo    |\n"
            "  |  auditor  -> consulta+NCs |\n"
            "  |  operador -> chat+docs    |\n"
            "  |  usuario  -> chat+glosa  |\n"
            "  +-------------+-------------+\n"
            "                |\n"
            "  +-------------+-------------+\n"
            "  |  SESSION TIMEOUT (30 min) |\n"
            "  +-------------+-------------+\n"
            "                |\n"
            "  +-------------+-------------+\n"
            "  |  DETECCION ANOMALIAS      |\n"
            "  |  20/min, 200/hora, 1000/dia|\n"
            "  +-------------+-------------+\n"
            "                |\n"
            "  +-------------+-------------+\n"
            "  |  WATERMARKING             |\n"
            "  |  <!--wm:user:timestamp--> |\n"
            "  +-------------+-------------+\n",
            language="text"
        )
        st.write("**Roles y permisos:**")
        st.table([
            {"Rol": "admin", "Permisos": "Todos los tabs + gestion usuarios"},
            {"Rol": "calidad", "Permisos": "Todos excepto gestion usuarios"},
            {"Rol": "auditor", "Permisos": "Chat + consulta + auditoria + NCs"},
            {"Rol": "operador", "Permisos": "Chat + documentos + glosario + vencidos"},
            {"Rol": "usuario", "Permisos": "Chat + documentos + glosario"},
        ])

    elif tipo_sel == "RAG Avanzado":
        st.subheader("Arquitectura RAG Avanzado")
        st.write("Pipeline de retrieval con 7 sistemas + RRF + Self-RAG + ColBERT + NER + RAPTOR + Parent-child + 27 mejoras en 6 modulos.")
        st.code(
            "  PREGUNTA\n"
            "    |\n"
            "    v\n"
            "  +--- Self-RAG ---+\n"
            "  |  Necesita     |  NO -> responder directo\n"
            "  |  retrieval?   |\n"
            "  +---+-----------+\n"
            "      | SI\n"
            "      v\n"
            "  +--- Query Expansion ---+\n"
            "  | IQ -> Installation     |\n"
            "  | Qualification         |\n"
            "  +---+-------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- HyDE + Multi-query ---+\n"
            "  |  HyDE: doc hipotetico   |\n"
            "  |  Multi-query: 3 variantes|\n"
            "  +---+---------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- 7 SISTEMAS PARALELOS ---+\n"
            "  |                           |\n"
            "  |  +-- Semantico (FAISS) --+|\n"
            "  |  +-- Lexical (BM25) ----+|\n"
            "  |  +-- Multi-vector       +|\n"
            "  |  |   (ColBERT MaxSim)   ||\n"
            "  |  +-- Grafo (NetworkX) --+|\n"
            "  |  +-- NER entidades -----+|\n"
            "  |  |   (1808 entidades)   ||\n"
            "  |  +-- RAPTOR ------------+|\n"
            "  |  |   (26 nodos, 3 niv)  ||\n"
            "  |  +-- Parent-child ------+|\n"
            "  |  |   (3224+24082 chunks)||\n"
            "  +---+-----------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- RRF (Reciprocal Rank Fusion) ---+\n"
            "  |  RRF(d) = Sum 1/(k + rank_i(d))    |\n"
            "  |  k = 60                            |\n"
            "  +---+-------------------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- CRAG ---+\n"
            "  |  good? -> top 5\n"
            "  |  poor? -> expandir\n"
            "  +---+-------+\n"
            "      |\n"
            "      v\n"
            "  +--- Parent-child + Chunking semantico ---+\n"
            "  |  Secciones relevantes por oraciones     |\n"
            "  +---+-------------------------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- Reranking (hybrid) ---+\n"
            "  |  1. Cross-encoder (top 10)|\n"
            "  |  2. LLM rerank (top 5)   |\n"
            "  +---+---------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- LLM + Guardrails ---+\n"
            "  |  Respuesta + PII filter |\n"
            "  |  + DLP (info sensible)  |\n"
            "  |  + Bias detection       |\n"
            "  |  + Watermarking         |\n"
            "  |  + Confidence score     |\n"
            "  |  + Hallucination detect |\n"
            "  |  + Citation verification |\n"
            "  +---+-------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- Evaluacion ---+\n"
            "  |  LLM-as-judge (1-10)    |\n"
            "  |  RAGAS: faithfulness,   |\n"
            "  |  relevance, recall, prec |\n"
            "  |  Active learning queue   |\n"
            "  +---+-------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- Observabilidad ---+\n"
            "  |  OpenTelemetry traces    |\n"
            "  |  Sentry (PII scrubbing)  |\n"
            "  |  P50/P95/P99 latency     |\n"
            "  |  Cost alerts + dashboards|\n"
            "  +---+-------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- Capacidades Agenticas ---+\n"
            "  |  Plan-execute-verify      |\n"
            "  |  Long-term memory        |\n"
            "  |  Proactividad            |\n"
            "  |  Explicabilidad          |\n"
            "  |  Multi-turn reasoning    |\n"
            "  +---+-------------------+\n"
            "      |\n"
            "      v\n"
            "  +--- Memoria + Audit ---+\n"
            "  |  Chat persistente        |\n"
            "  |  Cache semantico         |\n"
            "  |  Human-in-the-loop       |\n"
            "  |  Change log (documentos) |\n"
            "  |  Audit trail (18 campos) |\n"
            "  +---+-------------------+\n"
            "      |\n"
            "      v\n"
            "  RESPUESTA (con confianza + citas + watermark)\n",
            language="text"
        )
        st.write("**27 tecnicas implementadas en 6 modulos:**")
        tecnicas = [
            ("Self-RAG", "Decide si necesita retrieval"),
            ("Query Expansion", "Expande abreviaciones del dominio"),
            ("HyDE", "Documento hipotetico (200 palabras)"),
            ("Multi-query", "3 variantes de la pregunta"),
            ("BM25", "Retrieval lexical con rank_bm25"),
            ("ColBERT simplificado", "Multi-vector con MaxSim"),
            ("RRF", "Reciprocal Rank Fusion (k=60)"),
            ("CRAG", "Corrective RAG (good/ambiguous/poor)"),
            ("Chunking semantico", "Division por oraciones agrupadas"),
            ("Modo rapido", "Adaptive retrieval automatico"),
            ("FAQ precargadas", "Respuestas instantaneas para consultas frecuentes"),
            ("Cross-encoder", "ms-marco-MiniLM-L-6-v2 (local)"),
            ("LLM reranking", "Hybrid: cross-encoder + LLM"),
            ("NER entidades", "1808 entidades (procesos, normas, temperaturas)"),
            ("RAPTOR", "Arbol jerarquico de resumenes (26 nodos)"),
            ("Parent-child", "3224 padres + 24082 hijos chunks"),
            ("Hallucination detection", "Verifica claims vs documentos"),
            ("Citation verification", "Verifica codigos citados vs DB"),
            ("DLP", "Enmascara secrets y info sensible"),
            ("PII redaction", "Enmascara PII en logs y audit"),
            ("Confidence score", "Alto/Medio/Bajo"),
            ("Citation linking", "Citas clickeables a documentos"),
            ("LLM-as-judge", "Evalua calidad de respuesta (1-10)"),
            ("RAGAS", "faithfulness, relevance, recall, precision"),
            ("Active learning", "Cola de preguntas de baja calidad"),
            ("OpenTelemetry", "Traces distribuidas + fallback local"),
            ("Sentry", "Errores con PII scrubbing"),
            ("Latency P50/P95/P99", "Percentiles por operacion"),
            ("Cost alerts", "Umbral por dia/proveedor"),
            ("Quality dashboards", "7 metricas clave"),
            ("Plan-execute-verify", "Planifica antes de responder"),
            ("Long-term memory", "Preferencias e intereses entre sesiones"),
            ("Proactividad", "Docs vencidos, NCs abiertas, temas"),
            ("Explicabilidad", "Explica retrieval (pasos, scores)"),
            ("Multi-turn reasoning", "Contexto entre turnos, cambio de tema"),
            ("Bias detection", "Sesgos genero/edad/discapacidad"),
            ("Red teaming", "16 ataques (jailbreak, injection, etc.)"),
            ("Human-in-the-loop", "Feedback tipado + dataset fine-tuning"),
            ("Tabla de cambios", "Historial de cambios de documentos"),
        ]
        st.table([{"Tecnica": t[0], "Descripcion": t[1]} for t in tecnicas])

        st.write("**Modulos avanzados:**")
        st.markdown("""
| # | Modulo | Archivo | Capacidades |
|---|--------|---------|--------------|
| 1 | Retrieval Avanzado | `retrieval_avanzado.py` | NER, RAPTOR, parent-child, late chunking, embeddings ES, fine-tuning |
| 2 | Calidad y Seguridad | `calidad_seguridad.py` | Hallucination, citation verification, DLP, PII redaction |
| 3 | Evaluacion | `evaluacion.py` | LLM-as-judge, RAGAS, active learning |
| 4 | Observabilidad Avanzada | `observabilidad_avanzada.py` | OpenTelemetry, Sentry, latency, cost alerts, dashboards |
| 5 | Capacidades Agenticas | `capacidades_agenticas.py` | Plan-execute-verify, memoria LP, proactividad, explicabilidad, multi-turn |
| 6 | Mejoras Extras | `mejoras_extras.py` | Bias detection, red teaming, HITL, tabla de cambios |
""")
    elif tipo_sel == "Grafo de Conocimiento":
        st.subheader("Grafo de Conocimiento Interactivo")
        st.caption("Red de procesos, documentos, responsables y relaciones extraidas de Integr@")

        try:
            nodos = rag.conn.execute("""
                SELECT n.id, n.etiqueta, n.tipo, n.propiedades
                FROM grafo_nodos n
                LIMIT 500
            """).fetchall()

            aristas = rag.conn.execute("""
                SELECT a.origen, a.destino, a.relacion
                FROM grafo_aristas a
                LIMIT 1000
            """).fetchall()

            if not nodos:
                st.info("No hay nodos en el grafo. Ejecuta sincronizacion completa primero.")
            else:
                tipos_nodo = sorted(list(set(n[2] for n in nodos)))
                tipo_filtro = st.multiselect("Filtrar por tipo de nodo:", tipos_nodo, default=tipos_nodo[:min(5, len(tipos_nodo))], key="grafo_tipo")
                nodos_filtrados = [n for n in nodos if n[2] in tipo_filtro]
                ids_filtrados = {n[0] for n in nodos_filtrados}
                aristas_filtradas = [a for a in aristas if a[0] in ids_filtrados and a[1] in ids_filtrados]

                if len(nodos_filtrados) > 300:
                    nodos_filtrados = nodos_filtrados[:300]
                    ids_filtrados = {n[0] for n in nodos_filtrados}
                    aristas_filtradas = [a for a in aristas_filtradas if a[0] in ids_filtrados and a[1] in ids_filtrados]

                import json as _json
                node_data = []
                color_map = {
                    "procedimiento": "#4A90E2",
                    "proceso": "#7ED321",
                    "persona": "#F5A623",
                    "tipo_documento": "#BD10E0",
                    "entidad": "#50E3C2",
                    "tema": "#B8E986",
                    "default": "#9013FE",
                }
                for n in nodos_filtrados:
                    node_data.append({
                        "id": n[0],
                        "label": n[1][:40] if n[1] else n[0][:20],
                        "title": f"Tipo: {n[2]}<br>{n[3][:200] if n[3] else ''}",
                        "color": color_map.get(n[2], color_map["default"]),
                        "group": n[2],
                    })
                edge_data = [{"from": a[0], "to": a[1], "label": a[2][:20]} for a in aristas_filtradas]

                html = f"""
                <div id="mynetwork" style="width: 100%; height: 700px; border: 1px solid lightgray;"></div>
                <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
                <script type="text/javascript">
                var nodes = new vis.DataSet({_json.dumps(node_data, ensure_ascii=False)});
                var edges = new vis.DataSet({_json.dumps(edge_data, ensure_ascii=False)});
                var container = document.getElementById('mynetwork');
                var data = {{nodes: nodes, edges: edges}};
                var options = {{
                    nodes: {{
                        shape: 'dot',
                        size: 16,
                        font: {{size: 14}}
                    }},
                    edges: {{
                        width: 1,
                        color: {{inherit: 'from'}},
                        smooth: {{type: 'continuous'}},
                        font: {{size: 12, align: 'middle'}}
                    }},
                    physics: {{
                        stabilization: false,
                        barnesHut: {{
                            gravitationalConstant: -2000,
                            springConstant: 0.04,
                            springLength: 95
                        }}
                    }},
                    interaction: {{
                        hover: true,
                        tooltipDelay: 200,
                        hideEdgesOnDrag: true
                    }}
                }};
                var network = new vis.Network(container, data, options);
                </script>
                """
                components.html(html, height=720)

                st.write(f"**Nodos mostrados:** {len(node_data)} | **Aristas:** {len(edge_data)}")
        except Exception as e:
            st.error(f"Error cargando grafo: {e}")

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

    st.divider()

    # Deteccion de anomalias
    st.subheader("Deteccion de anomalias (anti-abuso)")
    try:
        anomalias = auth.listar_anomalias(limit=20)
        if anomalias:
            st.warning(f"{len(anomalias)} anomalias detectadas:")
            st.table([
                {"Timestamp": a["timestamp"], "Usuario": a["username"], "Tipo": a["tipo"], "Descripcion": a["descripcion"][:80]}
                for a in anomalias
            ])
        else:
            st.success("No se han detectado anomalias.")
    except Exception as e:
        st.info(f"Deteccion de anomalias no disponible: {e}")

    # ─── Bias Detection (mejoras_extras.py) ───
    st.divider()
    st.subheader("Bias Detection (deteccion de sesgos)")
    st.caption("Detecta sesgos de genero, region, edad, discapacidad y cultural en las respuestas del agente")

    try:
        from mejoras_extras import get_bias_stats, RED_TEAM_ATTACKS
        bias_stats = get_bias_stats(rag.conn)
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            st.metric("Checks realizados", bias_stats.get("total_checks", 0))
        with col_b2:
            st.metric("Respuestas con sesgo", bias_stats.get("biased", 0))
        with col_b3:
            st.metric("Tasa de sesgo", f"{bias_stats.get('bias_rate', 0):.1%}")

        if bias_stats.get("avg_score", 0) > 0:
            st.metric("Score promedio", f"{bias_stats['avg_score']:.3f}")

        # Ultimos checks de bias
        try:
            bias_rows = rag.conn.execute("""
                SELECT timestamp, session_id, bias_score, categories, has_bias
                FROM bias_checks
                ORDER BY id DESC
                LIMIT 20
            """).fetchall()
            if bias_rows:
                st.write("**Ultimos checks de bias:**")
                st.table([
                    {"Timestamp": r[0][:19] if r[0] else "", "Sesion": (r[1] or "")[:20],
                     "Score": f"{r[2]:.3f}" if r[2] else "0",
                     "Categorias": r[3] or "Ninguna",
                     "Sesgo": "Si" if r[4] else "No"}
                    for r in bias_rows
                ])
            else:
                st.info("Aun no hay checks de bias. Haz preguntas al agente para generar datos.")
        except Exception as e:
            st.info(f"Tabla bias_checks no disponible: {e}")
    except ImportError:
        st.warning("Modulo mejoras_extras no disponible.")

    # ─── Red Teaming (mejoras_extras.py) ───
    st.divider()
    st.subheader("Red Teaming (pruebas de seguridad automatizadas)")
    st.caption("16 ataques predefinidos para probar la seguridad del agente")

    try:
        from mejoras_extras import RED_TEAM_ATTACKS, get_red_team_summary
        st.write(f"**Ataques definidos:** {len(RED_TEAM_ATTACKS)}")
        st.write("**Categorias de ataques:**")
        cats = {}
        for a in RED_TEAM_ATTACKS:
            cats.setdefault(a["category"], []).append(a)
        st.table([
            {"Categoria": cat, "Cantidad": len(ataques),
             "Descripcion": ", ".join(a["name"] for a in ataques[:3])}
            for cat, ataques in cats.items()
        ])

        # Resumen historico de red teaming
        rt_summary = get_red_team_summary(rag.conn)
        if rt_summary and rt_summary.get("total_tests", 0) > 0:
            st.write("**Resumen de pruebas ejecutadas:**")
            col_rt1, col_rt2, col_rt3 = st.columns(3)
            with col_rt1:
                st.metric("Pruebas totales", rt_summary["total_tests"])
            with col_rt2:
                st.metric("Bloqueadas", rt_summary["blocked"])
            with col_rt3:
                st.metric("Tasa bloqueo", f"{rt_summary['blocked_rate']:.1%}")

            if rt_summary.get("vulnerabilities"):
                st.error(f"Vulnerabilidades encontradas: {len(rt_summary['vulnerabilities'])}")
                st.table([
                    {"Categoria": v["category"], "Ataque": v["attack"],
                     "Descripcion": v["description"][:80]}
                    for v in rt_summary["vulnerabilities"]
                ])
            else:
                st.success("Sin vulnerabilidades detectadas")
        else:
            st.info("Aun no se han ejecutado pruebas de red teaming.")

        # Boton para ejecutar red teaming
        if st.button("Ejecutar Red Teaming ahora", type="secondary"):
            with st.spinner("Ejecutando pruebas de red teaming..."):
                try:
                    results = rag.ejecutar_red_team()
                    st.success(f"Red teaming completo: {results['passed']}/{results['total']} bloqueados")
                    if results["vulnerabilities"]:
                        st.error(f"Vulnerabilidades encontradas: {len(results['vulnerabilities'])}")
                        st.table([
                            {"Categoria": v["category"], "Ataque": v["attack"],
                             "Descripcion": v["description"][:80]}
                            for v in results["vulnerabilities"]
                        ])
                    st.rerun()
                except Exception as e:
                    st.error(f"Error ejecutando red teaming: {e}")
    except ImportError:
        st.warning("Modulo mejoras_extras no disponible.")

# ──────────────────────────────────────────────
# Tab: Sincronizacion
# ──────────────────────────────────────────────
with tab_sync:
    if not can_access("sincronizacion"):
        st.warning("Tu rol no tiene permiso para Sincronizacion. Requiere rol: admin o calidad.")
    st.markdown("""
    <div class="main-header">
        <h1>Sincronizacion con Integr@</h1>
        <p>Actualiza la base documental local con los cambios de Integr@ (SQL Server)</p>
    </div>
    """, unsafe_allow_html=True)

    # Mensaje de confirmacion despues de recargar el agente
    if st.session_state.get("rag_reloaded"):
        try:
            total_docs = rag.conn.execute("SELECT COUNT(*) FROM procedimientos").fetchone()[0]
            total_emb = rag.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            total_res = rag.conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
            total_nodos = rag.conn.execute("SELECT COUNT(*) FROM grafo_nodos").fetchone()[0]
            st.success(f"Agente recargado correctamente. Datos actuales en memoria: {total_docs} documentos, {total_emb} embeddings, {total_res} resumenes, {total_nodos} nodos en el grafo.")
        except Exception as e:
            st.success(f"Agente recargado correctamente desde SQLite. ({e})")
        st.session_state["rag_reloaded"] = False

    st.write("""
    Esta pagina sincroniza el indice local (SQLite) con la base de datos de Integr@ en SQL Server.
    El agente **solo lee** de Integr@ - nunca modifica, crea ni elimina documentos alla.
    """)

    # Verificar variables de entorno
    db_server = os.environ.get("INTEGRA_DB_SERVER", "10.238.66.14")
    mistral_key = bool(os.environ.get("MISTRAL_API_KEY") or os.environ.get("OPENAI_API_KEY"))

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Servidor Integr@:** {db_server}")
    with col2:
        st.write(f"**API key LLM:** {'Configurada' if mistral_key else 'Falta (necesaria para embeddings/resumenes)'}")

    st.divider()

    # ─── Estado actual ───
    st.subheader("Estado actual del indice")
    try:
        total_local = rag.conn.execute("SELECT COUNT(*) FROM procedimientos").fetchone()[0]
        total_vigentes = rag.conn.execute("SELECT COUNT(*) FROM procedimientos WHERE estado = 'P'").fetchone()[0]
        total_obsoletos = rag.conn.execute("SELECT COUNT(*) FROM procedimientos WHERE estado = 'O'").fetchone()[0]

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Documentos locales", f"{total_local:,}")
        with col2:
            st.metric("Vigentes (P)", f"{total_vigentes:,}")
        with col3:
            st.metric("Obsoletos (O)", f"{total_obsoletos:,}")
    except Exception as e:
        st.warning(f"No se pudo consultar el estado local: {e}")

    # ─── Historial de sincronizaciones ───
    st.subheader("Historial de sincronizaciones")
    try:
        sync_rows = rag.conn.execute("""
            SELECT fecha, nuevos, modificados, eliminados, sin_cambios
            FROM sync_log
            ORDER BY fecha DESC
            LIMIT 10
        """).fetchall()
        if sync_rows:
            st.table([
                {
                    "Fecha": r[0],
                    "Nuevos": r[1],
                    "Modificados": r[2],
                    "Eliminados": r[3],
                    "Sin cambios": r[4],
                }
                for r in sync_rows
            ])
        else:
            st.info("No hay sincronizaciones previas registradas.")
    except Exception:
        st.info("Tabla de sync_log no disponible (primera sincronizacion).")

    st.divider()

    # ─── Opcion 1: Solo reporte (detectar cambios sin aplicar) ───
    st.subheader("Opcion 1: Detectar cambios (solo reporte)")
    st.write("Compara Integr@ con el indice local sin modificar nada. Util para previsualizar que cambiaria.")
    if st.button("Detectar cambios", type="secondary"):
        with st.spinner("Comparando con Integr@..."):
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from sync_incremental import sync_incremental
                reporte = sync_incremental(solo_reporte=True)
                st.success("Comparacion completada.")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Nuevos", len(reporte.get("nuevos", [])))
                with col2:
                    st.metric("Modificados", len(reporte.get("modificados", [])))
                with col3:
                    st.metric("Eliminados", len(reporte.get("eliminados", [])))
                with col4:
                    st.metric("Sin cambios", reporte.get("sin_cambios", 0))

                if reporte.get("nuevos"):
                    with st.expander(f"Documentos nuevos ({len(reporte['nuevos'])})"):
                        st.table([
                            {"Codigo": d["codigo"], "Nombre": d["nombre"][:60]}
                            for d in reporte["nuevos"][:50]
                        ])
                if reporte.get("modificados"):
                    with st.expander(f"Documentos modificados ({len(reporte['modificados'])})"):
                        st.table([
                            {"Codigo": d["codigo"], "Cambios": ", ".join(d["cambios"])}
                            for d in reporte["modificados"][:50]
                        ])
                if reporte.get("eliminados"):
                    with st.expander(f"Documentos eliminados ({len(reporte['eliminados'])})"):
                        st.table([
                            {"Codigo": d["codigo"], "Nombre": d["nombre"][:60]}
                            for d in reporte["eliminados"][:50]
                        ])
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()

    # ─── Opcion 2: Sincronizar documentos (sin embeddings) ───
    st.subheader("Opcion 2: Sincronizar documentos")
    st.write("Descarga documentos nuevos y actualiza modificados. No regenera embeddings ni resumenes.")
    if st.button("Sincronizar documentos", type="primary"):
        with st.spinner("Sincronizando con Integr@..."):
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from sync_incremental import sync_incremental
                reporte = sync_incremental(solo_reporte=False)
                st.success(f"Sincronizacion completada en {reporte.get('tiempo_segundos', 0):.1f}s")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Nuevos", len(reporte.get("nuevos", [])))
                with col2:
                    st.metric("Modificados", len(reporte.get("modificados", [])))
                with col3:
                    st.metric("Eliminados", len(reporte.get("eliminados", [])))
                with col4:
                    st.metric("Sin cambios", reporte.get("sin_cambios", 0))

                if reporte.get("nuevos") or reporte.get("modificados"):
                    st.info("Para actualizar embeddings y resumenes, usa la Opcion 3.")

                # Boton para recargar el agente con los datos nuevos
                st.warning("El agente en memoria tiene datos anteriores. Recarga para usar los datos actualizados.")
                if st.button("Recargar agente con datos actualizados", key="reload_rag_opt2"):
                    import sys
                    print("\n[RELOAD] Boton recargar presionado (Opcion 2)...", file=sys.stderr, flush=True)
                    with st.spinner("Recargando agente desde SQLite..."):
                        st.cache_resource.clear()
                        st.session_state["rag_reloaded"] = True
                        st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()

    # ─── Opcion 3: Sincronizacion completa (documentos + embeddings + resumenes + grafo) ───
    st.subheader("Opcion 3: Sincronizacion completa")
    st.write("""
    Sincroniza documentos, regenera embeddings, resumenes ejecutivos y reconstruye el grafo de conocimiento.
    **Tarda varios minutos** si hay documentos nuevos o modificados.
    """)
    if st.button("Sincronizacion completa (documentos + embeddings + resumenes + grafo)", type="primary"):
        if not mistral_key:
            st.warning("Se necesita API key (MISTRAL_API_KEY u OPENAI_API_KEY) para regenerar embeddings y resumenes.")
        with st.spinner("Sincronizando documentos..."):
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from sync_incremental import sync_completo_con_embeddings
                with st.status("Sincronizacion completa...", expanded=True) as status:
                    st.write("Conectando a Integr@...")
                    reporte = sync_completo_con_embeddings()
                    st.write(f"Documentos: {len(reporte.get('nuevos', []))} nuevos, {len(reporte.get('modificados', []))} modificados")
                    if reporte.get("embeddings_regenerados"):
                        st.write("Embeddings regenerados.")
                    if reporte.get("resumenes_regenerados"):
                        st.write("Resumenes regenerados.")
                    if reporte.get("grafo_reconstruido"):
                        st.write("Grafo de conocimiento reconstruido.")
                    status.update(label="Sincronizacion completa finalizada", state="complete")

                st.success(f"Sincronizacion completa en {reporte.get('tiempo_segundos', 0):.1f}s")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Nuevos", len(reporte.get("nuevos", [])))
                with col2:
                    st.metric("Modificados", len(reporte.get("modificados", [])))
                with col3:
                    st.metric("Eliminados", len(reporte.get("eliminados", [])))

                if reporte.get("embeddings_error"):
                    st.warning(f"Error en embeddings: {reporte['embeddings_error']}")
                if reporte.get("resumenes_error"):
                    st.warning(f"Error en resumenes: {reporte['resumenes_error']}")
                if reporte.get("grafo_error"):
                    st.warning(f"Error en grafo: {reporte['grafo_error']}")

                # Boton para recargar el agente con los datos nuevos
                st.success("Sincronizacion completa. Recarga el agente para usar los datos actualizados en todas las pestañas.")
                if st.button("Recargar agente con datos actualizados", key="reload_rag_opt3", type="primary"):
                    import sys
                    print("\n[RELOAD] Boton recargar presionado (Opcion 3)...", file=sys.stderr, flush=True)
                    with st.spinner("Recargando agente desde SQLite..."):
                        st.cache_resource.clear()
                        st.session_state["rag_reloaded"] = True
                        st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()

    # ─── Configuracion sync diaria automatica ───
    st.subheader("Sincronizacion diaria automatica")
    st.write("""
    Para configurar una sincronizacion automatica diaria (ej. 2:00 AM), crea una tarea en Windows Task Scheduler:

    1. Abre **Task Scheduler** (Programador de tareas)
    2. Crear tarea basica -> Nombre: `SyncIntegra`
    3. Desencadenador: Diariamente a las 2:00 AM
    4. Accion: Iniciar programa
    5. Programa: `python`
    6. Argumentos: `Codigo/sync_diario.py`
    7. Iniciar en: `C:\\\\Users\\\\1121871773\\\\OneDrive - agvco\\\\Documentos\\\\Agente Calidad Codigo`

    O ejecuta este comando en PowerShell (como administrador):
    """)

    st.code("""
$action = New-ScheduledTaskAction -Execute "python" -Argument "Codigo/sync_diario.py" `
    -WorkingDirectory "C:\\Users\\1121871773\\OneDrive - agvco\\Documentos\\Agente Calidad Codigo"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
Register-ScheduledTask -TaskName "SyncIntegra" -Action $action -Trigger $trigger -Settings $settings
    """.strip(), language="powershell")

    st.info("El script `sync_diario.py` sincroniza documentos, embeddings, resumenes y grafo. "
            "Requiere que las variables de entorno (INTEGRA_DB_SERVER, MISTRAL_API_KEY) esten configuradas "
            "en el sistema o en el script.")

    # ─── Reintentar embeddings para documentos fallidos ───
    st.divider()
    st.subheader("Reintentar embeddings fallidos")
    try:
        docs_fallidos = rag.documentos_sin_embedding()
        st.write(f"Documentos con texto pero sin embedding: **{len(docs_fallidos)}**")
        if docs_fallidos:
            with st.expander(f"Ver {len(docs_fallidos)} documentos sin embedding"):
                st.table([{"Codigo": d["codigo"], "Nombre": d["nombre"][:60], "Caracteres": d["texto_length"]} for d in docs_fallidos[:50]])
            if st.button("Reintentar embeddings (solo fallidos)", key="retry_embeddings", type="primary"):
                with st.spinner("Generando embeddings para documentos fallidos..."):
                    try:
                        resultado = rag.reintentar_embeddings_fallidos(batch_size=10)
                        if resultado.get("generados", 0) > 0:
                            st.success(f"Embeddings generados: {resultado['generados']} / {resultado['total']}")
                            st.info("Recarga el agente para actualizar ChromaDB/FAISS si es necesario.")
                        else:
                            st.warning("No se generaron embeddings. Revisa errores.")
                        if resultado.get("errores"):
                            st.error("Errores: " + "; ".join(resultado["errores"][:5]))
                    except Exception as e:
                        st.error(f"Error reintentando embeddings: {e}")
    except Exception as e:
        st.warning(f"No se pudo listar documentos sin embedding: {e}")

    # ─── Backup y restauracion de indices ───
    st.divider()
    st.subheader("Backup y restauracion de indices")
    st.write("Crea o restaura backups de SQLite, ChromaDB, FAISS y resumenes.")

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Crear backup ahora", key="backup_now", type="primary"):
            with st.spinner("Creando backup comprimido..."):
                try:
                    zip_path = rag.backup_indices()
                    st.success(f"Backup creado: {zip_path}")
                    with open(zip_path, "rb") as f:
                        st.download_button(
                            label="Descargar backup",
                            data=f.read(),
                            file_name=Path(zip_path).name,
                            mime="application/zip",
                        )
                except Exception as e:
                    st.error(f"Error creando backup: {e}")

    with col_b2:
        uploaded_backup = st.file_uploader("Subir backup .zip para restaurar", type=["zip"], key="restore_zip")
        if uploaded_backup is not None:
            if st.button("Restaurar backup", key="restore_now"):
                with st.spinner("Restaurando indices..."):
                    try:
                        import tempfile
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                            tmp.write(uploaded_backup.read())
                            tmp_path = tmp.name
                        restored = rag.restore_indices(tmp_path)
                        st.success(f"Restauracion completada: {restored}")
                        st.cache_resource.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error restaurando: {e}")

# ──────────────────────────────────────────────
# Tab: Salud del Sistema
# ──────────────────────────────────────────────
with tab_salud:
    if not can_access("salud"):
        st.warning("Tu rol no tiene permiso para Salud del Sistema. Requiere rol: admin o calidad.")
    st.markdown("""
    <div class="main-header">
        <h1>Salud del Sistema</h1>
        <p>Estado de los componentes del agente Graph RAG</p>
    </div>
    """, unsafe_allow_html=True)

    import time
    st_autorefresh = True

    # ─── 1. SQL Server Integr@ ───
    st.subheader("SQL Server Integr@")
    try:
        from integra_db_client import IntegraDBClient
        server = os.getenv("INTEGRA_DB_SERVER", "10.238.66.14")
        client = IntegraDBClient(server=server)
        sql_conn = client.connect()
        sql_total = sql_conn.execute("SELECT COUNT(*) FROM dbo.PROCEDIMIENTOS").fetchone()[0]
        sql_conn.close()
        st.success(f"✅ SQL Server conectado ({server}) - {sql_total} documentos en Integr@")
    except Exception as e:
        st.error(f"❌ SQL Server no disponible: {e}")

    # ─── 2. SQLite ───
    st.subheader("Base de datos local SQLite")
    try:
        total_docs = rag.conn.execute("SELECT COUNT(*) FROM procedimientos").fetchone()[0]
        con_texto = rag.conn.execute("SELECT COUNT(*) FROM procedimientos WHERE texto_length > 0").fetchone()[0]
        total_emb = rag.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        total_res = rag.conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
        st.success(f"✅ SQLite OK - Documentos: {total_docs}, con texto: {con_texto}, embeddings: {total_emb}, resumenes: {total_res}")
    except Exception as e:
        st.error(f"❌ SQLite error: {e}")

    # ─── 3. ChromaDB ───
    st.subheader("ChromaDB")
    try:
        from chromadb import PersistentClient
        chroma_path = Path(__file__).parent / "chroma_db"
        chroma_client = PersistentClient(path=str(chroma_path))
        collection = chroma_client.get_or_create_collection("procedimientos")
        chroma_count = collection.count()
        st.success(f"✅ ChromaDB OK - {chroma_count} vectores indexados")
    except Exception as e:
        st.error(f"❌ ChromaDB error: {e}")

    # ─── 4. FAISS ───
    st.subheader("FAISS")
    try:
        if hasattr(rag, "faiss_index") and rag.faiss_index is not None and rag.faiss_index.ntotal > 0:
            st.success(f"✅ FAISS OK - {rag.faiss_index.ntotal} vectores cargados en memoria")
        else:
            import faiss
            faiss_path = Path(__file__).parent.parent / "faiss_index.bin"
            if faiss_path.exists():
                index = faiss.read_index(str(faiss_path))
                st.success(f"✅ FAISS OK - {index.ntotal} vectores (archivo {faiss_path.name})")
            else:
                st.warning("⚠ FAISS no inicializado (sin archivo faiss_index.bin)")
    except Exception as e:
        st.error(f"❌ FAISS error: {e}")

    # ─── 5. LLM providers ───
    st.subheader("Proveedores LLM")
    cols = st.columns(3)
    providers = [
        ("OpenAI", os.getenv("OPENAI_API_KEY")),
        ("Mistral", os.getenv("MISTRAL_API_KEY")),
        ("Groq", os.getenv("GROQ_API_KEY")),
        ("Gemini", os.getenv("GEMINI_API_KEY")),
    ]
    for i, (name, key) in enumerate(providers):
        with cols[i % 3]:
            if key:
                st.success(f"✅ {name} configurado")
            else:
                st.warning(f"⚠ {name} sin API key")

    # ─── 6. Resumen visual ───
    st.subheader("Resumen de salud")
    try:
        db_size = (Path(__file__).parent.parent / "indice_procedimientos.db").stat().st_size / (1024 * 1024)
        st.info(f"Tamaño base de datos SQLite: {db_size:.1f} MB")
    except Exception:
        pass

# ──────────────────────────────────────────────
# Tab: Auditoria (Audit Trail)
# ──────────────────────────────────────────────
with tab_audit:
    if not can_access("auditoria"):
        st.warning("Tu rol no tiene permiso para Auditoria. Requiere rol: admin, calidad o auditor.")
    st.markdown("""
    <div class="main-header">
        <h1>Audit Trail</h1>
        <p>Trazabilidad completa de interacciones del agente</p>
    </div>
    """, unsafe_allow_html=True)

    st.write("""
    Registro completo de cada interaccion: pregunta, respuesta, documentos consultados,
    confianza, hallucination detection, evaluacion automatica, tiempo, proveedor LLM y mas.
    """)

    st.divider()

    # ─── Resumen ───
    st.subheader("Resumen")
    try:
        audit_rows = rag.obtener_audit_trail(limit=100) if hasattr(rag, "obtener_audit_trail") else []
        if audit_rows:
            total_interacciones = len(audit_rows)
            bloqueadas = sum(1 for r in audit_rows if r.get("blocked"))
            avg_confidence = sum(r.get("confidence_score", 0) for r in audit_rows) / total_interacciones if total_interacciones else 0
            avg_hallucination = sum(r.get("hallucination_score", 1) for r in audit_rows) / total_interacciones if total_interacciones else 1
            avg_time = sum(r.get("total_time", 0) for r in audit_rows) / total_interacciones if total_interacciones else 0

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Interacciones", total_interacciones)
            with col2:
                st.metric("Bloqueadas", bloqueadas)
            with col3:
                st.metric("Confianza prom.", f"{avg_confidence:.2f}")
            with col4:
                st.metric("Hallucination prom.", f"{avg_hallucination:.2f}")
            with col5:
                st.metric("Tiempo prom. (s)", f"{avg_time:.1f}")
        else:
            st.info("No hay registros de audit trail aun. Haz una pregunta en el Chat para generar registros.")
    except Exception as e:
        st.warning(f"No se pudo cargar el audit trail: {e}")

    st.divider()

    # ─── Filtros ───
    st.subheader("Filtros")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filter_session = st.text_input("Filtrar por session_id", value="", key="audit_filter_session")
    with col_f2:
        filter_limit = st.number_input("Limite de registros", min_value=10, max_value=500, value=50, step=10, key="audit_limit")

    # ─── Tabla de audit trail ───
    st.subheader("Registros detallados")
    try:
        if filter_session:
            audit_rows = rag.obtener_audit_trail(limit=int(filter_limit), session_id=filter_session)
        else:
            audit_rows = rag.obtener_audit_trail(limit=int(filter_limit))

        if audit_rows:
            # Tabla resumida
            table_data = []
            for r in audit_rows:
                conf_emoji = {"alto": "🟢", "medio": "🟡", "bajo": "🔴"}.get(r.get("confidence_nivel", ""), "⚪")
                table_data.append({
                    "Timestamp": (r.get("timestamp", "") or "")[:19],
                    "Session": r.get("session_id", ""),
                    "Pregunta": (r.get("pregunta", "") or "")[:60],
                    "Provider": r.get("provider", ""),
                    f"{conf_emoji} Confianza": r.get("confidence_nivel", ""),
                    "Halluc.": f"{r.get('hallucination_score', 1):.2f}",
                    "Tiempo (s)": f"{r.get('total_time', 0):.1f}",
                    "Bloqueada": "Si" if r.get("blocked") else "No",
                })
            st.dataframe(table_data, width="stretch", hide_index=True)

            # Detalle expandible por registro
            st.subheader("Detalle por interaccion")
            for i, r in enumerate(audit_rows[:20]):
                conf_emoji = {"alto": "🟢", "medio": "🟡", "bajo": "🔴"}.get(r.get("confidence_nivel", ""), "⚪")
                with st.expander(f"{conf_emoji} {(r.get('timestamp', '') or '')[:19]} - {(r.get('pregunta', '') or '')[:60]}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Pregunta:**")
                        st.write(r.get("pregunta", ""))
                        st.write("**Respuesta:**")
                        st.write(r.get("respuesta", "")[:500])
                    with col2:
                        st.write(f"**Session:** {r.get('session_id', '')}")
                        st.write(f"**Provider:** {r.get('provider', '')}")
                        st.write(f"**Confianza:** {r.get('confidence_nivel', '')} ({r.get('confidence_score', 0):.3f})")
                        st.write(f"**Hallucination score:** {r.get('hallucination_score', 1):.3f}")
                        st.write(f"**Claims verificados:** {r.get('hallucination_claims', 0)}")
                        st.write(f"**Tiempo total:** {r.get('total_time', 0):.1f}s")
                        if r.get("blocked"):
                            st.error(f"Bloqueada: {r.get('block_reason', '')}")

                    # Documentos consultados
                    docs = r.get("documentos", [])
                    if docs:
                        st.write("**Documentos consultados:**")
                        for d in docs:
                            st.write(f"- {d.get('codigo', '')} - {d.get('nombre', '')[:60]} (score: {d.get('score', 0):.3f})")
        else:
            st.info("No hay registros para mostrar.")
    except Exception as e:
        st.error(f"Error cargando audit trail: {e}")

    st.divider()

    # ─── Exportar audit trail ───
    st.subheader("Exportar")
    if audit_rows:
        import json as _json
        export_data = _json.dumps(audit_rows, ensure_ascii=False, indent=2, default=str)
        st.download_button(
            label="Descargar audit trail (JSON)",
            data=export_data.encode("utf-8"),
            file_name=f"audit_trail_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )

# ──────────────────────────────────────────────
# Tab: No Conformidades
# ──────────────────────────────────────────────
with tab_nc:
    st.markdown("""
    <div class="main-header">
        <h1>No Conformidades de Integr@</h1>
        <p>Gestion de NCs, correcciones y planes de accion (solo lectura)</p>
    </div>
    """, unsafe_allow_html=True)

    st.write("""
    Consulta no conformidades registradas en Integr@ (SQL Server).
    El agente **solo lee** de Integr@ - nunca modifica, crea ni elimina NCs.
    """)

    st.divider()

    # ─── Estadisticas ───
    st.subheader("Estadisticas")
    nc_api = None
    try:
        from no_conformidades import NoConformidadesAPI
        nc_api = NoConformidadesAPI()
        stats_nc = nc_api.estadisticas_nc()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total NCs", stats_nc.get("total", 0))
        with col2:
            st.metric("Estados distintos", len(stats_nc.get("por_estado", {})))
        with col3:
            st.metric("Procesos con NCs", len(stats_nc.get("por_proceso", {})))

        # Por estado
        por_estado = stats_nc.get("por_estado", {})
        if por_estado:
            st.write("**Por estado:**")
            st.bar_chart(
                [{"estado": str(k), "cantidad": v} for k, v in por_estado.items()],
                x="estado", y="cantidad",
            )

        # Por proceso
        por_proceso = stats_nc.get("por_proceso", {})
        if por_proceso:
            st.write("**Por proceso (top 10):**")
            top_proc = sorted(por_proceso.items(), key=lambda x: -x[1])[:10]
            st.table([{"proceso": k, "ncs": v} for k, v in top_proc])

    except Exception as e:
        st.warning(f"No se pudo conectar a Integr@ para consultar NCs: {e}")
        st.info("Verifica que INTEGRA_DB_SERVER este configurado en .env y haya conexion a SQL Server.")

    st.divider()

    # ─── Buscador de NCs ───
    st.subheader("Buscar no conformidades")
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        nc_busqueda = st.text_input("Buscar por descripcion:", placeholder="Ej: temperatura, desviacion, embalaje...", key="nc_search")
    with col_b2:
        nc_estado_filtro = st.text_input("Filtrar por estado:", placeholder="Ej: Abierta, Cerrada", key="nc_estado")
    with col_b3:
        nc_limite = st.selectbox("Resultados:", [20, 50, 100, 200], index=0, key="nc_limit")

    if nc_api is None:
        st.info("No hay conexion a Integr@. Configura INTEGRA_DB_SERVER en .env para consultar NCs.")
    else:
        try:
            if nc_busqueda:
                ncs_lista = nc_api.buscar_ncs(nc_busqueda, limit=nc_limite)
            else:
                ncs_lista = nc_api.listar_ncs(estado=nc_estado_filtro, limit=nc_limite)

            st.caption(f"{len(ncs_lista)} no conformidades encontradas")

            if ncs_lista:
                # Tabla de NCs
                st.dataframe(
                    [
                        {
                            "Codigo": nc["codigo"],
                            "Que paso": nc["descripcion"][:80],
                            "Estado": nc["estado"],
                            "Fecha": nc["fecha"],
                            "Proceso": nc.get("proceso_nombre", ""),
                        }
                        for nc in ncs_lista
                    ],
                    width="stretch",
                    hide_index=True,
                )

                # Detalle de NC
                st.subheader("Detalle de no conformidad")
                nc_opciones = [f"{nc['codigo']} - {nc['descripcion'][:60]}" for nc in ncs_lista]
                nc_sel = st.selectbox("Selecciona una NC para ver el detalle:", nc_opciones, key="nc_detalle_sel")

                if nc_sel:
                    nc_codigo = nc_sel.split(" - ")[0]
                    nc_detalle = nc_api.obtener_nc(nc_codigo)

                    if nc_detalle:
                        st.divider()
                        st.subheader(f"NC {nc_detalle['codigo']}")

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Estado", nc_detalle.get("estado", ""))
                        with col2:
                            st.metric("Proceso", nc_detalle.get("proceso_nombre", ""))
                        with col3:
                            st.metric("Categoria", nc_detalle.get("categoria", ""))

                        st.write(f"**Fecha creacion:** {nc_detalle.get('fecha_creacion', '')}")
                        st.write(f"**Fecha desviacion:** {nc_detalle.get('fecha_desviacion', '')}")
                        st.write(f"**Norma:** {nc_detalle.get('norma', '')}")
                        st.write(f"**Area:** {nc_detalle.get('area', '')}")

                        st.write("**¿Que paso?:**")
                        st.write(nc_detalle.get("que_paso", ""))

                        if nc_detalle.get("como_paso"):
                            st.write("**¿Como paso?:**")
                            st.write(nc_detalle["como_paso"])

                        if nc_detalle.get("donde_paso"):
                            st.write("**¿Donde paso?:**")
                            st.write(nc_detalle["donde_paso"])

                        if nc_detalle.get("cuando_paso"):
                            st.write("**¿Cuando paso?:**")
                            st.write(nc_detalle["cuando_paso"])

                        if nc_detalle.get("quien"):
                            st.write("**¿Quien?:**")
                            st.write(nc_detalle["quien"])

                        # Correcciones
                        correcciones = nc_detalle.get("correcciones", [])
                        if correcciones:
                            st.subheader(f"Correcciones ({len(correcciones)})")
                            for c in correcciones:
                                with st.expander(f"Correccion {c.get('id', '')} - {c.get('observacion', '')[:60]}"):
                                    st.write(f"**Fecha:** {c['fecha']}")
                                    st.write(f"**Observacion:** {c['observacion']}")
                                    st.write(f"**Registro:** {c['registro']}")

                        # Planes de accion
                        planes = nc_detalle.get("planes_accion", [])
                        if planes:
                            st.subheader(f"Planes de Accion ({len(planes)})")
                            for p in planes:
                                with st.expander(f"Plan {p.get('id', '')} - {p.get('rca', '')[:60]}"):
                                    st.write(f"**Estado:** {p['estado']}")
                                    st.write(f"**Tipo:** {p['tipo']}")
                                    st.write(f"**Fecha registro:** {p['fecha_registro']}")
                                    st.write(f"**Fecha compromiso:** {p['fecha_compromiso']}")
                                    st.write(f"**RCA (analisis causa raiz):** {p['rca']}")
                                    if p.get("accion_ejecutada"):
                                        st.write(f"**Accion ejecutada:** {p['accion_ejecutada']}")
                                    st.write(f"**Aprobacion:** {p['aprobacion']}")
                    else:
                        st.error(f"No se encontro la NC {nc_codigo}")
            else:
                st.info("No se encontraron NCs con los criterios especificados.")

        except Exception as e:
            st.error(f"Error consultando NCs: {e}")

# ──────────────────────────────────────────────
# Tab: Gestion Calidad (BPMN, Hallazgos, RACI, KPIs)
# ──────────────────────────────────────────────
with tab_gestion:
    if not can_access("no_conformidades"):
        st.warning("Tu rol no tiene permiso para Gestion de Calidad. Requiere rol: admin, calidad o auditor.")
    st.markdown("""
    <div class="main-header">
        <h1>Gestion de Calidad Avanzada</h1>
        <p>Grafo de procesos (BPMN), hallazgos, matriz RACI e indicadores automaticos</p>
    </div>
    """, unsafe_allow_html=True)

    try:
        from gestion_calidad import GestionCalidad
        gc = GestionCalidad()
    except Exception as e:
        st.error(f"Error cargando modulo de gestion de calidad: {e}")
        gc = None

    if gc:
        sub_tab_bpmn, sub_tab_hallazgos, sub_tab_raci, sub_tab_kpis = st.tabs([
            "Grafo Procesos (BPMN)", "Hallazgos", "Matriz RACI", "Indicadores KPI"
        ])

        # ─── Grafo de procesos (BPMN) ───
        with sub_tab_bpmn:
            st.subheader("Grafo de Procesos (BPMN)")
            st.write("Visualizacion navegable de procesos y documentos.")

            grafo = gc.grafo_procesos_bpmn()
            st.metric("Procesos", grafo.get("total_procesos", 0))
            st.metric("Documentos", grafo.get("total_documentos", 0))

            # Mostrar nodos y aristas como tabla
            st.write(f"**Nodos:** {len(grafo['nodos'])} | **Aristas:** {len(grafo['aristas'])}")

            # Lista de procesos
            procesos_nodos = [n for n in grafo["nodos"] if n["tipo"] == "proceso"]
            if procesos_nodos:
                st.write("**Procesos disponibles:**")
                proc_sel = st.selectbox(
                    "Selecciona un proceso para ver su flujo:",
                    [f"{n['id']} - {n['nombre']}" for n in procesos_nodos],
                    key="bpmn_proc_sel"
                )
                if proc_sel:
                    proc_codigo = proc_sel.split(" - ")[0].replace("proc:", "")
                    proc_nombre = proc_sel.split(" - ")[1] if " - " in proc_sel else ""

                    # Generar flujo BPMN del proceso
                    with st.spinner("Generando flujo de proceso..."):
                        flujo = gc.flujo_proceso_bpmn(proc_nombre or proc_codigo)

                    st.write(f"**Actividades detectadas:** {flujo['actividades']}")
                    st.write(f"**Documentos base:** {flujo['documentos_base']}")

                    # Mostrar flujo como lista secuencial
                    if flujo["nodos"]:
                        st.write("**Flujo del proceso:**")
                        for nodo in flujo["nodos"]:
                            if nodo["tipo"] == "inicio":
                                st.write(f"**INICIO**")
                            elif nodo["tipo"] == "fin":
                                st.write(f"**FIN**")
                            elif nodo["tipo"] == "decision":
                                st.write(f"**Decision:** {nodo['nombre']} _(doc: {nodo.get('documento', '')})_")
                            else:
                                st.write(f"{nodo['nombre']} _(doc: {nodo.get('documento', '')})_")

            # Exportar grafo como JSON
            col_exp1, col_exp2 = st.columns(2)
            with col_exp1:
                if st.button("Descargar grafo (JSON)"):
                    import json
                    st.download_button(
                        label="Descargar",
                        data=json.dumps(grafo, ensure_ascii=False, indent=2).encode("utf-8"),
                        file_name="grafo_procesos_bpmn.json",
                        mime="application/json",
                    )

        # ─── Hallazgos ───
        with sub_tab_hallazgos:
            st.subheader("Base de Conocimiento de Hallazgos")
            st.write("Hallazgos historicos de auditorias y sus CAPA (acciones correctivas/preventivas).")

            col_h1, col_h2 = st.columns(2)
            with col_h1:
                hal_estado = st.selectbox("Filtrar por estado:", ["Todos", "Abierto", "Cerrado"], key="hal_estado")
            with col_h2:
                hal_proceso = st.text_input("Filtrar por proceso:", key="hal_proc")

            hallazgos = gc.listar_hallazgos(
                estado="" if hal_estado == "Todos" else hal_estado,
                proceso=hal_proceso,
                limit=100
            )

            st.caption(f"{len(hallazgos)} hallazgos encontrados")

            if hallazgos:
                st.dataframe(
                    [
                        {
                            "Codigo": h["codigo"],
                            "Titulo": h["titulo"][:60],
                            "Severidad": h.get("severidad", ""),
                            "Proceso": h.get("proceso", ""),
                            "Estado": h.get("estado", ""),
                            "Fecha": h.get("fecha_deteccion", ""),
                        }
                        for h in hallazgos
                    ],
                    width="stretch",
                    hide_index=True,
                )

                # Detalle de hallazgo
                hal_sel = st.selectbox("Ver detalle:", [f"{h['codigo']} - {h['titulo'][:50]}" for h in hallazgos], key="hal_det")
                if hal_sel:
                    hal_cod = hal_sel.split(" - ")[0]
                    hal_detalle = next((h for h in hallazgos if h["codigo"] == hal_cod), None)
                    if hal_detalle:
                        st.divider()
                        st.write(f"**Codigo:** {hal_detalle['codigo']}")
                        st.write(f"**Titulo:** {hal_detalle['titulo']}")
                        st.write(f"**Descripcion:** {hal_detalle.get('descripcion', '')}")
                        st.write(f"**Tipo:** {hal_detalle.get('tipo', '')}")
                        st.write(f"**Severidad:** {hal_detalle.get('severidad', '')}")
                        st.write(f"**Proceso:** {hal_detalle.get('proceso', '')}")
                        st.write(f"**Documento origen:** {hal_detalle.get('documento_origen', '')}")
                        st.write(f"**Auditoria:** {hal_detalle.get('auditoria', '')}")
                        st.write(f"**Fecha deteccion:** {hal_detalle.get('fecha_deteccion', '')}")
                        st.write(f"**Estado:** {hal_detalle.get('estado', '')}")
                        if hal_detalle.get('capa_aplicada'):
                            st.write(f"**CAPA aplicada:** {hal_detalle['capa_aplicada']}")
                        if hal_detalle.get('fecha_cierre'):
                            st.write(f"**Fecha cierre:** {hal_detalle['fecha_cierre']}")
                        if hal_detalle.get('leccion_aprendida'):
                            st.write(f"**Leccion aprendida:** {hal_detalle['leccion_aprendida']}")

                        # Cerrar hallazgo (solo admin/calidad)
                        if hal_detalle.get("estado") == "Abierto" and can_access("gestion_usuarios"):
                            st.divider()
                            with st.form("cerrar_hallazgo"):
                                st.write("**Cerrar hallazgo con CAPA:**")
                                capa = st.text_area("CAPA aplicada:", key="capa_text")
                                leccion = st.text_area("Leccion aprendida (opcional):", key="leccion_text")
                                if st.form_submit_button("Cerrar hallazgo"):
                                    if capa:
                                        result = gc.cerrar_hallazgo(hal_cod, capa, leccion)
                                        st.success(result["mensaje"])
                                        st.rerun()
                                    else:
                                        st.error("CAPA es obligatorio para cerrar el hallazgo")

            # Registrar nuevo hallazgo (solo admin/calidad)
            if can_access("gestion_usuarios"):
                st.divider()
                with st.expander("Registrar nuevo hallazgo"):
                    with st.form("nuevo_hallazgo"):
                        titulo = st.text_input("Titulo *", key="hal_titulo")
                        descripcion = st.text_area("Descripcion *", key="hal_desc")
                        tipo = st.selectbox("Tipo:", ["", "Auditoria interna", "Auditoria externa", "Desviacion", "NC", "Observacion"], key="hal_tipo")
                        severidad = st.selectbox("Severidad:", ["", "Baja", "Media", "Alta", "Critica"], key="hal_sev")
                        proceso = st.text_input("Proceso", key="hal_proc_new")
                        doc_origen = st.text_input("Documento origen (codigo)", key="hal_doc")
                        auditoria = st.text_input("Auditoria", key="hal_aud")
                        if st.form_submit_button("Registrar"):
                            if titulo and descripcion:
                                result = gc.registrar_hallazgo(titulo, descripcion, tipo, severidad, proceso, doc_origen, auditoria)
                                st.success(f"Hallazgo registrado: {result['codigo']}")
                                st.rerun()
                            else:
                                st.error("Titulo y descripcion son obligatorios")

        # ─── Matriz RACI ───
        with sub_tab_raci:
            st.subheader("Matriz RACI Automatica")
            st.write("Generada desde el contenido de los documentos (responsables, revisores, aprobadores).")

            col_r1, col_r2 = st.columns(2)
            with col_r1:
                raci_doc = st.text_input("Por documento (codigo):", placeholder="Ej: PGC-16-15", key="raci_doc")
            with col_r2:
                raci_proc = st.text_input("Por proceso (nombre):", placeholder="Ej: almacenamiento", key="raci_proc")

            if raci_doc or raci_proc:
                with st.spinner("Generando matriz RACI..."):
                    raci = gc.matriz_raci(documento_codigo=raci_doc, proceso=raci_proc)

                if "error" in raci:
                    st.error(raci["error"])
                elif raci["total_actividades"] == 0:
                    st.info("No se encontraron actividades para generar la matriz RACI.")
                else:
                    st.caption(f"{raci['total_actividades']} actividades encontradas")
                    st.dataframe(
                        [
                            {
                                "Documento": r["documento"],
                                "Proceso": r.get("proceso", ""),
                                "Actividad": r["actividad"][:80],
                                "Responsable (R)": r.get("responsable", ""),
                                "Accountable (A)": r.get("accountable", ""),
                                "Consulted (C)": r.get("consulted", ""),
                                "Informed (I)": r.get("informed", ""),
                            }
                            for r in raci["matriz"]
                        ],
                        width="stretch",
                        hide_index=True,
                    )
            else:
                st.info("Especifica un documento o proceso para generar la matriz RACI.")

        # ─── Indicadores KPI ───
        with sub_tab_kpis:
            st.subheader("Indicadores Automaticos (KPIs)")
            st.write("Calculados desde los documentos y datos disponibles.")

            kpis = gc.indicadores_kpi()

            # Mostrar KPIs en grid
            col1, col2, col3, col4 = st.columns(4)
            kpi_list = list(kpis.items())
            for i, (nombre, info) in enumerate(kpi_list):
                col = [col1, col2, col3, col4][i % 4]
                with col:
                    valor = info["valor"]
                    unidad = info["unidad"]
                    meta = info.get("meta")
                    label = nombre.replace("_", " ").title()
                    if meta is not None:
                        st.metric(label, f"{valor} {unidad}", delta=f"Meta: {meta}")
                    else:
                        st.metric(label, f"{valor} {unidad}")

            st.divider()

            # Tabla detallada de KPIs
            st.write("**Detalle de indicadores:**")
            st.dataframe(
                [
                    {
                        "Indicador": nombre.replace("_", " ").title(),
                        "Valor": info["valor"],
                        "Unidad": info["unidad"],
                        "Meta": info.get("meta", "N/A"),
                    }
                    for nombre, info in kpis.items()
                ],
                width="stretch",
                hide_index=True,
            )

# ──────────────────────────────────────────────
# Tab: Diccionario Bilingue
# ──────────────────────────────────────────────
with tab_bilingue:
    if not can_access("glosario"):
        st.warning("Tu rol no tiene permiso para el Diccionario Bilingue.")
    st.markdown("""
    <div class="main-header">
        <h1>Diccionario Bilingue Español / Ingles</h1>
        <p>Terminos HSEQ en español e ingles para documentos de clientes internacionales</p>
    </div>
    """, unsafe_allow_html=True)

    try:
        from diccionario_bilingue import DiccionarioBilingue
        db = DiccionarioBilingue()
    except Exception as e:
        st.error(f"Error cargando diccionario bilingue: {e}")
        db = None

    if db:
        st.metric("Total terminos", db.total())

        # Buscador
        st.subheader("Buscar termino")
        busqueda_bi = st.text_input("Buscar en español o ingles:", placeholder="Ej: calidad, quality, GMP...", key="bi_search")

        if busqueda_bi:
            resultados = db.buscar(busqueda_bi)
            st.caption(f"{len(resultados)} terminos encontrados")

            for r in resultados:
                with st.expander(f"{r['termino_es']} / {r['termino_en']} ({r['categoria']})"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Español:** {r['termino_es']}")
                        st.write(f"**Definicion:** {r.get('definicion_es', '')}")
                    with col2:
                        st.write(f"**English:** {r['termino_en']}")
                        st.write(f"**Definition:** {r.get('definicion_en', '')}")
        else:
            # Listar por categoria
            st.subheader("Terminos por categoria")
            cats = db.categorias()
            cat_sel = st.selectbox("Categoria:", cats, key="bi_cat")
            if cat_sel:
                terminos = db.listar_por_categoria(cat_sel)
                st.dataframe(
                    [
                        {"Español": t["termino_es"], "English": t["termino_en"], "Categoria": t["categoria"]}
                        for t in terminos
                    ],
                    width="stretch",
                    hide_index=True,
                )

        # Traductor rapido
        st.divider()
        st.subheader("Traductor rapido")
        col_t1, col_t2, col_t3 = st.columns([3, 1, 3])
        with col_t1:
            texto_traducir = st.text_input("Termino a traducir:", key="bi_translate")
        with col_t2:
            direccion = st.selectbox("Direccion:", ["ES → EN", "EN → ES"], key="bi_dir")
        with col_t3:
            if texto_traducir:
                if "ES" in direccion:
                    resultado = db.traducir(texto_traducir, "es", "en")
                else:
                    resultado = db.traducir(texto_traducir, "en", "es")
                if resultado != texto_traducir:
                    st.success(f"**Traduccion:** {resultado}")
                else:
                    st.info("Termino no encontrado en el diccionario")
