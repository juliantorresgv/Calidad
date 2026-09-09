import json
import os
import re
import sys
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI

from governance import Governance
from memoria import Memoria
from context_manager import ContextManager
from content_moderation import ContentModeration
from integra_client import IntegraClient
from integra_procedimientos import ProcedimientosClient


def _reconfigure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


_reconfigure_stdout()

API_KEY = os.environ.get("MISTRAL_API_KEY")
BASE_URL = "https://api.mistral.ai/v1"
MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

DOCS_PATH = Path(__file__).with_name("docs_text.txt")
TRANSCRIPT_PATH = Path(__file__).with_name("transcripcion.txt")


class IntegraDocs:
    """Índice simple del texto extraído de la documentación y transcripción de Integr@."""

    def __init__(self, paths: list[Path] | None = None):
        if paths is None:
            paths = [DOCS_PATH, TRANSCRIPT_PATH]
        self.paths = paths
        self.chunks: list[str] = []
        for path in paths:
            if path.exists():
                self.chunks.extend(self._split(path.read_text(encoding="utf-8", errors="ignore")))

    @staticmethod
    def _split(text: str, max_chars: int = 800) -> list[str]:
        # Separa por líneas de archivo (====) y por cualquier salto de línea
        pieces = re.split(r"\n(?=={40,})|\n+", text)
        chunks: list[str] = []
        current = ""
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            # Si la pieza sola es muy larga, la partimos
            if len(piece) > max_chars:
                for i in range(0, len(piece), max_chars):
                    chunks.append(piece[i : i + max_chars])
                continue
            if len(current) + len(piece) < max_chars:
                current = f"{current}\n\n{piece}".strip()
            else:
                if current:
                    chunks.append(current)
                current = piece
        if current:
            chunks.append(current)
        return chunks

    def search(self, query: str, top_k: int = 8) -> str:
        words = [w.lower() for w in re.findall(r"[a-záéíóúñ0-9]+", query) if len(w) > 2]
        if not words:
            words = [query.lower()]
        scored = []
        for chunk in self.chunks:
            lowered = chunk.lower()
            score = sum(1 for w in words if w in lowered)
            if score:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        result = "\n\n---\n\n".join(c for _, c in scored[:top_k])
        return result or "No encontré información relevante en la documentación local."

    def list_modules(self) -> str:
        modules = [
            "Base Documental",
            "Contenido",
            "Servicios Técnicos",
            "Formatos",
            "Documentos Externos",
            "Glosario Logístico",
            "Procesos",
            "Usuarios",
            "Comunicaciones Calidad",
            "Fundamentos Corporativos",
            "No Conformidades",
            "Partes Interesadas y Normas",
        ]
        return "Módulos de Integr@:\n" + "\n".join(f"- {m}" for m in modules)


class IntegraAgent:
    def __init__(self, api_key: str | None = API_KEY):
        if not api_key:
            raise SystemExit("Falta la variable de entorno MISTRAL_API_KEY")
        self.client = OpenAI(base_url=BASE_URL, api_key=api_key)
        self.docs = IntegraDocs()
        self.governance = Governance()
        self.memoria = Memoria()
        self.context_mgr = ContextManager(memoria=self.memoria, llm_client=self.client, model=MODEL)
        self.moderation = ContentModeration()
        self.tools: list[dict] = [
            {
                "type": "function",
                "function": {
                    "name": "buscar_en_documentacion",
                    "description": "Busca información en la documentación local de Integr@.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Consulta sobre Integr@ (módulos, procedimientos, no conformidades, etc.)",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "intentar_login_integra",
                    "description": "Intenta iniciar sesión en la plataforma web Integr@ con las credenciales almacenadas.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "listar_modulos",
                    "description": "Lista los módulos conocidos de Integr@.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "probar_conexion_db",
                    "description": "Intenta conectar con la base de datos SQL Server de Integra (modo de solo lectura).",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "listar_tablas_db",
                    "description": "Lista las tablas disponibles en la base de datos Integra.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "describir_tabla_db",
                    "description": "Describe las columnas de una tabla de Integra.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Nombre de la tabla, por ejemplo 'dbo.procedimientos' o 'procedimientos'.",
                            }
                        },
                        "required": ["table_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_db",
                    "description": "Ejecuta una consulta SELECT de solo lectura en la base de datos Integra.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "Consulta SELECT SQL (solo lectura).",
                            }
                        },
                        "required": ["sql"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "resumen_procedimientos",
                    "description": "Devuelve un resumen de la tabla PROCEDIMIENTOS: total, conteos por estado, proceso y tipo de documento.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "buscar_procedimiento",
                    "description": "Busca procedimientos por código, nombre, estado, proceso o tipo de documento.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "codigo": {"type": "string"},
                            "nombre": {"type": "string"},
                            "estado": {"type": "string"},
                            "proceso": {"type": "string"},
                            "tipo": {"type": "string"},
                            "limite": {"type": "integer", "default": 10},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "detalle_procedimiento",
                    "description": "Muestra el detalle completo de un procedimiento a partir de su código.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "codigo": {"type": "string"}
                        },
                        "required": ["codigo"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "flujo_procedimiento",
                    "description": "Muestra el historial de estados de un procedimiento.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "codigo": {"type": "string"}
                        },
                        "required": ["codigo"],
                    },
                },
            },
        ]
        self.tool_map: dict[str, Callable] = {
            "buscar_en_documentacion": lambda args: self.docs.search(args.get("query", "")),
            "intentar_login_integra": lambda args: self._try_login(),
            "listar_modulos": lambda args: self.docs.list_modules(),
            "probar_conexion_db": lambda args: self._db_test(),
            "listar_tablas_db": lambda args: self._db_list_tables(),
            "describir_tabla_db": lambda args: self._db_describe(args.get("table_name", "")),
            "consultar_db": lambda args: self._db_query(args.get("sql", "")),
            "resumen_procedimientos": lambda args: self._proc_resumen(),
            "buscar_procedimiento": lambda args: self._proc_buscar(args),
            "detalle_procedimiento": lambda args: self._proc_detalle(args.get("codigo", "")),
            "flujo_procedimiento": lambda args: self._proc_flujo(args.get("codigo", "")),
        }

    @staticmethod
    def _make_db_client() -> tuple[Optional[object], str]:
        from integra_db_client import IntegraDBClient
        try:
            return IntegraDBClient(), ""
        except Exception as e:
            return None, str(e)

    def _db_test(self) -> str:
        client, err = self._make_db_client()
        if client is None:
            return f"No se pudo crear el cliente de base de datos: {err}"
        return client.test()

    def _db_list_tables(self) -> str:
        client, err = self._make_db_client()
        if client is None:
            return f"No se pudo crear el cliente de base de datos: {err}"
        try:
            tables = client.list_tables()
            return "\n".join(tables) or "No se encontraron tablas."
        except Exception as e:
            return f"Error listando tablas: {type(e).__name__}: {e}"

    def _db_describe(self, table_name: str) -> str:
        if not table_name:
            return "Debes proporcionar el nombre de la tabla."
        client, err = self._make_db_client()
        if client is None:
            return f"No se pudo crear el cliente de base de datos: {err}"
        try:
            cols = client.describe_table(table_name)
            lines = [f"{c['column']} ({c['type']}{f'({c['max_length']})' if c['max_length'] else ''})" for c in cols]
            return f"Columnas de {table_name}:\n" + "\n".join(lines)
        except Exception as e:
            return f"Error describiendo tabla: {type(e).__name__}: {e}"

    def _db_query(self, sql: str) -> str:
        if not sql:
            return "Debes proporcionar una consulta SQL."
        # Guardrail: validar SQL antes de ejecutar
        ok, reason = self.governance.validate_sql(sql)
        if not ok:
            return f"Consulta rechazada por governance: {reason}"
        client, err = self._make_db_client()
        if client is None:
            return f"No se pudo crear el cliente de base de datos: {err}"
        try:
            result = client.query(sql)
            lines = [" | ".join(str(v) for v in row) for row in result["rows"]]
            header = " | ".join(result["columns"])
            return f"{header}\n{'-' * len(header)}\n" + "\n".join(lines)
        except Exception as e:
            return f"Error ejecutando consulta: {type(e).__name__}: {e}"

    def _proc_client(self):
        if not hasattr(self, "_proc_cache"):
            self._proc_cache = ProcedimientosClient()
        return self._proc_cache

    def _proc_resumen(self) -> str:
        import json
        try:
            return json.dumps(self._proc_client().resumen(), default=str, ensure_ascii=False)
        except Exception as e:
            return f"Error resumen procedimientos: {type(e).__name__}: {e}"

    def _proc_buscar(self, args: dict) -> str:
        import json
        try:
            result = self._proc_client().buscar(
                codigo=args.get("codigo"),
                nombre=args.get("nombre"),
                estado=args.get("estado"),
                proceso=args.get("proceso"),
                tipo=args.get("tipo"),
                limit=args.get("limite", 10),
            )
            return json.dumps(result, default=str, ensure_ascii=False)
        except Exception as e:
            return f"Error buscando procedimientos: {type(e).__name__}: {e}"

    def _proc_detalle(self, codigo: str) -> str:
        import json
        if not codigo:
            return "Debes proporcionar el código del procedimiento."
        try:
            return json.dumps(self._proc_client().detalle(codigo), default=str, ensure_ascii=False)
        except Exception as e:
            return f"Error detalle procedimiento: {type(e).__name__}: {e}"

    def _proc_flujo(self, codigo: str) -> str:
        import json
        if not codigo:
            return "Debes proporcionar el código del procedimiento."
        try:
            return json.dumps(self._proc_client().flujo(codigo), default=str, ensure_ascii=False)
        except Exception as e:
            return f"Error flujo procedimiento: {type(e).__name__}: {e}"

    def _try_login(self) -> str:
        import requests
        try:
            client = IntegraClient()
            form = client.discover_login_form()
            result = client.login()
            return (
                f"Login HTTP status: {result['status_code']}\n"
                f"URL final: {result['final_url']}\n"
                f"¿Parece autenticado?: {result['is_logged_in']}\n"
                f"Campos detectados: usuario={form['username_field']}, "
                f"contraseña={form['password_field']}, submit={form['submit_field']}"
            )
        except requests.exceptions.HTTPError as e:
            if "502" in str(e) or "Bad Gateway" in str(e):
                return (
                    "El servidor de Integra responde 502 Bad Gateway. "
                    "Esto indica que el proxy/reverso está accesible pero no logra comunicarse con la aplicación backend; "
                    "puede deberse a que Integra requiere acceso a la red corporativa/VPN de Solistica o a que el backend está caído. "
                    f"Detalle técnico: {e}"
                )
            return f"Error HTTP al conectar con Integra: {e}"
        except requests.exceptions.ConnectionError as e:
            err = str(e).lower()
            if "name" in err or "getaddrinfo" in err or "resolve" in err:
                return (
                    "No se pudo resolver el nombre de dominio de Integra. "
                    "El entorno actual no parece tener acceso a la red corporativa de Solistica o la VPN. "
                    f"Detalle técnico: {e}"
                )
            return f"Error de conexión con Integra: {type(e).__name__}: {e}"
        except requests.exceptions.Timeout as e:
            return f"La conexión con Integra ha tardado demasiado (timeout): {e}"
        except Exception as e:
            return f"No se pudo conectar con Integra: {type(e).__name__}: {e}"

    def run(
        self,
        user_message: str,
        messages: list[dict] | None = None,
        user_id: str = "default",
        session_id: str | None = None,
    ) -> tuple[str, list[dict]]:
        import time as _time

        t_start = _time.time()

        # ── Guardrail de entrada: governance ──
        ok, reason = self.governance.validate_input(user_message, user_id=user_id)
        if not ok:
            safe = self.governance.safe_response(reason)
            self.governance.audit(user_id, user_message, safe, session_id=session_id)
            return safe, messages or []

        # ── Content moderation ──
        mod_result = self.moderation.moderate(user_message, user_id=user_id, session_id=session_id or "")
        if mod_result["blocked"]:
            safe = (
                f"Tu mensaje fue bloqueado por content moderation. "
                f"Categoría: {mod_result['category']}. "
                f"Razón: {mod_result['reason']}. "
                f"Por favor, mantén la conversación enfocada en calidad HSEQ."
            )
            self.governance.audit(user_id, user_message, safe, session_id=session_id)
            return safe, messages or []

        # Usar texto filtrado si moderation lo modificó
        user_message_filtered = mod_result["filtered_text"]

        # ── Cache de respuestas (semántico) ──
        cached = self.memoria.cache_semantic_lookup(user_message_filtered)
        if cached:
            self.governance.audit(
                user_id, user_message, cached["respuesta"],
                model="cache", session_id=session_id, tool_used=f"cache_{cached.get('match_type', 'exact')}"
            )
            return cached["respuesta"], messages or []

        # ── Sesión persistente ──
        if session_id is None:
            session = self.memoria.create_session(user_id)
            session_id = session["id"]
        self.memoria.add_message(session_id, "user", user_message_filtered)

        # ── Detección de cambio de tema ──
        if self.context_mgr.detect_topic_change(session_id, user_message_filtered):
            self.context_mgr.invalidate_summary(session_id)

        # ── Context management: construir contexto optimizado ──
        system_prompt = (
            "Eres un agente experto en la plataforma Integr@ de Solistica. "
            "Tienes acceso a la documentación local, a la plataforma web (cuando la red lo permita) "
            "y a la base de datos SQL Server de Integra (modo solo lectura). "
            "Puedes consultar directamente la tabla PROCEDIMIENTOS y otras tablas dbo. "
            "Responde de forma clara, breve y en español. "
            "Si vas a realizar una acción en Integr@, primero explica qué harás."
        ) + self.governance.get_system_prompt_addendum()

        messages = self.context_mgr.build_context(
            session_id=session_id,
            system_prompt=system_prompt,
            new_user_message=user_message_filtered,
            tools=self.tools,
        )

        # ── Llamada al LLM con tools ──
        tool_used = ""
        while True:
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=0.2,
            )
            assistant_message = response.choices[0].message
            assistant_dict: dict = {
                "role": getattr(assistant_message, "role", "assistant"),
                "content": getattr(assistant_message, "content", None) or "",
            }
            raw_tool_calls = getattr(assistant_message, "tool_calls", None)
            if raw_tool_calls:
                assistant_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": getattr(tc, "type", "function"),
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in raw_tool_calls
                ]
            messages.append(assistant_dict)

            tool_calls = raw_tool_calls
            if not tool_calls:
                answer = assistant_message.content or "(sin respuesta)"

                # ── Guardrail de salida: governance (PII, credenciales) ──
                ok_out, reason_out = self.governance.validate_output(answer)
                if not ok_out:
                    answer = self.governance.safe_response(reason_out)
                else:
                    # Filtrar PII de la respuesta
                    answer = self.governance._filter_pii(answer)

                # ── Content moderation de salida ──
                mod_out = self.moderation.moderate(answer, user_id=user_id, session_id=session_id)
                if mod_out["blocked"]:
                    answer = self.governance.safe_response("content_moderation_output")
                else:
                    answer = mod_out["filtered_text"]

                # ── Guardar en cache con tipo ──
                tokens_in = getattr(response.usage, "prompt_tokens", 0) or 0
                tokens_out = getattr(response.usage, "completion_tokens", 0) or 0
                cache_type = "procedimiento" if any(
                    kw in user_message_filtered.lower()
                    for kw in ["procedimiento", "pafa", "peop", "pgc", "pco", "pwhs", "pcp"]
                ) else "general"
                self.memoria.cache_set(
                    user_message_filtered, answer, modelo=MODEL,
                    tokens_input=tokens_in, tokens_output=tokens_out,
                    cache_type=cache_type
                )

                # ── Guardar en sesión ──
                self.memoria.add_message(
                    session_id, "assistant", answer,
                    tokens=tokens_out, model=MODEL, tool_used=tool_used
                )

                # ── Auditoría ──
                latency_ms = int((_time.time() - t_start) * 1000)
                self.governance.audit(
                    user_id, user_message, answer, model=MODEL,
                    tokens_input=tokens_in, tokens_output=tokens_out,
                    latency_ms=latency_ms, session_id=session_id, tool_used=tool_used
                )

                return answer, messages

            for tc in tool_calls:
                fn = tc.function
                args = json.loads(fn.arguments or "{}")
                tool_used = fn.name
                result = self.tool_map.get(fn.name, lambda a: f"Herramienta '{fn.name}' no implementada")(args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn.name,
                    "content": str(result)[:4000],
                })


def main():
    _reconfigure_stdout()
    agent = IntegraAgent()
    print("Agente Integr@ + Mistral iniciado. Escribe 'salir' para terminar.\n")
    print("  Governance: guardrails (prompt injection, PII, SQL, tópicos, rate limit)")
    print("  Content moderation: toxicidad, hate speech, acoso, spam")
    print("  Context management: sliding window, resumen automático, presupuesto tokens")
    print("  Memoria: cache semántico + sesiones + knowledge store + checkpoints\n")
    messages = None
    session_id = None
    user_id = "cli_user"
    while True:
        try:
            user = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user or user.lower() in ("salir", "exit", "quit"):
            break
        answer, messages = agent.run(user, messages, user_id=user_id, session_id=session_id)
        # Guardar session_id para reutilizar en la misma conversación
        if session_id is None and hasattr(agent, 'memoria'):
            sessions = agent.memoria.get_active_sessions(user_id)
            if sessions:
                session_id = sessions[0]["id"]
        print(f"Agente: {answer}\n")


if __name__ == "__main__":
    main()
