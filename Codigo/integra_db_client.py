import os
import re
from pathlib import Path
from typing import Optional

import pyodbc


def _load_credentials(path: Optional[Path] = None) -> tuple[str, str]:
    if path is None:
        path = Path(r"C:\Users\1121871773\OneDrive - agvco\Documentos\Agente Calidad Codigo\credenciales.txt")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("El archivo de credenciales debe contener al menos usuario y contraseña.")
    return lines[0], lines[1]


class IntegraDBClient:
    """Cliente de solo lectura para la base de datos Integra (SQL Server).

    Las credenciales se leen de ``credenciales.txt`` o de las variables de
    entorno ``INTEGRA_DB_USER`` y ``INTEGRA_DB_PASSWORD``.
    """

    def __init__(
        self,
        server: Optional[str] = None,
        database: str = "Integra",
        username: Optional[str] = None,
        password: Optional[str] = None,
        driver: str = "ODBC Driver 17 for SQL Server",
        timeout: int = 30,
    ):
        self.server = server or os.environ.get("INTEGRA_DB_SERVER")
        if not self.server:
            raise ValueError(
                "Falta el nombre/IP del servidor SQL. Define INTEGRA_DB_SERVER o pasa server=."
            )
        self.database = database
        self.driver = driver or "ODBC Driver 17 for SQL Server"
        self.timeout = timeout

        if username is None or password is None:
            self.username, self.password = _load_credentials()
        else:
            self.username, self.password = username, password

        self._conn: Optional[pyodbc.Connection] = None

    def _connection_string(self) -> str:
        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            f"Timeout={self.timeout};"
            f"TrustServerCertificate=yes;"
        )

    def connect(self) -> pyodbc.Connection:
        if self._conn is None:
            self._conn = pyodbc.connect(self._connection_string())
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def test(self) -> str:
        try:
            conn = self.connect()
            with conn.cursor() as cur:
                cur.execute("SELECT DB_NAME(), @@VERSION")
                row = cur.fetchone()
                return f"Conectado. Base: {row[0]}. Versión: {row[1][:80]}..."
        except Exception as e:
            return f"Error de conexión: {type(e).__name__}: {e}"

    def list_tables(self) -> list[str]:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
            return [f"{row.TABLE_SCHEMA}.{row.TABLE_NAME}" for row in cur.fetchall()]

    def describe_table(self, table_name: str) -> list[dict]:
        schema, _, name = table_name.rpartition(".")
        if not schema:
            schema = "dbo"
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
                "ORDER BY ORDINAL_POSITION",
                (schema, name),
            )
            return [
                {
                    "column": row.COLUMN_NAME,
                    "type": row.DATA_TYPE,
                    "max_length": row.CHARACTER_MAXIMUM_LENGTH,
                }
                for row in cur.fetchall()
            ]

    def query(self, sql: str, params: Optional[tuple] = None, max_rows: int = 50) -> dict:
        """Ejecuta una consulta SELECT de solo lectura.

        Rechaza sentencias que no sean SELECT para evitar modificaciones.
        """
        cleaned = re.sub(r"--[^\n]*", "", sql, flags=re.MULTILINE)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
        first_token = re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|SP_|XP_)\b", cleaned, re.I)
        if not first_token or first_token.group(1).upper() != "SELECT":
            raise ValueError("Solo se permiten consultas SELECT. Consulta rechazada por seguridad.")

        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchmany(max_rows)
            return {
                "columns": columns,
                "rows": [list(row) for row in rows],
                "row_count": len(rows),
            }


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    client = IntegraDBClient()
    print(client.test())
