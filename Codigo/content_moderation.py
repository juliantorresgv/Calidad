"""
Content Moderation para el Agente de Calidad Integr@.

Detecta y filtra contenido inapropiado:
- Toxicidad (insultos, lenguaje ofensivo)
- Hate speech (discurso de odio)
- Acoso (harassment)
- Spam / contenido repetitivo
- Autolesión / violencia
- Contenido sexual inapropiado

Funciona con detección basada en reglas (regex + léxicos) en español.
No requiere API externa - todo es local y sin rate limits.

Uso:
    from content_moderation import ContentModeration
    mod = ContentModeration()

    result = mod.moderate("texto a evaluar")
    if result["blocked"]:
        print(f"Bloqueado: {result['category']} - {result['reason']}")

    # O filtrar directamente
    filtered = mod.filter("texto con insulto")
"""
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"


# ──────────────────────────────────────────────
# Léxicos de moderación (español)
# ──────────────────────────────────────────────

# Toxicidad: insultos y lenguaje ofensivo
TOXICIDAD = re.compile(
    r"\b(idiota|imbecil|estupido|estupida|pendejo|pendeja|puto|puta|cabron|cabrona|"
    r"marica|maricon|hijueputa|hijoputa|malparido|malparida|gonorrea|"
    r"pirobo|sapa|comemierda|come_mierda|verga|culo|mierda|jodido|jodida|"
    r"chingado|chingada|pito|teta|verga|bicho|coño|carajo|"
    r"asshole|bitch|fuck|shit|damn|bastard|dick|cunt|moron|idiot|stupid)\b",
    re.IGNORECASE,
)

# Hate speech: discurso de odio contra grupos
HATE_SPEECH = re.compile(
    r"\b(odio\s+(a\s+)?(los|las|todos|todas|esa|esos|esas|estos|estas)\b|"
    r"odio\s+a\s+(los|las)\s+\w+|"
    r"exterminio|genocidio|"
    r"racis[tm]o|racista|xen[oó]fobo|xenofobia|"
    r"machista|misogino|misoginia|"
    r"homofobo|homofobia|transfobo|transfobia|"
    r"discriminaci[oó]n\s+(racial|sexual|de\s+genero|religiosa)|"
    r"inferior\s+por\s+(ser|raza|genero|color|religion)|"
    r"no\s+deber[ií]an\s+existir|"
    r"raza\s+inferior|raza\s+superior|"
    r"limpieza\s+(etnica|social)|"
    r"kill\s+all|death\s+to|exterminate)\b",
    re.IGNORECASE,
)

# Acoso / harassment
ACOSO = re.compile(
    r"\b(amenaza|amenazo|te\s+voy\s+a\s+(matar|lastimar|golpear|buscar|encontrar|hackear)|"
    r"voy\s+a\s+encontrarte|s[eé]\s+donde\s+vives|"
    r"te\s+estoy\s+vigilando|te\s+estoy\s+observando|"
    r"nadie\s+te\s+va\s+a\s+creer|"
    r"te\s+voy\s+a\s+arruinar|destruir\s+tu\s+vida|"
    r"acoso|hostigamiento|stalking|"
    r"doxxing|publicar\s+(sus|tus)\s+datos|"
    r"te\s+voy\s+a\s+hackear|hackearte|"
    r"kill\s+yourself|go\s+kill\s+yourself|"
    r"nadie\s+te\s+quiere|no\s+vales\s+nada|"
    r"eres\s+un\s+fracaso|mata\s+te\s+mismo)\b",
    re.IGNORECASE,
)

# Autolesión / violencia
AUTOLESION = re.compile(
    r"\b(suicidarme|suicidio|cortarme|cortar\s+(mis|las)\s+(mu[ñn]ecas|venas)|"
    r"acabar\s+con\s+todo|no\s+quiero\s+vivir|"
    r"tomar\s+pastillas|sobredosis|"
    r"ahogarme|saltar\s+de\s+(un|el)\s+(puente|edificio|balc[oó]n|ventana)|"
    r"self\s+harm|kill\s+myself|end\s+my\s+life|"
    r"como\s+(ahorcarme|colgarme|suicidarme))\b",
    re.IGNORECASE,
)

# Contenido sexual inapropiado
CONTENIDO_SEXUAL = re.compile(
    r"\b(pornograf[ií]a|porno|xxx|contenido\s+sexual\s+expl[ií]cito|"
    r"desnudo|desnuda|relaciones\s+sexuales|"
    r"actos\s+sexuales|exhibicionismo|"
    r"pedofilia|explotaci[oó]n\s+sexual|"
    r"nude|naked|sexual\s+content|explicit\s+sex)\b",
    re.IGNORECASE,
)

# Spam: patrones repetitivos y promocionales
SPAM_PATTERNS = re.compile(
    r"(https?://\S+\s+){3,}|"  # múltiples URLs
    r"(compra\s+ahora|oferta\s+limitada|gratis\s+aqu[ií]|click\s+aqu[ií]|"
    r"haz\s+click|descarga\s+gratis|gana\s+dinero|"
    r"trabaja\s+desde\s+casa|inversion\s+garantizada|"
    r"100\s*%\s+gratis|sin\s+inversion|"
    r"comparte\s+con\s+\d+|reenv[ií]a\s+esto|"
    r"si\s+no\s+env[ií]as|cadena\s+de\s+suerte)\b",
    re.IGNORECASE,
)

# Repetición excesiva (spam de caracteres)
REPETICION_EXCESIVA = re.compile(r"(.)\1{10,}|(\S+\s+){5,}\2")

# Whitelist: términos que parecen toxicidad pero son OK en contexto de calidad
WHITELIST_CALIDAD = re.compile(
    r"\b(no\s+conformidad|desviaci[oó]n|hallazgo|incumplimiento|"
    r"defecto|falla|error|correcci[oó]n|"
    r"acci[oó]n\s+correctiva|acci[oó]n\s+preventiva|"
    r"mejora\s+continua|auditor[ií]a)\b",
    re.IGNORECASE,
)


class ContentModeration:
    """Moderación de contenido basada en reglas léxicas en español."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Crea tabla de moderación."""
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS moderation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT,
                session_id TEXT,
                text_hash TEXT,
                category TEXT,
                severity TEXT,
                action TEXT,
                matched_terms TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_mod_category ON moderation_log(category);
            CREATE INDEX IF NOT EXISTS idx_mod_time ON moderation_log(timestamp);
        """)
        conn.commit()
        conn.close()

    def moderate(self, text: str, user_id: str = "default", session_id: str = "") -> dict:
        """Evalúa un texto y retorna el resultado de moderación.

        Retorna:
            {
                "blocked": bool,
                "category": str,  # toxicidad, hate_speech, acoso, etc.
                "severity": str,  # low, medium, high, critical
                "reason": str,
                "matched": list[str],
                "filtered_text": str,
            }
        """
        if not text or not text.strip():
            return {"blocked": False, "category": "", "severity": "", "reason": "", "matched": [], "filtered_text": text}

        # Verificar whitelist (contexto de calidad)
        has_whitelist = bool(WHITELIST_CALIDAD.search(text))

        # Evaluar cada categoría
        checks = [
            ("hate_speech", HATE_SPEECH, "critical", "Discurso de odio detectado"),
            ("acoso", ACOSO, "critical", "Contenido de acoso o amenaza detectado"),
            ("autolesion", AUTOLESION, "critical", "Contenido de autolesion detectado"),
            ("contenido_sexual", CONTENIDO_SEXUAL, "high", "Contenido sexual inapropiado"),
            ("toxicidad", TOXICIDAD, "high", "Lenguaje toxico detectado"),
            ("spam", SPAM_PATTERNS, "low", "Patron de spam detectado"),
        ]

        for category, pattern, severity, reason in checks:
            matches = pattern.findall(text)
            if matches:
                # Si es toxicidad pero hay whitelist, solo advertir
                if category == "toxicidad" and has_whitelist:
                    severity = "low"
                    reason = "Posible lenguaje inapropiado en contexto de calidad"

                matched = [str(m)[:50] for m in matches[:5]]
                filtered = self._filter_text(text, pattern)

                self._log_moderation(user_id, session_id, text, category, severity, "filtered", matched)

                return {
                    "blocked": severity in ("critical", "high"),
                    "category": category,
                    "severity": severity,
                    "reason": reason,
                    "matched": matched,
                    "filtered_text": filtered,
                }

        # Repetición excesiva
        if REPETICION_EXCESIVA.search(text):
            self._log_moderation(user_id, session_id, text, "spam", "low", "filtered", ["repeticion_excesiva"])
            return {
                "blocked": False,
                "category": "spam",
                "severity": "low",
                "reason": "Repeticion excesiva detectada",
                "matched": ["repeticion_excesiva"],
                "filtered_text": text,
            }

        return {"blocked": False, "category": "", "severity": "", "reason": "", "matched": [], "filtered_text": text}

    def _filter_text(self, text: str, pattern: re.Pattern) -> str:
        """Reemplaza términos ofensivos con asteriscos."""
        def replace_match(m):
            word = m.group()
            return word[0] + "*" * (len(word) - 1)
        return pattern.sub(replace_match, text)

    def _log_moderation(self, user_id: str, session_id: str, text: str, category: str, severity: str, action: str, matched: list):
        """Registra en log de moderación."""
        import hashlib
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO moderation_log (timestamp, user_id, session_id, text_hash, category, severity, action, matched_terms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), user_id, session_id, text_hash, category, severity, action, ", ".join(matched)))
        conn.commit()
        conn.close()

    def get_moderation_stats(self, hours: int = 24) -> dict:
        """Estadísticas de moderación."""
        from datetime import timedelta
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("""
            SELECT category, severity, COUNT(*)
            FROM moderation_log WHERE timestamp > ?
            GROUP BY category, severity
        """, (since,)).fetchall()
        conn.close()

        stats = {}
        for cat, sev, count in rows:
            if cat not in stats:
                stats[cat] = {}
            stats[cat][sev] = count

        return {"periodo_horas": hours, "by_category": stats}
