"""
Calidad y seguridad: Hallucination detection, citation verification,
DLP (Data Loss Prevention) y PII redaction en logs.

Este módulo valida que las respuestas del agente esten fundamentadas
en los documentos recuperados y que no contengan informacion sensible.
"""
import os
import re
import json
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "indice_procedimientos.db"


# ──────────────────────────────────────────────
# 1. Hallucination Detection
# ──────────────────────────────────────────────

# Patrones de afirmaciones que requieren verificacion
AFFIRMATION_PATTERNS = [
    r"seg[uú]n\s+(.{5,100})",
    r"de\s+acuerdo\s+con\s+(.{5,100})",
    r"el\s+documento\s+(.{5,50})",
    r"el\s+procedimiento\s+(.{5,50})",
    r"establece\s+que\s+(.{5,200})",
    r"indica\s+que\s+(.{5,200})",
    r"define\s+(.{5,200})",
    r"requiere\s+que\s+(.{5,200})",
    r"est[aá]\ndard\s+(.{5,100})",
]

# Patrones de alucinacion tipica
HALLUCINATION_INDICATORS = [
    r"no\s+tengo\s+informaci[oó]n",
    r"no\s+se\s+encuentra\s+en\s+los\s+documentos",
    r"bas[aá]ndome\s+en\s+mi\s+conocimiento",
    r"en\s+general\s+los\s+procedimientos",
    r"t[ií]picamente\s+se\s+suele",
    r"es\s+com[uú]n\s+que\s+se",
]


def detect_hallucination(response: str, retrieved_docs: list[dict],
                         llm_client=None) -> dict:
    """Detecta alucinaciones en la respuesta comparando con documentos recuperados.

    Retorna:
    {
        "hallucination_score": 0-1 (0=ok, 1=alucinacion total),
        "grounded": bool,
        "unsupported_claims": list[str],
        "verified_citations": list[str],
        "missing_citations": list[str],
    }
    """
    result = {
        "hallucination_score": 0.0,
        "grounded": True,
        "unsupported_claims": [],
        "verified_citations": [],
        "missing_citations": [],
    }

    if not response:
        return result

    # 1. Extraer citas de la respuesta (codigos de documento)
    cited_codes = set()
    code_pattern = re.compile(r'\b([A-Z]{2,5})[-_]?(\d{1,3})[-_]?(\d{1,3})\b')
    for match in code_pattern.finditer(response):
        cited_codes.add(match.group())

    # 2. Codigos de documentos recuperados
    retrieved_codes = set()
    for doc in retrieved_docs:
        if isinstance(doc, dict) and "codigo" in doc:
            retrieved_codes.add(doc["codigo"])

    # 3. Verificar que las citas existen en los documentos recuperados
    for code in cited_codes:
        if code in retrieved_codes:
            result["verified_citations"].append(code)
        else:
            # Verificar si existe en la base de datos
            try:
                conn = sqlite3.connect(str(DB_PATH))
                row = conn.execute(
                    "SELECT codigo FROM procedimientos WHERE codigo = ?", (code,)
                ).fetchone()
                conn.close()
                if row:
                    result["verified_citations"].append(code)
                    result["unsupported_claims"].append(
                        f"Cita {code} existe pero no fue recuperada en esta consulta"
                    )
                else:
                    result["missing_citations"].append(code)
                    result["unsupported_claims"].append(
                        f"Cita {code} no existe en la base de datos"
                    )
            except Exception:
                result["missing_citations"].append(code)

    # 4. Detectar indicadores de alucinacion
    response_lower = response.lower()
    for pattern in HALLUCINATION_INDICATORS:
        if re.search(pattern, response_lower):
            result["unsupported_claims"].append(
                f"Indicador de alucinacion: patron '{pattern}'"
            )
            result["hallucination_score"] += 0.2

    # 5. Verificar afirmaciones contra documentos recuperados
    retrieved_text = " ".join([
        doc.get("texto", "") or doc.get("nombre", "")
        for doc in retrieved_docs
        if isinstance(doc, dict)
    ]).lower()

    for pattern in AFFIRMATION_PATTERNS:
        for match in re.finditer(pattern, response, re.IGNORECASE):
            claim = match.group(1)[:100].lower()
            # Verificar si la afirmacion tiene soporte en los documentos
            words = set(claim.split())
            retrieved_words = set(retrieved_text.split())
            overlap = len(words & retrieved_words)
            if overlap < len(words) * 0.3 and len(words) > 3:
                result["unsupported_claims"].append(
                    f"Afirmacion sin soporte: '{match.group()[:80]}...'"
                )
                result["hallucination_score"] += 0.1

    # 6. LLM-based hallucination detection (opcional)
    if llm_client and len(result["unsupported_claims"]) > 0:
        try:
            prompt = f"""Analiza si la siguiente respuesta esta fundamentada en los documentos.

Respuesta: {response[:1000]}

Documentos recuperados:
{retrieved_text[:2000]}

Responde SOLO un JSON:
{{"grounded": true/false, "score": 0.0-1.0, "issues": ["problema1", "problema2"]}}"""

            resp = llm_client.chat.completions.create(
                model=os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=300,
            )
            content = resp.choices[0].message.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            llm_result = json.loads(content)
            result["hallucination_score"] = max(
                result["hallucination_score"], llm_result.get("score", 0)
            )
            if llm_result.get("issues"):
                result["unsupported_claims"].extend(llm_result["issues"])
        except Exception:
            pass

    # Normalizar score
    result["hallucination_score"] = min(result["hallucination_score"], 1.0)
    result["grounded"] = result["hallucination_score"] < 0.5

    return result


# ──────────────────────────────────────────────
# 2. Citation Verification
# ──────────────────────────────────────────────

def verify_citations(response: str, conn: sqlite3.Connection) -> dict:
    """Verifica que todos los codigos citados en la respuesta existen en la BD."""
    cited_codes = set()
    code_pattern = re.compile(r'\b([A-Z]{2,5})[-_]?(\d{1,3})[-_]?(\d{1,3})\b')
    for match in code_pattern.finditer(response):
        cited_codes.add(match.group())

    verified = []
    not_found = []

    for code in cited_codes:
        row = conn.execute(
            "SELECT codigo, nombre, estado FROM procedimientos WHERE codigo = ?",
            (code,)
        ).fetchone()
        if row:
            verified.append({"codigo": code, "nombre": row[1], "estado": row[2]})
        else:
            not_found.append(code)

    return {
        "total_citations": len(cited_codes),
        "verified": verified,
        "not_found": not_found,
        "all_valid": len(not_found) == 0,
    }


def add_citations_if_missing(response: str, retrieved_docs: list[dict]) -> str:
    """Si la respuesta no cita documentos pero los hay recuperados, los agrega."""
    code_pattern = re.compile(r'\b([A-Z]{2,5})[-_]?(\d{1,3})[-_]?(\d{1,3})\b')
    has_citations = bool(code_pattern.search(response))

    if has_citations:
        return response

    if not retrieved_docs:
        return response

    # Agregar citas al final
    citations = []
    for doc in retrieved_docs[:3]:
        if isinstance(doc, dict) and "codigo" in doc:
            citations.append(f"{doc['codigo']} - {doc.get('nombre', '')[:60]}")

    if citations:
        return response + "\n\nFuentes: " + "; ".join(citations)

    return response


# ──────────────────────────────────────────────
# 3. DLP (Data Loss Prevention)
# ──────────────────────────────────────────────

# Patrones de informacion sensible que NO debe revelar el agente
SENSITIVE_PATTERNS = {
    "password": re.compile(r'(?:password|passwd|pwd|contrase[ñn]a)\s*[:=]\s*\S+', re.IGNORECASE),
    "api_key": re.compile(r'(?:api[_-]?key|token|secret)\s*[:=]\s*[A-Za-z0-9_\-]{20,}', re.IGNORECASE),
    "credit_card": re.compile(r'\b(?:\d[ -]?){13,16}\b'),
    "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "ip_address": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    "phone": re.compile(r'\b(?:\+?\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b'),
    "sql_connection": re.compile(r'(?:server|data\s+source)\s*=\s*[^;]+;.*(?:uid|user)\s*=\s*[^;]+;.*(?:pwd|password)\s*=\s*[^;]+', re.IGNORECASE),
}

# Informacion que el agente NUNCA debe revelar
FORBIDDEN_TOPICS = [
    "credenciales", "contraseñas", "api keys", "tokens de acceso",
    "datos personales de empleados", "informacion financiera",
    "datos de tarjetas de credito", "numeros de cuenta bancaria",
]

DLP_REPLACEMENTS = {
    "password": "[REDACTED-PASSWORD]",
    "api_key": "[REDACTED-API-KEY]",
    "credit_card": "[REDACTED-CC]",
    "ssn": "[REDACTED-SSN]",
    "email": "[REDACTED-EMAIL]",
    "ip_address": "[REDACTED-IP]",
    "phone": "[REDACTED-PHONE]",
    "sql_connection": "[REDACTED-CONNECTION-STRING]",
}


def apply_dlp(text: str) -> tuple[str, list[dict]]:
    """Aplica DLP: detecta y enmascara informacion sensible en el texto.
    Retorna (texto_limpio, lista_de_detecciones)."""
    cleaned = text
    detections = []

    for pattern_name, pattern in SENSITIVE_PATTERNS.items():
        for match in pattern.finditer(text):
            replacement = DLP_REPLACEMENTS.get(pattern_name, "[REDACTED]")
            cleaned = cleaned.replace(match.group(), replacement)
            detections.append({
                "type": pattern_name,
                "start": match.start(),
                "end": match.end(),
                "masked": True,
            })

    # Verificar topics prohibidos
    text_lower = text.lower()
    for topic in FORBIDDEN_TOPICS:
        if topic in text_lower:
            detections.append({
                "type": "forbidden_topic",
                "topic": topic,
                "masked": False,
                "warning": f"Respuesta menciona tema prohibido: {topic}",
            })

    return cleaned, detections


def check_input_dlp(query: str) -> dict:
    """Verifica si la pregunta del usuario intenta extraer informacion sensible."""
    suspicious_patterns = [
        r"(?:cu[aá]l\s+es\s+)?(?:la\s+)?contrase[ñn]a",
        r"(?:dame|mu[eé]strame|cu[aá]l\s+es)\s+(?:el\s+)?(?:api[_-]?key|token|secret)",
        r"(?:cu[aá]les\s+son\s+)?(?:las\s+)?credenciales",
        r"(?:mu[eé]strame|dame)\s+(?:los\s+)?datos\s+(?:de\s+)?tarjeta",
        r"(?:cu[aá]l\s+es\s+)?(?:el\s+)?numero\s+de\s+cuenta",
        r"(?:dame|mu[eé]strame)\s+(?:los\s+)?datos\s+personales",
        r"(?:ignora|olvida|desactiva)\s+(?:las\s+)?(?:reglas|restricciones|guardrails)",
        r"(?:act[uú]a\s+como\s+)?(?:modo\s+)?(?:desarrollador|developer|admin|root)",
    ]

    threats = []
    for pattern in suspicious_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            threats.append({
                "type": "data_extraction_attempt",
                "pattern": pattern,
                "blocked": True,
            })

    return {
        "is_safe": len(threats) == 0,
        "threats": threats,
    }


# ──────────────────────────────────────────────
# 4. PII Redaction en Logs
# ──────────────────────────────────────────────

# Patrones de PII para enmascarar en logs
PII_PATTERNS = {
    "cedula_colombia": re.compile(r'\b\d{6,10}\b'),
    "nit": re.compile(r'\b\d{8,9}-\d\b'),
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "phone": re.compile(r'\b(?:\+?\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b'),
    "ip": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    "credit_card": re.compile(r'\b(?:\d[ -]?){13,16}\b'),
    "address": re.compile(r'(?:calle|carrera|av\.|avenida|diagonal|transversal)\s+\d+', re.IGNORECASE),
}


def redact_pii_in_log(text: str) -> str:
    """Enmascara PII en texto de logs para proteger informacion personal."""
    redacted = text

    # Email -> primer_caracter***@dominio.com
    for match in PII_PATTERNS["email"].finditer(text):
        email = match.group()
        if "@" in email:
            parts = email.split("@")
            if len(parts[0]) > 2:
                masked = parts[0][0] + "***@" + parts[1]
            else:
                masked = "***@" + parts[1]
            redacted = redacted.replace(email, masked)

    # Telefono -> ***-***-1234
    for match in PII_PATTERNS["phone"].finditer(text):
        phone = match.group()
        if len(phone) >= 7:
            masked = "***-***-" + phone[-4:]
            redacted = redacted.replace(phone, masked)

    # IP -> x.x.x.x
    for match in PII_PATTERNS["ip"].finditer(text):
        ip = match.group()
        parts = ip.split(".")
        if len(parts) == 4:
            masked = f"{parts[0]}.{parts[1]}.x.x"
            redacted = redacted.replace(ip, masked)

    # Cedula -> ****1234
    for match in PII_PATTERNS["cedula_colombia"].finditer(text):
        cedula = match.group()
        if 6 <= len(cedula) <= 10:
            masked = "****" + cedula[-4:]
            redacted = redacted.replace(cedula, masked)

    # NIT -> ********X
    for match in PII_PATTERNS["nit"].finditer(text):
        nit = match.group()
        masked = "********" + nit[-2:]
        redacted = redacted.replace(nit, masked)

    # Tarjeta -> ****-****-****-1234
    for match in PII_PATTERNS["credit_card"].finditer(text):
        cc = match.group().replace(" ", "").replace("-", "")
        if 13 <= len(cc) <= 16:
            masked = "****-****-****-" + cc[-4:]
            redacted = redacted.replace(match.group(), masked)

    # Direccion -> Calle ****
    for match in PII_PATTERNS["address"].finditer(text):
        addr = match.group()
        parts = addr.split()
        if len(parts) >= 2:
            masked = parts[0] + " ****"
            redacted = redacted.replace(addr, masked)

    return redacted


def safe_log(level: str, message: str, **kwargs) -> dict:
    """Log con PII redaction automatica."""
    safe_message = redact_pii_in_log(message)
    safe_kwargs = {k: redact_pii_in_log(str(v)) for k, v in kwargs.items()}

    log_entry = {
        "level": level,
        "message": safe_message,
        "redacted": safe_message != message,
        **safe_kwargs,
    }

    # Si hay redaccion, registrar
    if log_entry["redacted"]:
        log_entry["pii_detected"] = True

    return log_entry


# ──────────────────────────────────────────────
# Tabla SQLite para almacenar resultados
# ──────────────────────────────────────────────

def init_quality_tables(conn: sqlite3.Connection):
    """Crea tablas para almacenar resultados de calidad."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hallucination_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            pregunta TEXT,
            respuesta TEXT,
            hallucination_score REAL,
            grounded INTEGER,
            unsupported_claims TEXT,
            verified_citations TEXT,
            missing_citations TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dlp_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            tipo TEXT,
            detecciones TEXT,
            bloqueado INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS citation_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            respuesta TEXT,
            total_citations INTEGER,
            verified_count INTEGER,
            not_found TEXT,
            all_valid INTEGER
        )
    """)
    conn.commit()


def save_hallucination_check(conn: sqlite3.Connection, session_id: str,
                              pregunta: str, respuesta: str, result: dict):
    """Guarda resultado de deteccion de alucinacion."""
    conn.execute("""
        INSERT INTO hallucination_checks
        (session_id, pregunta, respuesta, hallucination_score, grounded,
         unsupported_claims, verified_citations, missing_citations)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, pregunta, respuesta,
        result["hallucination_score"],
        int(result["grounded"]),
        json.dumps(result["unsupported_claims"], ensure_ascii=False),
        json.dumps(result["verified_citations"], ensure_ascii=False),
        json.dumps(result["missing_citations"], ensure_ascii=False),
    ))
    conn.commit()


def save_dlp_check(conn: sqlite3.Connection, session_id: str,
                    tipo: str, detecciones: list[dict], bloqueado: bool = False):
    """Guarda resultado de DLP."""
    conn.execute("""
        INSERT INTO dlp_checks (session_id, tipo, detecciones, bloqueado)
        VALUES (?, ?, ?, ?)
    """, (
        session_id, tipo,
        json.dumps(detecciones, ensure_ascii=False),
        int(bloqueado),
    ))
    conn.commit()


def save_citation_verification(conn: sqlite3.Connection, session_id: str,
                                respuesta: str, result: dict):
    """Guarda verificacion de citas."""
    conn.execute("""
        INSERT INTO citation_verifications
        (session_id, respuesta, total_citations, verified_count, not_found, all_valid)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session_id, respuesta,
        result["total_citations"],
        len(result["verified"]),
        json.dumps(result["not_found"], ensure_ascii=False),
        int(result["all_valid"]),
    ))
    conn.commit()


if __name__ == "__main__":
    # Test rapido
    conn = sqlite3.connect(str(DB_PATH))
    init_quality_tables(conn)

    # Test hallucination detection
    test_response = "Segun el documento PGC-16-15, la temperatura debe ser 2-8°C."
    test_docs = [{"codigo": "PGC-16-15", "nombre": "Almacenamiento", "texto": "temperatura 2-8"}]
    result = detect_hallucination(test_response, test_docs)
    print("Hallucination:", json.dumps(result, indent=2, ensure_ascii=False))

    # Test DLP
    test_text = "Mi password es admin123 y el email es user@agv.com y la IP es 10.238.66.14"
    cleaned, detections = apply_dlp(test_text)
    print(f"\nDLP original: {test_text}")
    print(f"DLP limpio: {cleaned}")
    print(f"Detecciones: {len(detections)}")

    # Test PII redaction
    log_text = "Usuario juan@empresa.com con telefono +57-310-123-4567 desde IP 10.238.66.14"
    print(f"\nLog original: {log_text}")
    print(f"Log redacted: {redact_pii_in_log(log_text)}")

    conn.close()
