"""
Genera resúmenes ejecutivos de cada procedimiento usando Mistral,
construye la tabla jerárquica de contenido y detecta documentos vencidos.

Uso:
    $env:MISTRAL_API_KEY="<tu_api_key>"
    python Codigo/generar_resumenes.py
"""
import json
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from openai import OpenAI

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Manejo graceful de Ctrl+C
_INTERRUPTED = False

def _signal_handler(signum, frame):
    global _INTERRUPTED
    _INTERRUPTED = True

signal.signal(signal.SIGINT, _signal_handler)

def interruptible_sleep(seconds: float, msg: str = ""):
    """Sleep que puede ser interrumpido con Ctrl+C.
    Verifica el flag cada 0.5s en vez de bloquear todo el tiempo."""
    if msg:
        print(msg, end="", flush=True)
    elapsed = 0.0
    while elapsed < seconds:
        if _INTERRUPTED:
            return
        chunk = min(0.5, seconds - elapsed)
        time.sleep(chunk)
        elapsed += chunk

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
CHAT_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
BATCH_SIZE = 5  # resúmenes por lote (cada uno es una llamada al LLM)
MAX_TEXT = 1500  # texto máximo enviado al LLM por documento (optimizado para Ollama CPU)

# Fallback OpenAI - configurable vía env var (puede estar bloqueado por firewall)
OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")

# Fallback Groq - configurable vía env var
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_CHAT_MODEL = os.environ.get("GROQ_CHAT_MODEL", "groq/compound")

# Fallback Gemini (Google AI Studio) - tier gratuito
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_CHAT_MODEL = os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.0-flash")

# Fallback Ollama (local) - sin rate limit ni firewall
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "qwen-fast")

RATE_LIMIT_WAIT = 10
MAX_RETRIES = 3
MAX_RECONNECT_RETRIES = 5
RECONNECT_WAIT = 30


def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def _get_openai_client():
    """Inicializa cliente OpenAI si hay API key disponible."""
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        return None
    try:
        from openai import OpenAI as OpenAIClient
        return OpenAIClient(api_key=openai_key, timeout=120.0, max_retries=2)
    except Exception:
        return None


def _get_groq_client():
    """Inicializa cliente Groq si hay API key disponible."""
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        return None
    try:
        from openai import OpenAI as OpenAIClient
        return OpenAIClient(base_url=GROQ_BASE_URL, api_key=groq_key, timeout=60.0, max_retries=2)
    except Exception:
        return None


def _get_gemini_client():
    """Inicializa cliente Gemini (Google AI Studio) si hay API key disponible."""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        return None
    try:
        from openai import OpenAI as OpenAIClient
        return OpenAIClient(base_url=GEMINI_BASE_URL, api_key=gemini_key, timeout=60.0, max_retries=2)
    except Exception:
        return None


def _get_ollama_client():
    """Inicializa cliente Ollama (local). No requiere API key."""
    try:
        from openai import OpenAI as OpenAIClient
        return OpenAIClient(base_url=OLLAMA_BASE_URL, api_key="ollama", timeout=120.0, max_retries=2)
    except Exception:
        return None


def _try_provider(provider_client, model, messages, max_tokens=300, provider_name=""):
    """Intenta una llamada al LLM. Retorna (texto, None) o (None, error_type)."""
    try:
        resp = provider_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip(), None
    except Exception as e:
        err = str(e)
        err_type = type(e).__name__
        # Clasificar el error
        if "429" in err or "rate" in err.lower():
            return None, "rate_limit"
        elif "401" in err or "auth" in err.lower() or "api key" in err.lower():
            return None, f"auth_error"
        elif "404" in err or "model_not_found" in err:
            return None, f"model_not_found"
        elif "timeout" in err.lower() or "APITimeoutError" in err_type:
            return None, "timeout"
        else:
            return None, f"{err_type}"


def llm_chat(client, prompt: str, system_msg: str,
             openai_client=None, groq_client=None, gemini_client=None, ollama_client=None,
             use_openai: bool = False, use_groq: bool = False, use_gemini: bool = False, use_ollama: bool = False):
    """Llama al LLM con cascada: Ollama (local) → Mistral → Groq → Gemini → OpenAI.
    Ollama es primario (sin rate limit ni firewall). Las nubes son fallback de velocidad.
    Retorna (respuesta_texto, modelo_usado).
    """
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]

    # Modo forzado: si se fuerza un proveedor específico, intentarlo primero
    if use_ollama and ollama_client:
        result, err = _try_provider(ollama_client, OLLAMA_CHAT_MODEL, messages, provider_name="ollama")
        if result:
            return result, "ollama"
        print(f"\n  ⚠ Ollama forzado falló: {err}", end="")
    if use_groq and groq_client:
        result, err = _try_provider(groq_client, GROQ_CHAT_MODEL, messages, provider_name="groq")
        if result:
            return result, "groq"
        print(f"\n  ⚠ Groq forzado falló: {err}", end="")
    if use_gemini and gemini_client:
        result, err = _try_provider(gemini_client, GEMINI_CHAT_MODEL, messages, provider_name="gemini")
        if result:
            return result, "gemini"
        print(f"\n  ⚠ Gemini forzado falló: {err}", end="")
    if use_openai and openai_client:
        result, err = _try_provider(openai_client, OPENAI_CHAT_MODEL, messages, provider_name="openai")
        if result:
            return result, "openai"
        print(f"\n  ⚠ OpenAI forzado falló: {err}", end="")

    # ── PRIMARIO: Ollama (local, sin rate limit, sin firewall) ──
    if ollama_client:
        result, err = _try_provider(ollama_client, OLLAMA_CHAT_MODEL, messages, provider_name="ollama")
        if result:
            return result, "ollama"
        # Si Ollama falla, intentar nubes como fallback
        print(f"\n  ⚠ Ollama falló: {err}. Intentando nubes...", end="")

    # ── FALLBACK VELOCIDAD: Mistral (cloud, rápido) ──
    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip(), "mistral"
    except Exception as e:
        err_msg = str(e)
        err_type = type(e).__name__

        # Rate limit Mistral → Groq → Gemini → OpenAI → backoff con Ollama
        if "429" in err_msg or "rate" in err_msg.lower():
            # Intentar Groq
            if groq_client:
                print(f"\n  ⚡ Rate limit Mistral → Groq...", end="")
                result, err = _try_provider(groq_client, GROQ_CHAT_MODEL, messages, provider_name="groq")
                if result:
                    return result, "groq"
                print(f" ⚠ Groq falló: {err}", end="")

            # Intentar Gemini
            if gemini_client:
                print(f"\n  ⚡ Fallback Gemini...", end="")
                result, err = _try_provider(gemini_client, GEMINI_CHAT_MODEL, messages, provider_name="gemini")
                if result:
                    return result, "gemini"
                print(f" ⚠ Gemini falló: {err}", end="")

            # Intentar OpenAI (puede estar bloqueado)
            if openai_client:
                print(f"\n  ⚡ Fallback OpenAI...", end="")
                result, err = _try_provider(openai_client, OPENAI_CHAT_MODEL, messages, provider_name="openai")
                if result:
                    return result, "openai"
                print(f" ⚠ OpenAI falló: {err}", end="")

            # Si todas las nubes fallan, Ollama es el salvavidas (sin backoff, directo)
            if ollama_client:
                print(f"\n  ⚡ Todas las nubes limitadas → Ollama (local)...", end="")
                result, err = _try_provider(ollama_client, OLLAMA_CHAT_MODEL, messages, provider_name="ollama")
                if result:
                    return result, "ollama"
                print(f" ⚠ Ollama falló: {err}", end="")

            # Backoff rotando, con Ollama primero en cada intento
            providers = []
            if ollama_client:
                providers.append(("ollama", ollama_client, OLLAMA_CHAT_MODEL))
            if groq_client:
                providers.append(("groq", groq_client, GROQ_CHAT_MODEL))
            if gemini_client:
                providers.append(("gemini", gemini_client, GEMINI_CHAT_MODEL))
            providers.append(("mistral", client, CHAT_MODEL))
            if openai_client:
                providers.append(("openai", openai_client, OPENAI_CHAT_MODEL))

            wait = RATE_LIMIT_WAIT
            for rl in range(10):
                interruptible_sleep(wait, f"\n  Esperando {wait}s... (intento {rl+1})")
                if _INTERRUPTED:
                    raise KeyboardInterrupt
                wait = min(wait * 2, 120)

                prov_name, prov_client, prov_model = providers[rl % len(providers)]
                result, err = _try_provider(prov_client, prov_model, messages, provider_name=prov_name)
                if result:
                    print(f"\n  ✅ Recuperado con {prov_name}", end="")
                    return result, prov_name
            raise

        # Error de conexión → reintentar con todos los proveedores
        if "ConnectError" in err_type or "getaddrinfo" in err_msg or \
           "APIConnectionError" in err_type or "ReadError" in err_type or \
           "WinError 10054" in err_msg or "APITimeoutError" in err_type:
            # Ollama no depende de red, intentarlo primero
            if ollama_client:
                result, err = _try_provider(ollama_client, OLLAMA_CHAT_MODEL, messages, provider_name="ollama")
                if result:
                    return result, "ollama"

            wait = RECONNECT_WAIT
            for rc in range(MAX_RECONNECT_RETRIES):
                interruptible_sleep(wait, f"\n  Error de conexión, reintentando en {wait}s "
                    f"({rc+1}/{MAX_RECONNECT_RETRIES})...")
                if _INTERRUPTED:
                    raise KeyboardInterrupt
                wait = min(wait * 2, 120)

                # Intentar proveedores en orden: Ollama, Mistral, Groq, Gemini, OpenAI
                for prov_name, prov_client, prov_model in [
                    ("ollama", ollama_client, OLLAMA_CHAT_MODEL) if ollama_client else None,
                    ("mistral", client, CHAT_MODEL),
                    ("groq", groq_client, GROQ_CHAT_MODEL) if groq_client else None,
                    ("gemini", gemini_client, GEMINI_CHAT_MODEL) if gemini_client else None,
                    ("openai", openai_client, OPENAI_CHAT_MODEL) if openai_client else None,
                ]:
                    if prov_client is None:
                        continue
                    result, err = _try_provider(prov_client, prov_model, messages, provider_name=prov_name)
                    if result:
                        return result, prov_name
            raise

        raise


def progress_bar(current: int, total: int, start_time: float, width: int = 30):
    pct = current / total * 100 if total else 0
    filled = int(width * current / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    elapsed = time.time() - start_time
    eta = elapsed / current * (total - current) if current > 0 else 0
    sys.stdout.write(
        f"\r  |{bar}| {current}/{total} ({pct:.1f}%) "
        f"elapsed: {fmt_time(elapsed)} eta: {fmt_time(eta)}"
    )
    sys.stdout.flush()


# ──────────────────────────────────────────────
# 1. RESÚMENES EJECUTIVOS
# ──────────────────────────────────────────────

def generar_resumenes(conn, client):
    """Genera resumen ejecutivo de cada procedimiento con Mistral (+ fallback OpenAI)."""
    # Crear tabla
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resumenes (
            codigo TEXT PRIMARY KEY,
            resumen TEXT,
            palabras_clave TEXT,
            proposito TEXT,
            alcance TEXT,
            generado TEXT
        )
    """)
    conn.commit()

    # Inicializar Ollama (primario) + fallbacks cloud
    ollama_client = _get_ollama_client()
    openai_client = _get_openai_client()
    groq_client = _get_groq_client()
    gemini_client = _get_gemini_client()
    if ollama_client:
        print(f"  ✅ LLM primario: Ollama ({OLLAMA_CHAT_MODEL}) [local, sin rate limit]")
    else:
        print("  ⚠ Ollama no disponible (instalar con: ollama pull qwen2.5:7b)")
    if groq_client:
        print(f"  ✅ Fallback Groq disponible ({GROQ_CHAT_MODEL}) [cloud, rápido]")
    else:
        print("  ⚠ Sin GROQ_API_KEY - fallback Groq no disponible")
    if gemini_client:
        print(f"  ✅ Fallback Gemini disponible ({GEMINI_CHAT_MODEL}) [cloud, rápido]")
    else:
        print("  ⚠ Sin GEMINI_API_KEY - fallback Gemini no disponible")
    if openai_client:
        print(f"  ✅ Fallback OpenAI disponible ({OPENAI_CHAT_MODEL}) [cloud, puede estar bloqueado]")
    else:
        print("  ⚠ Sin OPENAI_API_KEY - fallback OpenAI no disponible")

    # Contar pendientes
    total = conn.execute("SELECT COUNT(*) FROM procedimientos WHERE texto_length > 100").fetchone()[0]
    ya = conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
    pendientes = total - ya

    print(f"\n  Documentos con texto: {total}")
    print(f"  Ya con resumen:       {ya}")
    print(f"  Pendientes:           {pendientes}")

    if pendientes <= 0:
        print("  Todos los resúmenes ya están generados.")
        return

    primario = OLLAMA_CHAT_MODEL if ollama_client else CHAT_MODEL
    print(f"\n  Generando resúmenes con {primario} (primario)...\n")

    start_time = time.time()
    processed = 0
    consecutive_rate_limits = 0
    force_openai = False
    force_groq = False
    force_gemini = False
    force_ollama = False

    while True:
        rows = conn.execute("""
            SELECT p.codigo, p.nombre, p.proceso_nom, p.contenido_texto
            FROM procedimientos p
            WHERE p.texto_length > 100
              AND p.codigo NOT IN (SELECT codigo FROM resumenes)
            LIMIT ?
        """, (BATCH_SIZE,)).fetchall()

        if not rows:
            break

        for codigo, nombre, proceso, texto in rows:
          try:
            try:
                prompt = (
                    f"Analiza el siguiente documento de calidad de una empresa de logística farmacéutica.\n"
                    f"Genera un resumen ejecutivo en español con:\n"
                    f"1. RESUMEN: 2-3 líneas describiendo qué hace el documento\n"
                    f"2. PROPOSITO: 1 línea sobre el objetivo\n"
                    f"3. ALCANCE: 1 línea sobre qué procesos/áreas cubre\n"
                    f"4. PALABRAS_CLAVE: 5 términos separados por coma\n\n"
                    f"Documento: {codigo} - {nombre}\n"
                    f"Proceso: {proceso}\n"
                    f"Contenido:\n{(texto or '')[:MAX_TEXT]}\n\n"
                    f"Responde en formato:\n"
                    f"RESUMEN: ...\nPROPOSITO: ...\nALCANCE: ...\nPALABRAS_CLAVE: ..."
                )

                system_msg = "Eres un experto en gestión de calidad. Genera resúmenes concisos y precisos en español."

                respuesta, modelo = llm_chat(
                    client, prompt, system_msg,
                    openai_client=openai_client,
                    groq_client=groq_client,
                    gemini_client=gemini_client,
                    ollama_client=ollama_client,
                    use_openai=force_openai,
                    use_groq=force_groq,
                    use_gemini=force_gemini,
                    use_ollama=force_ollama,
                )

                # Reset rate limit counter si tuvo éxito
                if modelo in ("mistral", "openai", "groq", "gemini", "ollama"):
                    if consecutive_rate_limits > 0:
                        print(f"\n  ✅ Rate limit recuperado (proveedor: {modelo})", end="")
                    consecutive_rate_limits = 0
                    force_openai = False
                    force_groq = False
                    force_gemini = False
                    force_ollama = False

                # Parsear respuesta
                resumen = ""
                proposito = ""
                alcance = ""
                palabras_clave = ""

                for linea in respuesta.split("\n"):
                    linea = linea.strip()
                    if linea.upper().startswith("RESUMEN:"):
                        resumen = linea.split(":", 1)[1].strip()
                    elif linea.upper().startswith("PROPOSITO:"):
                        proposito = linea.split(":", 1)[1].strip()
                    elif linea.upper().startswith("ALCANCE:"):
                        alcance = linea.split(":", 1)[1].strip()
                    elif linea.upper().startswith("PALABRAS_CLAVE:"):
                        palabras_clave = linea.split(":", 1)[1].strip()

                conn.execute("""
                    INSERT OR REPLACE INTO resumenes
                    (codigo, resumen, palabras_clave, proposito, alcance, generado)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    codigo, resumen, palabras_clave, proposito, alcance,
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                ))
                conn.commit()

            except KeyboardInterrupt:
                total_res = conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
                print(f"\n\n  ⏹ Interrupción detectada (Ctrl+C)")
                print(f"  ✅ Progreso guardado: {total_res} resúmenes en SQLite")
                print(f"  📊 Procesados: {processed} de {pendientes}")
                print(f"  💡 Ejecuta el script nuevamente para continuar desde donde quedó.")
                conn.commit()
                conn.close()
                return
            except Exception as e:
                err_str = str(e)
                err_type_name = type(e).__name__
                print(f"\n  Error en {codigo}: {err_type_name}: {err_str[:120]}")
                if "429" in err_str or "rate" in err_str.lower():
                    consecutive_rate_limits += 1
                    # Con Ollama como primario, los rate limits solo vienen de las nubes
                    # Escalar: 3 → forzar Ollama (local, siempre disponible)
                    if consecutive_rate_limits >= 3 and ollama_client:
                        print(f"  ⚠ {consecutive_rate_limits} rate limits. Forzando Ollama (local)...")
                        force_ollama = True
                        force_groq = False
                        force_gemini = False
                        force_openai = False
                    elif consecutive_rate_limits >= 6 and groq_client:
                        print(f"  ⚠ {consecutive_rate_limits} rate limits. Forzando Groq...")
                        force_groq = True
                        force_ollama = False
                        force_gemini = False
                        force_openai = False
                    elif consecutive_rate_limits >= 9 and gemini_client:
                        print(f"  ⚠ {consecutive_rate_limits} rate limits. Forzando Gemini...")
                        force_gemini = True
                        force_ollama = False
                        force_groq = False
                        force_openai = False
                    # Backoff escalado: 10s, 20s, 30s, 40s, 50s, 60s max
                    wait = min(10 * consecutive_rate_limits, 60)
                    interruptible_sleep(wait, f"  Esperando {wait}s por rate limit (intento {consecutive_rate_limits})...")
                    if _INTERRUPTED:
                        total_res = conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
                        print(f"\n\n  ⏹ Interrupción detectada (Ctrl+C)")
                        print(f"  ✅ Progreso guardado: {total_res} resúmenes en SQLite")
                        print(f"  💡 Ejecuta el script nuevamente para continuar.")
                        conn.commit()
                        conn.close()
                        return
                    continue
                elif "ConnectError" in err_type_name or "APIConnectionError" in err_type_name or \
                     "ReadError" in err_type_name or "WinError 10054" in err_str:
                    interruptible_sleep(30, "  Error de conexión, esperando 30s...")
                    if _INTERRUPTED:
                        total_res = conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
                        print(f"\n\n  ⏹ Interrupción detectada (Ctrl+C)")
                        print(f"  ✅ Progreso guardado: {total_res} resúmenes en SQLite")
                        print(f"  💡 Ejecuta el script nuevamente para continuar.")
                        conn.commit()
                        conn.close()
                        return
                    continue

            processed += 1
            progress_bar(processed, pendientes, start_time)
            # Pausa adaptativa: más lento si hay rate limits recientes
            pause = 0.5 if consecutive_rate_limits == 0 else min(2.0 * consecutive_rate_limits, 5.0)
            interruptible_sleep(pause)

            # Verificar si el usuario presionó Ctrl+C
            if _INTERRUPTED:
                total_res = conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
                print(f"\n\n  ⏹ Interrupción detectada (Ctrl+C)")
                print(f"  ✅ Progreso guardado: {total_res} resúmenes en SQLite")
                print(f"  📊 Faltaron: {pendientes - processed} documentos")
                print(f"  💡 Ejecuta el script nuevamente para continuar desde donde quedó.")
                conn.commit()
                conn.close()
                return
          except KeyboardInterrupt:
            total_res = conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
            print(f"\n\n  ⏹ Interrupción detectada (Ctrl+C)")
            print(f"  ✅ Progreso guardado: {total_res} resúmenes en SQLite")
            print(f"  💡 Ejecuta el script nuevamente para continuar.")
            conn.commit()
            conn.close()
            return

    elapsed = time.time() - start_time
    total_res = conn.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
    print(f"\n\n  Resúmenes generados: {total_res} en {fmt_time(elapsed)}")


# ──────────────────────────────────────────────
# 2. TABLA JERÁRQUICA DE CONTENIDO
# ──────────────────────────────────────────────

def construir_tabla_jerarquica(conn):
    """Construye una tabla de contenido jerárquica:
    Proceso → Tipo → Procedimiento → Versión
    """
    print("\n  Construyendo tabla jerárquica...")

    rows = conn.execute("""
        SELECT
            TRIM(proceso_cod) as proc_cod,
            TRIM(proceso_nom) as proc_nom,
            TRIM(tipo_documento) as tipo,
            TRIM(codigo) as codigo,
            TRIM(nombre) as nombre,
            estado,
            estado_desc,
            fecha_publicacion,
            vigencia_dias
        FROM procedimientos
        WHERE codigo IS NOT NULL
        ORDER BY proc_nom, tipo, codigo
    """).fetchall()

    jerarquia = {}
    for r in rows:
        proc_cod, proc_nom, tipo, codigo, nombre, estado, estado_desc, fecha_pub, vigencia = r
        proc_key = proc_cod or "SIN_PROCESO"
        proc_nom = proc_nom or "Sin proceso"
        tipo = tipo or "Sin tipo"

        if proc_key not in jerarquia:
            jerarquia[proc_key] = {
                "codigo": proc_cod,
                "nombre": proc_nom,
                "tipos": {},
                "total_docs": 0,
            }

        if tipo not in jerarquia[proc_key]["tipos"]:
            jerarquia[proc_key]["tipos"][tipo] = {
                "nombre": tipo,
                "documentos": [],
                "total": 0,
            }

        jerarquia[proc_key]["tipos"][tipo]["documentos"].append({
            "codigo": codigo,
            "nombre": nombre,
            "estado": estado,
            "estado_desc": estado_desc,
            "fecha_publicacion": fecha_pub,
            "vigencia_dias": vigencia,
        })
        jerarquia[proc_key]["tipos"][tipo]["total"] += 1
        jerarquia[proc_key]["total_docs"] += 1

    # Guardar en SQLite
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tabla_jerarquica (
            proceso_cod TEXT,
            proceso_nom TEXT,
            tipo_documento TEXT,
            codigo TEXT,
            nombre TEXT,
            estado TEXT,
            estado_desc TEXT,
            fecha_publicacion TEXT,
            vigencia_dias INTEGER,
            nivel INTEGER,
            PRIMARY KEY (proceso_cod, tipo_documento, codigo)
        )
    """)
    conn.execute("DELETE FROM tabla_jerarquica")

    batch = []
    for proc_key, proc_data in jerarquia.items():
        # Nivel 1: proceso
        batch.append((
            proc_data["codigo"] or proc_key, proc_data["nombre"],
            None, None, None, None, None, None, None, 1
        ))
        for tipo, tipo_data in proc_data["tipos"].items():
            # Nivel 2: tipo
            batch.append((
                proc_data["codigo"] or proc_key, proc_data["nombre"],
                tipo, None, None, None, None, None, None, 2
            ))
            for doc in tipo_data["documentos"]:
                # Nivel 3: documento
                batch.append((
                    proc_data["codigo"] or proc_key, proc_data["nombre"],
                    tipo, doc["codigo"], doc["nombre"],
                    doc["estado"], doc["estado_desc"],
                    doc["fecha_publicacion"], doc["vigencia_dias"], 3
                ))

    conn.executemany("""
        INSERT OR REPLACE INTO tabla_jerarquica
        (proceso_cod, proceso_nom, tipo_documento, codigo, nombre,
         estado, estado_desc, fecha_publicacion, vigencia_dias, nivel)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, batch)
    conn.commit()

    # Guardar JSON para visualización
    jerarquia_path = Path(__file__).parent.parent / "tabla_jerarquica.json"
    jerarquia_path.write_text(
        json.dumps(jerarquia, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    total_procs = len(jerarquia)
    total_tipos = sum(len(p["tipos"]) for p in jerarquia.values())
    total_docs = sum(p["total_docs"] for p in jerarquia.values())

    print(f"  Tabla jerárquica: {total_procs} procesos, {total_tipos} tipos, {total_docs} documentos")
    print(f"  Guardada en: {jerarquia_path}")

    # Mostrar resumen
    print(f"\n  Estructura jerárquica:")
    for proc_key, proc_data in sorted(jerarquia.items(), key=lambda x: -x[1]["total_docs"]):
        print(f"    📁 {proc_data['nombre']} ({proc_data['total_docs']} docs)")
        for tipo, tipo_data in sorted(proc_data["tipos"].items(), key=lambda x: -x[1]["total"]):
            print(f"       📄 {tipo} ({tipo_data['total']})")


# ──────────────────────────────────────────────
# 3. ALERTAS DE VENCIMIENTO
# ──────────────────────────────────────────────

def detectar_vencimientos(conn):
    """Detecta documentos publicados que están por vencer o ya vencieron."""
    print("\n  Detectando documentos vencidos/por vencer...")

    rows = conn.execute("""
        SELECT
            TRIM(codigo),
            TRIM(nombre),
            estado,
            estado_desc,
            fecha_publicacion,
            vigencia_dias,
            TRIM(proceso_nom)
        FROM procedimientos
        WHERE estado = 'P'
          AND fecha_publicacion IS NOT NULL
          AND vigencia_dias IS NOT NULL
          AND vigencia_dias > 0
    """).fetchall()

    hoy = datetime.now()
    vencidos = []
    por_vencer_30 = []
    por_vencer_90 = []
    vigentes = []

    for codigo, nombre, estado, estado_desc, fecha_pub, vigencia, proceso in rows:
        try:
            # Parsear fecha (formato SQL Server)
            fecha_str = str(fecha_pub).split(".")[0].strip()
            fecha_pub_dt = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            try:
                fecha_pub_dt = datetime.strptime(str(fecha_pub)[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                continue

        fecha_vencimiento = fecha_pub_dt + timedelta(days=int(vigencia or 0))
        dias_restantes = (fecha_vencimiento - hoy).days

        doc_info = {
            "codigo": codigo,
            "nombre": nombre,
            "proceso": proceso,
            "fecha_publicacion": str(fecha_pub),
            "vigencia_dias": vigencia,
            "fecha_vencimiento": fecha_vencimiento.strftime("%Y-%m-%d"),
            "dias_restantes": dias_restantes,
        }

        if dias_restantes < 0:
            vencidos.append(doc_info)
        elif dias_restantes <= 30:
            por_vencer_30.append(doc_info)
        elif dias_restantes <= 90:
            por_vencer_90.append(doc_info)
        else:
            vigentes.append(doc_info)

    # Guardar en SQLite
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alertas_vencimiento (
            codigo TEXT PRIMARY KEY,
            nombre TEXT,
            proceso TEXT,
            fecha_publicacion TEXT,
            vigencia_dias INTEGER,
            fecha_vencimiento TEXT,
            dias_restantes INTEGER,
            estado_alerta TEXT
        )
    """)
    conn.execute("DELETE FROM alertas_vencimiento")

    batch = []
    for doc in vencidos:
        batch.append((doc["codigo"], doc["nombre"], doc["proceso"],
                      doc["fecha_publicacion"], doc["vigencia_dias"],
                      doc["fecha_vencimiento"], doc["dias_restantes"], "VENCIDO"))
    for doc in por_vencer_30:
        batch.append((doc["codigo"], doc["nombre"], doc["proceso"],
                      doc["fecha_publicacion"], doc["vigencia_dias"],
                      doc["fecha_vencimiento"], doc["dias_restantes"], "POR_VENCER_30"))
    for doc in por_vencer_90:
        batch.append((doc["codigo"], doc["nombre"], doc["proceso"],
                      doc["fecha_publicacion"], doc["vigencia_dias"],
                      doc["fecha_vencimiento"], doc["dias_restantes"], "POR_VENCER_90"))
    for doc in vigentes:
        batch.append((doc["codigo"], doc["nombre"], doc["proceso"],
                      doc["fecha_publicacion"], doc["vigencia_dias"],
                      doc["fecha_vencimiento"], doc["dias_restantes"], "VIGENTE"))

    conn.executemany("""
        INSERT OR REPLACE INTO alertas_vencimiento
        (codigo, nombre, proceso, fecha_publicacion, vigencia_dias,
         fecha_vencimiento, dias_restantes, estado_alerta)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, batch)
    conn.commit()

    # Reporte
    print(f"\n  {'='*50}")
    print(f"  ALERTAS DE VENCIMIENTO")
    print(f"  {'='*50}")
    print(f"  🔴 Vencidos:           {len(vencidos)}")
    print(f"  🟡 Por vencer (30 días): {len(por_vencer_30)}")
    print(f"  🟠 Por vencer (90 días): {len(por_vencer_90)}")
    print(f"  🟢 Vigentes:           {len(vigentes)}")

    if vencidos:
        print(f"\n  🔴 TOP 10 documentos VENCIDOS:")
        for doc in sorted(vencidos, key=lambda x: x["dias_restantes"])[:10]:
            print(f"    {doc['codigo']} | venció {doc['fecha_vencimiento']} ({abs(doc['dias_restantes'])} días) | {doc['nombre'][:40]}")

    if por_vencer_30:
        print(f"\n  🟡 Documentos por vencer en 30 días:")
        for doc in sorted(por_vencer_30, key=lambda x: x["dias_restantes"])[:10]:
            print(f"    {doc['codigo']} | vence {doc['fecha_vencimiento']} ({doc['dias_restantes']} días) | {doc['nombre'][:40]}")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  GENERADOR DE RESÚMENES + TABLA JERÁRQUICA + ALERTAS")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))

    # 1. Tabla jerárquica (no necesita Mistral)
    print("\n[1/3] Tabla jerárquica de contenido...")
    construir_tabla_jerarquica(conn)

    # 2. Alertas de vencimiento (no necesita Mistral)
    print("\n[2/3] Alertas de vencimiento...")
    detectar_vencimientos(conn)

    # 3. Resúmenes ejecutivos (necesita Mistral)
    print("\n[3/3] Resúmenes ejecutivos...")
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("  ⚠ Sin MISTRAL_API_KEY, saltando resúmenes ejecutivos.")
        print("  Ejecuta después con MISTRAL_API_KEY para generar resúmenes.")
    else:
        client = OpenAI(base_url=MISTRAL_BASE_URL, api_key=api_key)
        generar_resumenes(conn, client)

    print(f"\n{'='*60}")
    print(f"  COMPLETADO")
    print(f"{'='*60}")
    print(f"  Tabla jerárquica:  tabla_jerarquica (SQLite + JSON)")
    print(f"  Alertas:           alertas_vencimiento (SQLite)")
    print(f"  Resúmenes:         resumenes (SQLite)")
    conn.close()


if __name__ == "__main__":
    main()
