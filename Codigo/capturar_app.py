"""
Toma capturas de pantalla de cada pestaña del Agente de Calidad Integr@
y genera un PDF con las capturas y explicaciones.

Requisitos:
- Streamlit corriendo en http://localhost:8501
- Playwright + Chromium instalados
- Pillow instalado
- fpdf2 instalado
"""
import sys
import os
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright
from fpdf import FPDF
from PIL import Image

# Configuracion
URL = "http://localhost:8501"
USERNAME = "admin"
PASSWORD = "admin123"
SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# Lista de pestañas en orden (indice del tab)
# Streamlit tabs se renderizan como divs clickeables
TABS = [
    (0, "login", "Login", "Pantalla de autenticacion"),
    (0, "chat", "Chat", "Chat con el agente de calidad"),
    (1, "estadisticas", "Estadisticas", "Estadisticas del grafo de conocimiento"),
    (2, "jerarquia", "Jerarquia", "Tabla jerarquica de documentos"),
    (3, "vencidos", "Vencidos", "Alertas de vencimiento documental"),
    (4, "glosario", "Glosario", "Glosario de calidad y logistica"),
    (5, "finops", "FinOps", "Dashboard FinOps y metricas"),
    (6, "documentos", "Documentos", "Visor de documentos"),
    (7, "comparador", "Comparador", "Comparador de versiones"),
    (8, "arquitectura", "Arquitectura", "Arquitectura del agente"),
    (9, "seguridad", "Seguridad", "Seguridad y gobernanza"),
    (10, "sincronizacion", "Sincronizacion", "Sincronizacion con Integr@"),
    (11, "auditoria", "Auditoria", "Audit trail"),
    (12, "nc", "No Conformidades", "No conformidades de Integr@"),
    (13, "gestion", "Gestion Calidad", "Gestion de calidad avanzada"),
    (14, "bilingue", "Diccionario Bilingue", "Diccionario bilingue ES/EN"),
]

# Descripciones detalladas de cada pestaña
DESCRIPCIONES = {
    "login": (
        "Pantalla de autenticacion. El usuario ingresa sus credenciales (usuario y password) "
        "para acceder al agente. El usuario por defecto es admin/admin123. El sistema implementa "
        "RBAC con 5 roles: admin, calidad, auditor, operador y usuario. Cada rol tiene permisos "
        "diferentes sobre las pestañas. La sesion se cierra automaticamente despues de 30 minutos "
        "de inactividad."
    ),
    "chat": (
        "Chat conversacional en español con el agente de calidad. El usuario escribe preguntas "
        "en lenguaje natural sobre procedimientos, formatos, no conformidades y procesos de Integr@. "
        "El agente usa Graph RAG Hibrido (BM25 + FAISS + grafo + cross-encoder) para recuperar "
        "documentos relevantes y genera respuestas con streaming y citas a documentos especificos. "
        "Incluye historial persistente, feedback positivo/negativo, y comandos especiales como "
        "/stats, /temas, /jerarquia, /vencidos, /resumen, /glosario."
    ),
    "estadisticas": (
        "Estadisticas del grafo de conocimiento construido a partir de los documentos de Integr@. "
        "Muestra nodos por tipo (documento, proceso, tema, tipo_documento, usuario), documentos por "
        "estado (P=Vigente, O=Obsoleto, E=Elaborado, etc.), documentos por proceso y por tipo. "
        "Incluye graficos de barras y tablas con la distribucion de los 2,805 documentos indexados."
    ),
    "jerarquia": (
        "Tabla jerarquica de documentos organizada como Procesos -> Tipos de documento -> Documentos. "
        "Permite navegar la estructura documental de Integr@ con leyenda de iconos por estado "
        "(verde=vigente, rojo=obsoleto, azul=elaborado, etc.). Incluye filtros por proceso y tipo."
    ),
    "vencidos": (
        "Alertas de vencimiento documental. Muestra documentos vencidos (icono rojo) y por vencer "
        "(icono amarillo) con los dias restantes o dias vencidos. Permite expandir cada alerta para "
        "ver detalles: codigo, nombre, proceso y fecha. Actualmente hay 14 documentos vencidos."
    ),
    "glosario": (
        "Glosario con 55 terminos de calidad HSEQ, logistica farmaceutica, Invima, FDA y OMS. "
        "Permite buscar terminos por texto libre. Cada termino muestra definicion, categoria y "
        "ejemplos. El glosario se incluye automaticamente en el contexto del chat cuando hay "
        "terminos relevantes en la pregunta del usuario."
    ),
    "finops": (
        "Dashboard FinOps (Financial Operations) con metricas en tiempo real del agente. Muestra "
        "total de traces, tokens consumidos, costo en USD, latencia promedio y feedback. Incluye "
        "graficos de traces por dia, tokens por dia, costo por modelo LLM, distribucion de latencia "
        "y traces recientes con detalle completo."
    ),
    "documentos": (
        "Visor de documentos completos con metadatos de Integr@. Incluye busqueda global por codigo, "
        "nombre, proceso o contenido. Filtros avanzados por proceso, estado, tipo, fecha y vigencia. "
        "Cada documento muestra codigo, nombre, proceso, estado, texto completo, resumen ejecutivo, "
        "palabras clave, proposito y alcance. Permite descarga como texto o PDF."
    ),
    "comparador": (
        "Comparador de versiones de documentos. Detecta automaticamente documentos con multiples "
        "versiones y permite comparar dos versiones lado a lado. Resalta texto agregado, eliminado "
        "y modificado. Muestra estadisticas de cambio (parrafos agregados, eliminados, modificados)."
    ),
    "arquitectura": (
        "Diagramas de arquitectura del agente desde 10 perspectivas: empresarial, negocio, soluciones, "
        "datos, ciberseguridad, integraciones, aplicacion, infraestructura, seguridad RBAC y RAG "
        "avanzado. Cada vista muestra diagramas ASCII con la estructura y componentes del sistema."
    ),
    "seguridad": (
        "Panel de seguridad y gobernanza del agente. Muestra estado de governance (guardrails, PII, "
        "prompt injection), moderation (toxicidad, hate speech), rate limiting (20/min, 200/hora, "
        "1000/dia), watermarking, deteccion de anomalias y logs de moderacion. Solo accesible para "
        "roles admin y calidad."
    ),
    "sincronizacion": (
        "Sincronizacion con Integr@ (SQL Server). Permite actualizar el indice local con los cambios "
        "de Integr@. El agente SOLO LEE de Integr@ - nunca modifica, crea ni elimina documentos. "
        "Verifica variables de entorno, estado de conexion, y permite sincronizar documentos y "
        "regenerar embeddings. Solo accesible para roles admin y calidad."
    ),
    "auditoria": (
        "Audit trail completo de cada interaccion del agente. Registra: timestamp, usuario, pregunta, "
        "respuesta, documentos consultados, confianza, deteccion de alucinaciones, evaluacion "
        "automatica, tiempo de respuesta y proveedor LLM usado. Solo accesible para roles admin, "
        "calidad y auditor."
    ),
    "nc": (
        "Consulta de no conformidades registradas en Integr@ (1,215 NCs). Muestra estadisticas por "
        "estado y proceso, lista con busqueda por texto, y detalle de cada NC con: que paso, como "
        "paso, donde paso, cuando paso, quien, correcciones asociadas y planes de accion con RCA "
        "(analisis de causa raiz). El agente SOLO LEE de Integr@."
    ),
    "gestion": (
        "Gestion de calidad avanzada con 4 sub-pestañas: 1) Grafo de procesos BPMN navegable, "
        "2) Base de conocimiento de hallazgos con lecciones aprendidas y CAPA, 3) Matriz RACI "
        "automatica extraida de documentos (Responsable, Aprobador, Consultado, Informado), "
        "4) Indicadores KPI automaticos (tasa NC, tiempo CAPA, documentos vigentes). Solo "
        "accesible para roles admin, calidad y auditor."
    ),
    "bilingue": (
        "Diccionario bilingue español/ingles de terminos HSEQ para documentos de clientes "
        "internacionales (FDA, OMS). Permite buscar terminos en ambos idiomas. Cada termino "
        "muestra traduccion, definicion y contexto. Util para redactar documentos en ingles "
        "para auditorias internacionales."
    ),
}


def captura_completa(page, path, viewport_h=1080):
    """Toma una captura completa haciendo scroll y uniendo las partes.
    Streamlit usa contenedores con scroll interno, por lo que full_page=True
    no captura todo el contenido."""
    # Obtener la altura total del contenido scrollable
    # Streamlit usa [data-testid="stAppViewContainer"] o section.main como contenedor scrollable
    total_h = page.evaluate("""() => {
        // Buscar el contenedor scrollable de Streamlit
        const containers = [
            document.querySelector('[data-testid="stAppViewContainer"]'),
            document.querySelector('section[data-testid="stAppViewContainer"]'),
            document.querySelector('section.main'),
            document.querySelector('[tabindex="0"]'),
            document.body,
        ];
        for (const c of containers) {
            if (c && c.scrollHeight > window.innerHeight) {
                return c.scrollHeight;
            }
        }
        return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
    }""")

    # Tambien buscar dentro de iframes
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            frame_h = frame.evaluate("""() => {
                const containers = [
                    document.querySelector('[data-testid="stAppViewContainer"]'),
                    document.querySelector('section[data-testid="stAppViewContainer"]'),
                    document.querySelector('section.main'),
                    document.querySelector('[tabindex="0"]'),
                    document.body,
                ];
                for (const c of containers) {
                    if (c && c.scrollHeight > window.innerHeight) {
                        return c.scrollHeight;
                    }
                }
                return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
            }""")
            if frame_h > total_h:
                total_h = frame_h
        except Exception:
            pass

    if total_h <= viewport_h:
        # El contenido cabe en una sola captura
        page.screenshot(path=str(path), full_page=True)
        return

    # Tomar multiples capturas con scroll
    parts = []
    scroll_y = 0
    part_num = 0

    while scroll_y < total_h:
        # Hacer scroll
        page.evaluate(f"window.scrollTo(0, {scroll_y})")
        # Tambien scroll en el contenedor de Streamlit
        page.evaluate(f"""() => {{
            const containers = [
                document.querySelector('[data-testid="stAppViewContainer"]'),
                document.querySelector('section[data-testid="stAppViewContainer"]'),
                document.querySelector('section.main'),
                document.querySelector('[tabindex="0"]'),
            ];
            for (const c of containers) {{
                if (c) c.scrollTop = {scroll_y};
            }}
        }}""")
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                frame.evaluate(f"window.scrollTo(0, {scroll_y})")
                frame.evaluate(f"""() => {{
                    const containers = [
                        document.querySelector('[data-testid="stAppViewContainer"]'),
                        document.querySelector('section.main'),
                        document.querySelector('[tabindex="0"]'),
                    ];
                    for (const c of containers) {{
                        if (c) c.scrollTop = {scroll_y};
                    }}
                }}""")
            except Exception:
                pass

        time.sleep(0.5)

        # Capturar
        part_path = str(path).replace(".png", f"_part{part_num}.png")
        page.screenshot(path=part_path, full_page=False)
        parts.append(part_path)
        part_num += 1

        scroll_y += viewport_h

    # Unir las partes con PIL
    if len(parts) > 0:
        imgs = [Image.open(p) for p in parts]
        total_height = sum(img.height for img in imgs)
        max_width = max(img.width for img in imgs)

        combined = Image.new("RGB", (max_width, total_height), "white")
        y_offset = 0
        for img in imgs:
            combined.paste(img, (0, y_offset))
            y_offset += img.height
            img.close()

        combined.save(str(path))
        combined.close()

        # Limpiar partes temporales
        for p in parts:
            try:
                os.remove(p)
            except Exception:
                pass


def tomar_capturas():
    """Toma capturas de pantalla de cada pestaña."""
    capturas = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="es-ES",
        )
        page = context.new_page()

        # ─── 1. Captura del login ───
        print("Navegando a la aplicacion...")
        page.goto(URL, wait_until="networkidle", timeout=60000)
        time.sleep(5)

        login_path = SCREENSHOTS_DIR / "login.png"
        page.screenshot(path=str(login_path), full_page=True)
        capturas["login"] = login_path

        # ─── 2. Hacer login ───
        print("Haciendo login...")
        # Streamlit usa iframes - buscar el iframe principal
        frames = page.frames
        print(f"  Frames encontrados: {len(frames)}")

        # El iframe de Streamlit normalmente es el segundo frame
        st_frame = None
        for frame in frames:
            if "streamlit" in frame.url.lower() or "localhost" in frame.url.lower():
                if frame != page.main_frame:
                    st_frame = frame
                    break

        # Si no hay iframe, usar el frame principal
        if st_frame is None:
            st_frame = page.main_frame
            print(f"  Usando frame principal")
        else:
            print(f"  Usando iframe: {st_frame.url}")

        # Buscar inputs dentro del frame correcto
        inputs = st_frame.query_selector_all("input")
        print(f"  Inputs encontrados: {len(inputs)}")

        # Llenar usuario (primer input de texto)
        user_filled = False
        pass_filled = False
        for inp in inputs:
            input_type = inp.get_attribute("type") or "text"
            aria_label = inp.get_attribute("aria-label") or ""
            print(f"    Input: type={input_type}, aria-label={aria_label}")

            if input_type == "password" and not pass_filled:
                inp.fill(PASSWORD)
                pass_filled = True
                print(f"  Password llenado")
            elif input_type != "password" and not user_filled:
                inp.fill(USERNAME)
                user_filled = True
                print(f"  Usuario llenado: {USERNAME}")

        if not user_filled or not pass_filled:
            # Intentar con selectores mas especificos
            try:
                user_input = st_frame.query_selector('[data-testid="stTextInputInput"]')
                if user_input and not user_filled:
                    user_input.fill(USERNAME)
                    user_filled = True
                    print(f"  Usuario llenado (via testid)")
            except Exception:
                pass

        # Click en boton Entrar o presionar Enter
        time.sleep(1)
        try:
            # Buscar boton por texto
            buttons = st_frame.query_selector_all("button")
            print(f"  Botones encontrados: {len(buttons)}")
            for btn in buttons:
                btn_text = btn.inner_text() or ""
                print(f"    Button: {btn_text}")
                if "Entrar" in btn_text or "entrar" in btn_text.lower():
                    btn.click()
                    print(f"  Click en boton: {btn_text}")
                    break
            else:
                # Intentar Enter en el ultimo input
                st_frame.keyboard.press("Enter")
                print(f"  Enter presionado")
        except Exception as e:
            print(f"  [WARN] Error clickeando boton: {e}")
            st_frame.keyboard.press("Enter")

        # Esperar a que cargue despues del login
        time.sleep(10)
        print(f"  Login completado")

        # ─── 3. Capturar cada pestaña ───
        # Buscar tabs dentro del frame correcto
        # Streamlit tabs tienen role="tab" o son botones con clase specifica
        tab_elements = st_frame.query_selector_all('[role="tab"]')
        print(f"Tabs encontrados: {len(tab_elements)}")

        # Si no encuentra con role=tab, intentar con otros selectores
        if len(tab_elements) == 0:
            tab_elements = st_frame.query_selector_all('.stTabs [role="tab"]')
            print(f"  (selector alternativo) Tabs: {len(tab_elements)}")

        if len(tab_elements) == 0:
            # Streamlit 1.58 usa button con aria-selected
            tab_elements = st_frame.query_selector_all('button[role="tab"]')
            print(f"  (button role=tab) Tabs: {len(tab_elements)}")

        if len(tab_elements) == 0:
            # Ultimo intento: buscar por texto de los tabs conocidos
            tab_names = ["Chat", "Estadisticas", "Jerarquia", "Vencidos", "Glosario",
                        "FinOps", "Documentos", "Comparador", "Arquitectura", "Seguridad",
                        "Sincronizacion", "Auditoria", "No Conformidades",
                        "Gestion Calidad", "Diccionario Bilingue"]
            print(f"  Buscando tabs por nombre...")
            for tname in tab_names:
                try:
                    el = st_frame.query_selector(f'button:has-text("{tname}")')
                    if el:
                        tab_elements.append(el)
                except Exception:
                    pass
            print(f"  (por nombre) Tabs: {len(tab_elements)}")

        for idx, (tab_idx, key, nombre, titulo) in enumerate(TABS):
            if key == "login":
                continue

            print(f"Capturando pestaña: {nombre} (tab {tab_idx})...")

            try:
                # Obtener tabs nuevamente
                if len(tab_elements) == 0:
                    tab_elements = st_frame.query_selector_all('[role="tab"]')

                if tab_idx < len(tab_elements):
                    tab_elements[tab_idx].click()
                    time.sleep(5)  # Esperar a que cargue el contenido

                    # Capturar contenido completo con scroll
                    path = SCREENSHOTS_DIR / f"{key}.png"
                    captura_completa(page, path)
                    capturas[key] = path
                    print(f"  [OK] {nombre} capturado")
                else:
                    # Intentar por nombre
                    try:
                        btn = st_frame.query_selector(f'button:has-text("{nombre}")')
                        if btn:
                            btn.click()
                            time.sleep(5)
                            path = SCREENSHOTS_DIR / f"{key}.png"
                            captura_completa(page, path)
                            capturas[key] = path
                            print(f"  [OK] {nombre} capturado (por nombre)")
                        else:
                            print(f"  [WARN] Tab {tab_idx} no encontrado")
                    except Exception as e2:
                        print(f"  [WARN] Tab {tab_idx} no existe: {e2}")
            except Exception as e:
                print(f"  [ERROR] No se pudo capturar {nombre}: {e}")

        browser.close()

    return capturas


def generar_pdf(capturas):
    """Genera el PDF con las capturas y explicaciones."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ─── PORTADA ───
    pdf.add_page()
    pdf.ln(50)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(0, 120, 212)
    pdf.cell(0, 15, "Guia Visual de la Aplicacion", 0, 1, "C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 10, "Agente de Calidad Integr@", 0, 1, "C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7, "Consultor HSEQ con RAG Hibrido", 0, 1, "C")
    pdf.cell(0, 7, "AGV Open Market", 0, 1, "C")
    pdf.ln(30)
    pdf.set_draw_color(0, 120, 212)
    pdf.set_line_width(1)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 7, "Manual visual con capturas de pantalla", 0, 1, "C")
    pdf.cell(0, 7, "de cada pestaña y funcionalidad", 0, 1, "C")
    pdf.ln(40)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Fecha: {__import__('datetime').datetime.now().strftime('%d/%m/%Y')}", 0, 1, "C")
    pdf.cell(0, 6, "Version: 1.0", 0, 1, "C")

    # ─── PAGINAS CON CAPTURAS ───
    for idx, (tab_idx, key, nombre, titulo) in enumerate(TABS):
        if key not in capturas:
            print(f"  [SKIP] {nombre} - sin captura")
            continue

        pdf.add_page()

        # Titulo de la pestaña
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(0, 120, 212)
        pdf.cell(0, 10, f"{idx}. {nombre}", 0, 1, "L")
        pdf.set_draw_color(0, 120, 212)
        pdf.set_line_width(0.3)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

        # Subtitulo
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 6, titulo, 0, 1, "L")
        pdf.ln(3)

        # Descripcion
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 30, 30)
        desc = DESCRIPCIONES.get(key, "")
        pdf.multi_cell(0, 5, desc)
        pdf.ln(5)

        # Captura de pantalla - dividir en multiples paginas si es muy alta
        img_path = capturas[key]
        try:
            img = Image.open(str(img_path))
            img_w, img_h = img.size

            # Dimensiones utiles de pagina A4: 190mm ancho, 277mm alto (con margenes)
            page_w_mm = 190
            page_h_mm = 277  # alto util de pagina A4

            # Convertir dimensiones de imagen de pixeles a mm (1 px = 0.264583 mm a 96 DPI)
            img_w_mm = img_w * 0.264583
            img_h_mm = img_h * 0.264583

            # Escalar al ancho de pagina manteniendo aspect ratio
            scale = page_w_mm / img_w_mm
            scaled_w_mm = page_w_mm
            scaled_h_mm = img_h_mm * scale

            # Cuantas paginas necesita la imagen
            # La primera pagina tiene menos espacio (titulo + descripcion ya ocupan ~50mm)
            first_page_h_mm = page_h_mm - 55  # espacio restante despues del texto
            if scaled_h_mm <= first_page_h_mm:
                # Cabe en una sola pagina
                pdf.image(str(img_path), x=10, w=scaled_w_mm)
            else:
                # Dividir la imagen en multiples paginas
                # Calcular cuantos pixeles corresponden a cada pagina
                px_per_mm = img_w / img_w_mm  # pixeles por mm (escala original)
                first_page_px = int(first_page_h_mm * px_per_mm / scale)
                full_page_px = int(page_h_mm * px_per_mm / scale)

                # Primera porcion
                top = 0
                bottom = min(first_page_px, img_h)
                img_crop = img.crop((0, top, img_w, bottom))
                crop_path = SCREENSHOTS_DIR / f"{key}_p1.png"
                img_crop.save(str(crop_path))
                img_crop.close()
                pdf.image(str(crop_path), x=10, w=scaled_w_mm)

                # Paginas adicionales
                page_num = 2
                top = bottom
                while top < img_h:
                    pdf.add_page()
                    bottom = min(top + full_page_px, img_h)
                    img_crop = img.crop((0, top, img_w, bottom))
                    crop_path = SCREENSHOTS_DIR / f"{key}_p{page_num}.png"
                    img_crop.save(str(crop_path))
                    img_crop.close()
                    pdf.image(str(crop_path), x=10, w=scaled_w_mm)
                    top = bottom
                    page_num += 1

            img.close()

        except Exception as e:
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(150, 150, 150)
            pdf.cell(0, 5, f"[Captura no disponible: {e}]", 0, 1, "L")

    # ─── PAGINA FINAL ───
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 120, 212)
    pdf.cell(0, 10, "Resumen del Sistema", 0, 1, "L")
    pdf.set_draw_color(0, 120, 212)
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 5,
        "El Agente de Calidad Integr@ es una plataforma completa de consulta HSEQ "
        "que combina RAG hibrido, grafo de conocimiento, governance AI y gestion "
        "de calidad. Conecta a Integr@ como fuente de verdad y entrega respuestas "
        "precisas en español con citas a documentos especificos."
    )
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "15 pestañas con funcionalidades especializadas:", 0, 1, "L")
    pdf.ln(2)

    resumen = [
        ("Chat", "Consultas en lenguaje natural con RAG hibrido"),
        ("Estadisticas", "Metricas del grafo de conocimiento"),
        ("Jerarquia", "Estructura procesos -> tipos -> documentos"),
        ("Vencidos", "Alertas de vencimiento documental"),
        ("Glosario", "55 terminos de calidad HSEQ"),
        ("FinOps", "Dashboard de tokens, costos y latencia"),
        ("Documentos", "Visor y descarga de documentos"),
        ("Comparador", "Comparar versiones de documentos"),
        ("Arquitectura", "10 vistas de arquitectura del sistema"),
        ("Seguridad", "Guardrails, moderacion y anomalias"),
        ("Sincronizacion", "Sync con Integr@ (solo lectura)"),
        ("Auditoria", "Audit trail completo de interacciones"),
        ("No Conformidades", "1,215 NCs de Integr@ con correcciones y CAPA"),
        ("Gestion Calidad", "BPMN, hallazgos, RACI y KPIs automaticos"),
        ("Diccionario Bilingue", "Terminos HSEQ en español e ingles"),
    ]

    for nombre, desc in resumen:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 120, 212)
        pdf.cell(50, 5, f"- {nombre}:", 0, 0, "L")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 5, desc, 0, 1, "L")

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "5 roles con permisos granulares (RBAC):", 0, 1, "L")
    pdf.ln(2)

    roles = [
        ("admin", "Todos los permisos + gestion de usuarios"),
        ("calidad", "Todos excepto gestion de usuarios"),
        ("auditor", "Chat, consulta, auditoria y NCs"),
        ("operador", "Chat, documentos, glosario y vencidos"),
        ("usuario", "Chat, documentos y glosario"),
    ]

    for rol, desc in roles:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 120, 212)
        pdf.cell(40, 5, f"- {rol}:", 0, 0, "L")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 5, desc, 0, 1, "L")

    # Guardar
    output_path = Path(__file__).parent.parent / "Guia_Visual_Agente_Calidad.pdf"
    pdf.output(str(output_path))
    print(f"\nPDF generado: {output_path}")
    print(f"Tamano: {output_path.stat().st_size / 1024:.1f} KB")
    return output_path


if __name__ == "__main__":
    print("=" * 60)
    print("  Capturas de pantalla del Agente de Calidad Integr@")
    print("=" * 60)
    print(f"\nURL: {URL}")
    print(f"Usuario: {USERNAME}")
    print(f"Directorio capturas: {SCREENSHOTS_DIR}\n")

    # Tomar capturas
    print("\n--- TOMANDO CAPTURAS ---\n")
    capturas = tomar_capturas()
    print(f"\nTotal capturas: {len(capturas)}")

    # Generar PDF
    print("\n--- GENERANDO PDF ---\n")
    pdf_path = generar_pdf(capturas)

    print("\n" + "=" * 60)
    print("  COMPLETADO")
    print("=" * 60)
