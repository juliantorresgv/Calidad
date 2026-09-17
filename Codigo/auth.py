"""
Autenticacion basica de usuarios para el Agente de Calidad Integr@.
Soporta login con usuario/password y sesiones persistentes en SQLite.
Los passwords se almacenan con hash (sha256 + salt).
"""
import hashlib
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"


def _hash_password(password: str, salt: str = "") -> str:
    """Hash de password con salt."""
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def _verify_password(password: str, stored: str) -> bool:
    """Verifica password contra el hash almacenado."""
    try:
        salt, hashed = stored.split(":")
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except Exception:
        return False


class AuthManager:
    """Gestor de autenticacion de usuarios."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_tables()
        self._ensure_default_admin()

    def _init_tables(self):
        """Crea las tablas de usuarios y sesiones."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol TEXT DEFAULT 'usuario',
                nombre TEXT DEFAULT '',
                email TEXT DEFAULT '',
                activo BOOLEAN DEFAULT 1,
                creado TEXT DEFAULT (datetime('now', 'localtime')),
                ultimo_login TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sesiones_auth (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                username TEXT,
                rol TEXT,
                creada TEXT DEFAULT (datetime('now', 'localtime')),
                expira TEXT,
                FOREIGN KEY (user_id) REFERENCES usuarios(id)
            )
        """)
        self.conn.commit()

    def _ensure_default_admin(self):
        """Crea un usuario admin por defecto si no hay usuarios."""
        count = self.conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if count == 0:
            self.create_user("admin", "admin123", rol="admin", nombre="Administrador")
            print("  [Auth] Usuario admin creado (usuario: admin, password: admin123) - CAMBIA EL PASSWORD!")

    def create_user(self, username: str, password: str, rol: str = "usuario",
                    nombre: str = "", email: str = "") -> dict:
        """Crea un nuevo usuario."""
        try:
            self.conn.execute(
                "INSERT INTO usuarios (username, password_hash, rol, nombre, email) VALUES (?, ?, ?, ?, ?)",
                (username, _hash_password(password), rol, nombre, email)
            )
            self.conn.commit()
            return {"ok": True, "mensaje": f"Usuario {username} creado"}
        except sqlite3.IntegrityError:
            return {"ok": False, "mensaje": f"Usuario {username} ya existe"}

    def login(self, username: str, password: str) -> dict:
        """Inicia sesion. Retorna {ok, token, user} o {ok: False, mensaje}."""
        row = self.conn.execute(
            "SELECT id, username, password_hash, rol, nombre, activo FROM usuarios WHERE username = ?",
            (username,)
        ).fetchone()

        if not row:
            return {"ok": False, "mensaje": "Usuario no encontrado"}

        user_id, uname, pw_hash, rol, nombre, activo = row
        if not activo:
            return {"ok": False, "mensaje": "Usuario inactivo"}

        if not _verify_password(password, pw_hash):
            return {"ok": False, "mensaje": "Password incorrecto"}

        # Crear sesion
        token = os.urandom(24).hex()
        expira = str(int(time.time()) + 86400 * 7)  # 7 dias
        self.conn.execute(
            "INSERT INTO sesiones_auth (token, user_id, username, rol, expira) VALUES (?, ?, ?, ?, ?)",
            (token, user_id, uname, rol, expira)
        )
        self.conn.execute(
            "UPDATE usuarios SET ultimo_login = datetime('now', 'localtime') WHERE id = ?",
            (user_id,)
        )
        self.conn.commit()

        return {
            "ok": True,
            "token": token,
            "user": {"id": user_id, "username": uname, "rol": rol, "nombre": nombre}
        }

    def verify_session(self, token: str) -> dict | None:
        """Verifica un token de sesion. Retorna user info o None."""
        if not token:
            return None
        row = self.conn.execute(
            "SELECT user_id, username, rol FROM sesiones_auth WHERE token = ? AND expira > ?",
            (token, str(int(time.time())))
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "rol": row[2]}

    def logout(self, token: str):
        """Cierra sesion."""
        self.conn.execute("DELETE FROM sesiones_auth WHERE token = ?", (token,))
        self.conn.commit()

    def list_users(self) -> list[dict]:
        """Lista todos los usuarios."""
        rows = self.conn.execute(
            "SELECT id, username, rol, nombre, email, activo, creado, ultimo_login FROM usuarios ORDER BY id"
        ).fetchall()
        return [
            {"id": r[0], "username": r[1], "rol": r[2], "nombre": r[3],
             "email": r[4], "activo": bool(r[5]), "creado": r[6], "ultimo_login": r[7]}
            for r in rows
        ]

    def change_password(self, username: str, old_password: str, new_password: str) -> dict:
        """Cambia el password de un usuario."""
        row = self.conn.execute(
            "SELECT password_hash FROM usuarios WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return {"ok": False, "mensaje": "Usuario no encontrado"}
        if not _verify_password(old_password, row[0]):
            return {"ok": False, "mensaje": "Password actual incorrecto"}
        self.conn.execute(
            "UPDATE usuarios SET password_hash = ? WHERE username = ?",
            (_hash_password(new_password), username)
        )
        self.conn.commit()
        return {"ok": True, "mensaje": "Password actualizado"}

    def delete_user(self, username: str) -> dict:
        """Elimina un usuario."""
        if username == "admin":
            return {"ok": False, "mensaje": "No se puede eliminar el usuario admin"}
        self.conn.execute("DELETE FROM usuarios WHERE username = ?", (username,))
        self.conn.commit()
        return {"ok": True, "mensaje": f"Usuario {username} eliminado"}

    # ──────────────────────────────────────────────
    # RBAC: Role-Based Access Control
    # ──────────────────────────────────────────────

    # Definicion de permisos por rol
    PERMISOS = {
        "admin": {
            "chat", "estadisticas", "jerarquia", "vencidos", "glosario",
            "finops", "documentos", "comparador", "arquitectura", "seguridad",
            "sincronizacion", "auditoria", "no_conformidades", "salud",
            "gestion_usuarios", "exportar", "descargar",
        },
        "calidad": {
            "chat", "estadisticas", "jerarquia", "vencidos", "glosario",
            "finops", "documentos", "comparador", "arquitectura", "seguridad",
            "sincronizacion", "auditoria", "no_conformidades", "salud",
            "exportar", "descargar",
        },
        "auditor": {
            "chat", "estadisticas", "jerarquia", "vencidos", "glosario",
            "documentos", "comparador", "arquitectura", "auditoria", "no_conformidades",
            "salud", "exportar", "descargar",
        },
        "operador": {
            "chat", "documentos", "glosario", "vencidos", "descargar",
        },
        "usuario": {
            "chat", "documentos", "glosario",
        },
    }

    def has_permission(self, rol: str, permiso: str) -> bool:
        """Verifica si un rol tiene un permiso especifico."""
        permisos_rol = self.PERMISOS.get(rol, self.PERMISOS["usuario"])
        return permiso in permisos_rol

    def get_permissions(self, rol: str) -> set:
        """Retorna el conjunto de permisos de un rol."""
        return self.PERMISOS.get(rol, self.PERMISOS["usuario"])

    # ──────────────────────────────────────────────
    # Session timeout (cerrar sesion por inactividad)
    # ──────────────────────────────────────────────

    SESSION_TIMEOUT_SECONDS = 1800  # 30 minutos de inactividad

    def check_session_timeout(self, token: str, last_activity: float) -> bool:
        """Verifica si la sesion ha expirado por inactividad.
        last_activity: timestamp de la ultima actividad.
        Retorna True si la sesion sigue activa, False si expiro.
        """
        if not token:
            return False
        elapsed = time.time() - last_activity
        if elapsed > self.SESSION_TIMEOUT_SECONDS:
            self.logout(token)
            return False
        return True

    # ──────────────────────────────────────────────
    # Watermarking de respuestas
    # ──────────────────────────────────────────────

    def watermark_response(self, respuesta: str, user_id: int, username: str) -> str:
        """Agrega un watermark invisible a la respuesta para trazabilidad.
        El watermark contiene el ID de usuario y timestamp, codificado para no ser visible.
        """
        timestamp = int(time.time())
        # Watermark como comentario HTML invisible (no se muestra en markdown)
        watermark = f"<!--wm:{user_id}:{username}:{timestamp}-->"
        # Insertar al final de la respuesta
        return respuesta + watermark

    def verify_watermark(self, respuesta: str) -> dict | None:
        """Extrae y verifica el watermark de una respuesta.
        Retorna {user_id, username, timestamp} o None si no hay watermark.
        """
        import re
        match = re.search(r'<!--wm:(\d+):([^:]+):(\d+)-->', respuesta)
        if match:
            return {
                "user_id": int(match.group(1)),
                "username": match.group(2),
                "timestamp": int(match.group(3)),
            }
        return None

    # ──────────────────────────────────────────────
    # Deteccion de anomalias (anti-abuso)
    # ──────────────────────────────────────────────

    ANOMALIA_UMBRAL_POR_MINUTO = 20  # mas de 20 preguntas por minuto = anomalia
    ANOMALIA_UMBRAL_POR_HORA = 200  # mas de 200 por hora = anomalia
    ANOMALIA_UMBRAL_POR_DIA = 1000  # mas de 1000 por dia = anomalia

    def _init_anomalias_table(self):
        """Crea la tabla de deteccion de anomalias."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS anomalias_detectadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                tipo TEXT,
                descripcion TEXT,
                timestamp TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self.conn.commit()

    def detectar_anomalia(self, user_id: int, username: str) -> dict:
        """Detecta patrones de uso sospechosos.
        Retorna {anomalia: bool, tipo: str, descripcion: str}
        """
        self._init_anomalias_table()
        ahora = int(time.time())

        # Contar preguntas en el ultimo minuto
        hace_un_minuto = ahora - 60
        count_minuto = self.conn.execute(
            "SELECT COUNT(*) FROM audit_trail WHERE timestamp >= ?",
            (str(hace_un_minuto),)
        ).fetchone()[0]

        # Contar preguntas en la ultima hora
        hace_una_hora = ahora - 3600
        count_hora = self.conn.execute(
            "SELECT COUNT(*) FROM audit_trail WHERE timestamp >= ?",
            (str(hace_una_hora),)
        ).fetchone()[0]

        # Contar preguntas en el ultimo dia
        hace_un_dia = ahora - 86400
        count_dia = self.conn.execute(
            "SELECT COUNT(*) FROM audit_trail WHERE timestamp >= ?",
            (str(hace_un_dia),)
        ).fetchone()[0]

        if count_minuto > self.ANOMALIA_UMBRAL_POR_MINUTO:
            desc = f"{count_minuto} preguntas en 1 minuto (umbral: {self.ANOMALIA_UMBRAL_POR_MINUTO})"
            self._registrar_anomalia(user_id, username, "rate_minuto", desc)
            return {"anomalia": True, "tipo": "rate_minuto", "descripcion": desc, "count": count_minuto}

        if count_hora > self.ANOMALIA_UMBRAL_POR_HORA:
            desc = f"{count_hora} preguntas en 1 hora (umbral: {self.ANOMALIA_UMBRAL_POR_HORA})"
            self._registrar_anomalia(user_id, username, "rate_hora", desc)
            return {"anomalia": True, "tipo": "rate_hora", "descripcion": desc, "count": count_hora}

        if count_dia > self.ANOMALIA_UMBRAL_POR_DIA:
            desc = f"{count_dia} preguntas en 1 dia (umbral: {self.ANOMALIA_UMBRAL_POR_DIA})"
            self._registrar_anomalia(user_id, username, "rate_dia", desc)
            return {"anomalia": True, "tipo": "rate_dia", "descripcion": desc, "count": count_dia}

        return {"anomalia": False, "tipo": "", "descripcion": "", "count": count_minuto}

    def _registrar_anomalia(self, user_id: int, username: str, tipo: str, descripcion: str):
        """Registra una anomalia detectada."""
        self.conn.execute(
            "INSERT INTO anomalias_detectadas (user_id, username, tipo, descripcion) VALUES (?, ?, ?, ?)",
            (user_id, username, tipo, descripcion)
        )
        self.conn.commit()

    def listar_anomalias(self, limit: int = 50) -> list[dict]:
        """Lista anomalias detectadas."""
        self._init_anomalias_table()
        rows = self.conn.execute(
            "SELECT id, user_id, username, tipo, descripcion, timestamp FROM anomalias_detectadas ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [
            {"id": r[0], "user_id": r[1], "username": r[2], "tipo": r[3],
             "descripcion": r[4], "timestamp": r[5]}
            for r in rows
        ]
