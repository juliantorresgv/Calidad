"""
Paso 2 (v2): Genera embeddings con Mistral y los almacena en:
  - ChromaDB (base vectorial con metadata + persistencia automática)
  - FAISS (índice ultra rápido para búsqueda)
  - SQLite (respaldo)

Estrategia de lotes progresivos: 50 → 40 → 30 → 20 → 10 → 5 → 1
Manejo de rate limiting (429) con backoff exponencial.

Uso:
    $env:INTEGRA_DB_SERVER="10.238.66.14"
    $env:MISTRAL_API_KEY="<tu_api_key>"
    python Codigo/generate_embeddings.py
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

import faiss
import numpy as np
from openai import OpenAI

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ──────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"
CHROMA_PATH = Path(__file__).parent.parent / "chroma_db"
FAISS_PATH = Path(__file__).parent.parent / "faiss_index.bin"

MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
EMBED_MODEL = "mistral-embed"
EMBED_DIM = 1024  # dimensión de mistral-embed

# ─── OpenAI como fallback ───
# OpenAI text-embedding-3-small soporta parámetro `dimensions`
# Usamos dimensions=1024 para que sea compatible con mistral-embed
OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_EMBED_DIM = 1024  # forzamos 1024 para compatibilidad con Mistral

BATCH_LEVELS = [50, 40, 30, 20, 10, 5, 1]
MAX_RETRIES = 3
RATE_LIMIT_WAIT = 10
FAISS_SAVE_EVERY = 100  # guardar FAISS cada 100 documentos

# Límite de tokens de mistral-embed y text-embedding-3-small (ambos 8192)
MAX_TOKENS = 8000  # margen seguro bajo 8192
MAX_CHARS = 30000  # fallback si tiktoken no está disponible
MAX_RECONNECT_RETRIES = 5  # reintentos por error de conexión
RECONNECT_WAIT = 30  # segundos entre reintentos de conexión

# Cuántos rate limits consecutivos tolerar antes de cambiar a OpenAI
RATE_LIMIT_THRESHOLD = 3

# Cache del encoder tiktoken
_TIKTOKEN_ENCODER = None


def _get_encoder():
    """Obtiene el encoder de tiktoken (cacheado)."""
    global _TIKTOKEN_ENCODER
    if _TIKTOKEN_ENCODER is None:
        try:
            import tiktoken
            _TIKTOKEN_ENCODER = tiktoken.encoding_for_model("text-embedding-3-small")
        except Exception:
            _TIKTOKEN_ENCODER = False  # no disponible
    return _TIKTOKEN_ENCODER


# ──────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────

def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def progress_bar(current: int, total: int, start_time: float, width: int = 30):
    pct = current / total * 100 if total else 0
    filled = int(width * current / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    elapsed = time.time() - start_time
    if current > 0:
        eta = elapsed / current * (total - current)
    else:
        eta = 0
    sys.stdout.write(
        f"\r  |{bar}| {current}/{total} ({pct:.1f}%) "
        f"elapsed: {fmt_time(elapsed)} eta: {fmt_time(eta)}"
    )
    sys.stdout.flush()


# ──────────────────────────────────────────────
# ChromaDB
# ──────────────────────────────────────────────

def init_chroma():
    """Inicializa ChromaDB con persistencia local."""
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    # Crear o obtener colección
    collection = client.get_or_create_collection(
        name="procedimientos",
        metadata={"description": "Procedimientos de Integra con embeddings Mistral"},
    )
    return client, collection


# ──────────────────────────────────────────────
# FAISS
# ──────────────────────────────────────────────

class FAISSIndex:
    """Índice FAISS para búsqueda ultra rápida."""

    def __init__(self, dim: int = EMBED_DIM):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)  # producto interno (con normalización = coseno)
        self.codigos: list[str] = []

    def add(self, codigo: str, embedding: np.ndarray):
        vec = embedding.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(vec)  # normalizar para similitud coseno
        self.index.add(vec)
        self.codigos.append(codigo)

    def search(self, query_emb: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
        if self.index.ntotal == 0:
            return []
        vec = query_emb.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(vec)
        scores, indices = self.index.search(vec, min(top_k, self.index.ntotal))
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(self.codigos):
                results.append((self.codigos[idx], float(scores[0][i])))
        return results

    def save(self, path: Path):
        faiss.write_index(self.index, str(path))
        # Guardar mapeo de códigos
        meta_path = path.with_suffix(".meta.json")
        import json
        meta_path.write_text(json.dumps(self.codigos), encoding="utf-8")

    def load(self, path: Path):
        self.index = faiss.read_index(str(path))
        import json
        meta_path = path.with_suffix(".meta.json")
        if meta_path.exists():
            self.codigos = json.loads(meta_path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────
# Generación de embeddings con fallback Mistral → OpenAI
# ──────────────────────────────────────────────

def truncate_text(texto: str, max_tokens: int = MAX_TOKENS) -> str:
    """Trunca el texto para no exceder el límite de tokens (8192).
    Usa tiktoken para contar tokens reales. Fallback a chars si no disponible.
    """
    if not texto:
        return texto

    encoder = _get_encoder()
    if encoder:
        tokens = encoder.encode(texto)
        if len(tokens) <= max_tokens:
            return texto
        # Truncar a max_tokens y decodificar de vuelta
        truncated = encoder.decode(tokens[:max_tokens])
        return truncated
    else:
        # Fallback: aproximación por caracteres
        max_chars = max_tokens * 3  # ~3 chars/token en español
        if len(texto) > max_chars:
            return texto[:max_chars]
        return texto


def _get_openai_client():
    """Inicializa cliente OpenAI si hay API key disponible."""
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        return None
    try:
        from openai import OpenAI as OpenAIClient
        return OpenAIClient(api_key=openai_key)
    except Exception:
        return None


def embed_batch_openai(openai_client, textos: list[str], batch_size: int):
    """Genera embeddings con OpenAI text-embedding-3-small (dimensions=1024)."""
    textos_trunc = [truncate_text(t) for t in textos[:batch_size]]
    try:
        resp = openai_client.embeddings.create(
            model=OPENAI_EMBED_MODEL,
            input=textos_trunc,
            dimensions=OPENAI_EMBED_DIM,
        )
        return resp.data
    except Exception as e:
        err_msg = str(e)
        if "Too many tokens" in err_msg or "maximum context length" in err_msg:
            return None
        raise


def embed_single_openai(openai_client, texto: str):
    """Genera embedding individual con OpenAI (fallback)."""
    texto = truncate_text(texto)
    try:
        resp = openai_client.embeddings.create(
            model=OPENAI_EMBED_MODEL,
            input=[texto],
            dimensions=OPENAI_EMBED_DIM,
        )
        return resp.data[0]
    except Exception:
        return None


def embed_batch(client, textos: list[str], batch_size: int,
                openai_client=None, use_openai: bool = False):
    """Intenta generar embeddings para un sub-lote.
    Retorna (data, model_used) donde model_used es 'mistral' o 'openai'.
    Retorna (None, model) si el lote es muy grande (para reducir tamaño).
    """
    textos_trunc = [truncate_text(t) for t in textos[:batch_size]]

    # Si ya estamos en modo OpenAI (rate limit persistente en Mistral)
    if use_openai and openai_client:
        data = embed_batch_openai(openai_client, textos, batch_size)
        return (data, "openai") if data else (None, "openai")

    try:
        resp = client.embeddings.create(model=EMBED_MODEL, input=textos_trunc)
        return (resp.data, "mistral")
    except Exception as e:
        err_msg = str(e)
        err_type = type(e).__name__

        # Error de tokens → reducir lote
        if "Too many tokens" in err_msg or "3210" in err_msg or "exceeding max" in err_msg:
            return (None, "mistral")

        # Rate limit (429) → intentar OpenAI como fallback primero
        if "429" in err_msg or "rate" in err_msg.lower():
            if openai_client:
                print(f"\n  ⚡ Rate limit Mistral → fallback OpenAI...", end="")
                try:
                    data = embed_batch_openai(openai_client, textos, batch_size)
                    if data:
                        return (data, "openai")
                except Exception:
                    pass
            # Si no hay OpenAI o falló, manejar rate limit normal con backoff
            wait = RATE_LIMIT_WAIT
            for rl in range(MAX_RETRIES):
                print(f"\n  Rate limit (429) en lote, esperando {wait}s...", end="")
                time.sleep(wait)
                wait *= 2
                try:
                    resp = client.embeddings.create(model=EMBED_MODEL, input=textos_trunc)
                    return (resp.data, "mistral")
                except Exception:
                    continue
            return (None, "mistral")

        # Error de conexión → reintentar con backoff
        if "ConnectError" in err_type or "getaddrinfo" in err_msg or \
           "Connection error" in err_msg or "APITimeoutError" in err_type or \
           "APIConnectionError" in err_type:
            wait = RECONNECT_WAIT
            for reconnect in range(MAX_RECONNECT_RETRIES):
                print(f"\n  Error de conexión en lote, reintentando en {wait}s "
                      f"(intento {reconnect + 1}/{MAX_RECONNECT_RETRIES})...", end="")
                time.sleep(wait)
                wait = min(wait * 2, 120)
                try:
                    resp = client.embeddings.create(model=EMBED_MODEL, input=textos_trunc)
                    return (resp.data, "mistral")
                except Exception as e2:
                    err2_type = type(e2).__name__
                    if "ConnectError" in err2_type or "APIConnectionError" in err2_type:
                        continue
                    raise
            raise

        raise


def embed_single(client, texto: str, max_retries: int = MAX_RETRIES,
                 openai_client=None, use_openai: bool = False):
    """Genera embedding de un documento con reintentos y fallback a OpenAI."""
    texto = truncate_text(texto)
    wait = RATE_LIMIT_WAIT
    reconnect_wait = RECONNECT_WAIT

    # Si ya estamos en modo OpenAI
    if use_openai and openai_client:
        return embed_single_openai(openai_client, texto)

    for attempt in range(max_retries + MAX_RECONNECT_RETRIES):
        try:
            resp = client.embeddings.create(model=EMBED_MODEL, input=[texto])
            return resp.data[0]
        except Exception as e:
            err_msg = str(e)
            err_type = type(e).__name__

            # Rate limiting (429) → fallback OpenAI o backoff
            if "429" in err_msg or "rate" in err_msg.lower():
                if openai_client:
                    print(f"\n  ⚡ Rate limit Mistral → fallback OpenAI (single)...", end="")
                    result = embed_single_openai(openai_client, texto)
                    if result:
                        return result
                print(f"\n  Rate limit (429), esperando {wait}s...", end="")
                time.sleep(wait)
                wait *= 2
                continue

            # Error de conexión (DNS, timeout, red)
            if "ConnectError" in err_type or "getaddrinfo" in err_msg or \
               "Connection error" in err_msg or "APITimeoutError" in err_type or \
               "APIConnectionError" in err_type:
                print(f"\n  Error de conexión, reintentando en {reconnect_wait}s "
                      f"(intento {attempt + 1}/{MAX_RECONNECT_RETRIES})...", end="")
                time.sleep(reconnect_wait)
                reconnect_wait = min(reconnect_wait * 2, 120)
                continue

            # Error de tokens (documento demasiado grande)
            if "exceeding max" in err_msg or "3210" in err_msg:
                # Truncar más agresivamente
                texto = texto[:MAX_CHARS // 2]
                print(f"\n  Documento muy largo, truncando a {len(texto)} chars...", end="")
                continue

            # Otro error
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                print(f"\n  Error final: {err_type}: {err_msg[:100]}")
                return None
    return None


def _sync_chroma_from_sqlite(conn, collection, faiss_idx):
    """Sincroniza ChromaDB con los embeddings que ya están en SQLite pero no en Chroma."""
    import pickle
    # Obtener códigos que están en SQLite pero no en ChromaDB
    chroma_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()
    rows = conn.execute("""
        SELECT e.codigo, e.embedding, p.nombre, p.estado, p.estado_desc,
               p.proceso_cod, p.proceso_nom, p.tipo_documento,
               p.fecha_publicacion, p.elaborador, p.contenido_texto
        FROM embeddings e
        JOIN procedimientos p ON e.codigo = p.codigo
        WHERE e.codigo NOT IN ({})
    """.format(",".join(["?"] * len(chroma_ids)) if chroma_ids else "SELECT ''"),
    list(chroma_ids) if chroma_ids else []).fetchall() if chroma_ids else conn.execute("""
        SELECT e.codigo, e.embedding, p.nombre, p.estado, p.estado_desc,
               p.proceso_cod, p.proceso_nom, p.tipo_documento,
               p.fecha_publicacion, p.elaborador, p.contenido_texto
        FROM embeddings e
        JOIN procedimientos p ON e.codigo = p.codigo
    """).fetchall()

    synced = 0
    for row in rows:
        codigo, emb_blob, nombre, estado, estado_desc, proceso_cod, proceso_nom, \
            tipo_documento, fecha_publicacion, elaborador, contenido_texto = row
        emb = pickle.loads(emb_blob)
        meta = {
            "nombre": (nombre or "")[:200],
            "estado": estado or "",
            "estado_desc": estado_desc or "",
            "proceso_cod": proceso_cod or "",
            "proceso_nom": (proceso_nom or "")[:100],
            "tipo_documento": tipo_documento or "",
            "fecha_publicacion": fecha_publicacion or "",
            "elaborador": (elaborador or "")[:100],
        }
        collection.upsert(
            ids=[codigo],
            embeddings=[emb if isinstance(emb, list) else emb.tolist()],
            documents=[(contenido_texto or "")[:4000]],
            metadatas=[meta],
        )
        # También agregar a FAISS si no está
        emb_np = np.array(emb)
        faiss_idx.add(codigo, emb_np)
        synced += 1
        if synced % 100 == 0:
            print(f"    Sincronizados {synced}...", end="")
    faiss_idx.save(FAISS_PATH)
    print(f"\n  ✅ {synced} documentos sincronizados en ChromaDB + FAISS")


def _rebuild_faiss_from_sqlite(conn, faiss_idx):
    """Reconstruye el indice FAISS desde los embeddings en SQLite.
    Modifica el objeto faiss_idx in-place (limpia y rellena).
    """
    import pickle
    rows = conn.execute("SELECT codigo, embedding FROM embeddings").fetchall()
    # Limpiar el indice existente in-place en vez de crear variable local
    faiss_idx.index = faiss.IndexFlatIP(EMBED_DIM)
    faiss_idx.codigos = []
    rebuilt = 0
    for codigo, emb_blob in rows:
        emb = pickle.loads(emb_blob)
        emb_np = np.array(emb)
        faiss_idx.add(codigo, emb_np)
        rebuilt += 1
        if rebuilt % 500 == 0:
            print(f"    Reconstruidos {rebuilt}...", end="")
    faiss_idx.save(FAISS_PATH)
    print(f"\n  ✅ FAISS reconstruido con {rebuilt} vectores")


def main():
    print("=" * 60)
    print("  GENERADOR DE EMBEDDINGS - MISTRAL (+ fallback OpenAI)")
    print("  Almacenamiento: ChromaDB + FAISS + SQLite")
    print("  Lotes progresivos: 50 → 40 → 30 → 20 → 10 → 5 → 1")
    print("=" * 60)

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("ERROR: Define MISTRAL_API_KEY")
        sys.exit(1)

    client = OpenAI(base_url=MISTRAL_BASE_URL, api_key=api_key)

    # Inicializar cliente OpenAI como fallback
    openai_client = _get_openai_client()
    if openai_client:
        print("  ✅ Fallback OpenAI disponible (text-embedding-3-small, dim=1024)")
    else:
        print("  ⚠ Sin OPENAI_API_KEY - fallback no disponible")
        print("    Para activar fallback: $env:OPENAI_API_KEY=\"<tu_key>\"")

    # Estado de rate limiting persistente
    consecutive_rate_limits = 0
    force_openai = False

    # Conectar a SQLite
    conn = sqlite3.connect(str(DB_PATH))

    # Inicializar ChromaDB
    print("\n  Inicializando ChromaDB...")
    chroma_client, collection = init_chroma()
    existing_chroma = collection.count()
    print(f"  ChromaDB: {existing_chroma} documentos ya indexados")

    # Inicializar FAISS
    faiss_idx = FAISSIndex(dim=EMBED_DIM)
    if FAISS_PATH.exists():
        print("  Cargando índice FAISS existente...")
        faiss_idx.load(FAISS_PATH)
        print(f"  FAISS: {faiss_idx.index.ntotal} vectores cargados")

    # Contar pendientes y diagnosticar discrepancias
    total_db = conn.execute("SELECT COUNT(*) FROM procedimientos WHERE texto_length > 100").fetchone()[0]
    ya_sqlite = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    ya_chroma = collection.count()
    ya_faiss = faiss_idx.index.ntotal

    print(f"\n  Documentos con texto:  {total_db}")
    print(f"  Ya en SQLite:          {ya_sqlite}")
    print(f"  Ya en ChromaDB:        {ya_chroma}")
    print(f"  Ya en FAISS:           {ya_faiss}")

    # Detectar discrepancias (independientes, no excluyentes)
    pendientes = 0
    if ya_sqlite < total_db:
        pendientes = total_db - ya_sqlite
        print(f"  Pendientes (SQLite):   {pendientes}")

    # ChromaDB puede faltar aunque SQLite este completo
    if ya_chroma < ya_sqlite:
        pendientes_chroma = ya_sqlite - ya_chroma
        print(f"\n  ⚠ ChromaDB falta {pendientes_chroma} documentos (SQLite completo)")
        print(f"  Sincronizando ChromaDB desde SQLite...")
        _sync_chroma_from_sqlite(conn, collection, faiss_idx)
        ya_chroma = collection.count()
        ya_faiss = faiss_idx.index.ntotal  # actualizar despues de sync

    # FAISS puede faltar aunque ChromaDB este completo
    if ya_faiss < ya_sqlite:
        pendientes_faiss = ya_sqlite - ya_faiss
        print(f"\n  ⚠ FAISS falta {pendientes_faiss} vectores (SQLite completo)")
        print(f"  Reconstruyendo FAISS desde SQLite...")
        _rebuild_faiss_from_sqlite(conn, faiss_idx)
        ya_faiss = faiss_idx.index.ntotal

    if pendientes <= 0 and ya_chroma >= total_db and ya_faiss >= total_db:
        print("\n  ✅ Todos los documentos están indexados en los 3 almacenes.")
        conn.close()
        return

    print(f"\n[1/3] Generando embeddings (modelo: {EMBED_MODEL})...")
    print(f"[2/3] Guardando en ChromaDB + FAISS...")
    print(f"[3/3] Sincronizando SQLite...\n")

    start_time = time.time()
    processed = 0
    batch_size_actual = BATCH_LEVELS[0]
    rate_limit_count = 0
    saved_chroma = 0
    saved_faiss = 0

    while True:
        # Obtener documentos pendientes (no en ChromaDB)
        rows = conn.execute("""
            SELECT p.codigo, p.nombre, p.estado, p.estado_desc, p.proceso_cod,
                   p.proceso_nom, p.tipo_documento, p.contenido_texto,
                   p.fecha_publicacion, p.elaborador
            FROM procedimientos p
            WHERE p.texto_length > 100
              AND p.codigo NOT IN (SELECT codigo FROM embeddings)
            LIMIT ?
        """, (batch_size_actual,)).fetchall()

        if not rows:
            break

        codigos = [r[0] for r in rows]
        textos = [(r[7] or "") for r in rows]

        # Metadatos para ChromaDB
        metadatas = []
        for r in rows:
            meta = {
                "nombre": (r[1] or "")[:200],
                "estado": r[2] or "",
                "estado_desc": r[3] or "",
                "proceso_cod": r[4] or "",
                "proceso_nom": (r[5] or "")[:100],
                "tipo_documento": r[6] or "",
                "fecha_publicacion": r[8] or "",
                "elaborador": (r[9] or "")[:100],
            }
            metadatas.append(meta)

        # Intentar con tamaño de lote progresivo
        embeddings_data = None
        model_used = "mistral"
        for size in BATCH_LEVELS:
            if size > len(textos):
                continue
            try:
                embeddings_data, model_used = embed_batch(
                    client, textos, size,
                    openai_client=openai_client,
                    use_openai=force_openai,
                )
                if embeddings_data is not None:
                    if size < batch_size_actual:
                        print(f"\n  Lote reducido a {size}", end="")
                        batch_size_actual = size
                    # Reset rate limit counter si tuvo éxito con Mistral
                    if model_used == "mistral":
                        consecutive_rate_limits = 0
                        force_openai = False
                    break
            except Exception as e:
                err_msg = str(e)
                err_type = type(e).__name__

                # Error de conexión → pausar y reintentar
                if "ConnectError" in err_type or "getaddrinfo" in err_msg or \
                   "Connection error" in err_msg or "APIConnectionError" in err_type:
                    wait = RECONNECT_WAIT
                    reconnected = False
                    for rc in range(MAX_RECONNECT_RETRIES):
                        print(f"\n  ⚠ Error de conexión. Verifica VPN/red. "
                              f"Reintentando en {wait}s "
                              f"(intento {rc + 1}/{MAX_RECONNECT_RETRIES})...")
                        time.sleep(wait)
                        wait = min(wait * 2, 120)
                        try:
                            embeddings_data, model_used = embed_batch(
                                client, textos, size,
                                openai_client=openai_client,
                                use_openai=force_openai,
                            )
                            if embeddings_data is not None:
                                reconnected = True
                                print(f"\n  ✅ Conexión restablecida.")
                                break
                        except Exception as e2:
                            if "ConnectError" in type(e2).__name__ or \
                               "APIConnectionError" in type(e2).__name__:
                                continue
                            raise
                    if not reconnected:
                        print(f"\n  ❌ No se pudo restablecer la conexión tras "
                              f"{MAX_RECONNECT_RETRIES} intentos.")
                        print(f"  Guardando progreso y saliendo...")
                        faiss_idx.save(FAISS_PATH)
                        conn.commit()
                        conn.close()
                        print(f"  Progreso guardado. Ejecuta el script nuevamente "
                              f"para continuar desde donde quedó.")
                        sys.exit(1)
                    break

                # Rate limit (429) persistente → forzar OpenAI
                elif "429" in err_msg or "rate" in err_msg.lower():
                    rate_limit_count += 1
                    consecutive_rate_limits += 1
                    if openai_client and consecutive_rate_limits >= RATE_LIMIT_THRESHOLD:
                        print(f"\n  ⚠ {consecutive_rate_limits} rate limits consecutivos. "
                              f"Cambiando a OpenAI...")
                        force_openai = True
                        try:
                            embeddings_data, model_used = embed_batch(
                                client, textos, size,
                                openai_client=openai_client,
                                use_openai=True,
                            )
                            if embeddings_data is not None:
                                break
                        except Exception:
                            pass
                    wait = RATE_LIMIT_WAIT * (2 ** min(rate_limit_count, 4))
                    print(f"\n  Rate limit, esperando {wait}s...", end="")
                    time.sleep(wait)
                    try:
                        embeddings_data, model_used = embed_batch(
                            client, textos, size,
                            openai_client=openai_client,
                            use_openai=force_openai,
                        )
                        if embeddings_data is not None:
                            break
                    except Exception:
                        continue
                else:
                    raise

        # Si ningún lote funcionó, procesar uno a uno
        if embeddings_data is None:
            print(f"\n  Procesando uno a uno...", end="")
            for j, texto in enumerate(textos):
                emb_info = embed_single(
                    client, texto,
                    openai_client=openai_client,
                    use_openai=force_openai,
                )
                if emb_info is not None:
                    emb = np.array(emb_info.embedding)
                    # ChromaDB
                    collection.upsert(
                        ids=[codigos[j]],
                        embeddings=[emb.tolist()],
                        documents=[texto[:4000]],
                        metadatas=[metadatas[j]],
                    )
                    saved_chroma += 1
                    # FAISS
                    faiss_idx.add(codigos[j], emb)
                    saved_faiss += 1
                    # SQLite
                    import pickle
                    conn.execute("""
                        INSERT OR REPLACE INTO embeddings (codigo, embedding, modelo, creado)
                        VALUES (?, ?, ?, ?)
                    """, (codigos[j], pickle.dumps(emb.tolist()), EMBED_MODEL,
                          time.strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()

                processed += 1
                progress_bar(processed, pendientes, start_time)

                # Guardar FAISS incrementalmente
                if saved_faiss % FAISS_SAVE_EVERY == 0:
                    faiss_idx.save(FAISS_PATH)
            continue

        # Guardar lote en ChromaDB + FAISS + SQLite
        import pickle
        emb_list = []
        ids_list = []
        docs_list = []
        meta_list = []
        batch_sqlite = []

        for emb_info in embeddings_data:
            if emb_info is None:
                continue
            idx = emb_info.index if hasattr(emb_info, 'index') else 0
            if idx >= len(codigos):
                continue
            emb = np.array(emb_info.embedding)
            emb_list.append(emb.tolist())
            ids_list.append(codigos[idx])
            docs_list.append(textos[idx][:4000])
            meta_list.append(metadatas[idx])
            # FAISS
            faiss_idx.add(codigos[idx], emb)
            saved_faiss += 1
            # SQLite - guardar modelo real usado
            modelo_guardar = OPENAI_EMBED_MODEL if model_used == "openai" else EMBED_MODEL
            batch_sqlite.append((
                codigos[idx],
                pickle.dumps(emb.tolist()),
                modelo_guardar,
                time.strftime("%Y-%m-%d %H:%M:%S"),
            ))

        if emb_list:
            # ChromaDB
            collection.upsert(
                ids=ids_list,
                embeddings=emb_list,
                documents=docs_list,
                metadatas=meta_list,
            )
            saved_chroma += len(emb_list)

            # SQLite
            conn.executemany("""
                INSERT OR REPLACE INTO embeddings (codigo, embedding, modelo, creado)
                VALUES (?, ?, ?, ?)
            """, batch_sqlite)
            conn.commit()

        processed += len(emb_list)
        progress_bar(processed, pendientes, start_time)

        # Guardar FAISS incrementalmente
        if saved_faiss % FAISS_SAVE_EVERY < batch_size_actual:
            faiss_idx.save(FAISS_PATH)

        # Pausa entre lotes
        time.sleep(0.5)

    # Guardar FAISS al final (por si quedaron pendientes)
    faiss_idx.save(FAISS_PATH)

    elapsed = time.time() - start_time
    total_chroma = collection.count()
    total_faiss = faiss_idx.index.ntotal
    total_sqlite = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

    print(f"\n\n{'=' * 60}")
    print(f"  COMPLETADO en {fmt_time(elapsed)}")
    print(f"{'=' * 60}")
    print(f"  ChromaDB:    {total_chroma} documentos")
    print(f"  FAISS:       {total_faiss} vectores")
    print(f"  SQLite:      {total_sqlite} embeddings")
    print(f"  Rate limits: {rate_limit_count}")
    print(f"  Lote final:  {batch_size_actual}")
    print(f"\n  Archivos:")
    print(f"    ChromaDB:  {CHROMA_PATH}")
    print(f"    FAISS:     {FAISS_PATH}")
    print(f"    SQLite:    {DB_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
