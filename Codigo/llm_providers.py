"""
Proveedores LLM con fallback automatico.

Centraliza la inicializacion y logica de fallback entre todos los
proveedores LLM disponibles:
  1. Ollama (local, sin rate limit)
  2. Mistral (cloud, rapido)
  3. Groq (cloud, rapido)
  4. Gemini (cloud, rapido)
  5. OpenAI (cloud, puede estar bloqueado por firewall)

Uso:
    from llm_providers import LLMProviders

    providers = LLMProviders()
    response = providers.chat(messages, temperature=0.2)
    # → intenta Ollama → Mistral → Groq → Gemini → OpenAI
"""
import os
import sys
import time
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ──────────────────────────────────────────────
# Configuracion de proveedores
# ──────────────────────────────────────────────

MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_CHAT_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_EMBED_MODEL = "mistral-embed"

OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_EMBED_MODEL = "text-embedding-3-small"

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_CHAT_MODEL = os.environ.get("GROQ_CHAT_MODEL", "groq/compound")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_CHAT_MODEL = os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.0-flash")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "qwen-fast")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Orden de fallback por defecto
DEFAULT_FALLBACK_ORDER = ["ollama", "mistral", "groq", "gemini", "openai"]


def _classify_error(e: Exception) -> str:
    """Clasifica un error de LLM en una categoria."""
    err = str(e)
    err_type = type(e).__name__
    if "429" in err or "rate" in err.lower() or "rate_limit" in err_type.lower():
        return "rate_limit"
    if "401" in err or "auth" in err.lower() or "api key" in err.lower():
        return "auth_error"
    if "404" in err or "model_not_found" in err:
        return "model_not_found"
    if "timeout" in err.lower() or "APITimeoutError" in err_type or "ConnectTimeout" in err_type:
        return "timeout"
    if "Connection" in err_type or "ConnectError" in err_type or "getaddrinfo" in err:
        return "connection_error"
    return f"other:{err_type}"


class LLMProviders:
    """Gestor de multiples proveedores LLM con fallback automatico."""

    def __init__(self, primary: str = "mistral", fallback_order: list[str] | None = None):
        """
        Args:
            primary: Proveedor primario ('mistral', 'ollama', 'groq', 'gemini', 'openai')
            fallback_order: Orden de fallback. Si None, usa DEFAULT_FALLBACK_ORDER.
        """
        from openai import OpenAI

        self.primary = primary
        self.fallback_order = fallback_order or DEFAULT_FALLBACK_ORDER

        # Asegurar que el primario este primero
        if primary in self.fallback_order:
            self.fallback_order.remove(primary)
        self.fallback_order.insert(0, primary)

        # Inicializar clientes
        self.clients: dict[str, tuple] = {}  # {name: (client, model)}

        # Mistral
        mistral_key = os.environ.get("MISTRAL_API_KEY")
        if mistral_key:
            try:
                self.clients["mistral"] = (
                    OpenAI(base_url=MISTRAL_BASE_URL, api_key=mistral_key, timeout=60.0, max_retries=2),
                    MISTRAL_CHAT_MODEL,
                )
            except Exception:
                pass

        # Ollama (local, no requiere API key)
        try:
            self.clients["ollama"] = (
                OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama", timeout=120.0, max_retries=2),
                OLLAMA_CHAT_MODEL,
            )
        except Exception:
            pass



        # Groq
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            try:
                self.clients["groq"] = (
                    OpenAI(base_url=GROQ_BASE_URL, api_key=groq_key, timeout=60.0, max_retries=2),
                    GROQ_CHAT_MODEL,
                )
            except Exception:
                pass

        # Gemini
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                self.clients["gemini"] = (
                    OpenAI(base_url=GEMINI_BASE_URL, api_key=gemini_key, timeout=60.0, max_retries=2),
                    GEMINI_CHAT_MODEL,
                )
            except Exception:
                pass

        # OpenAI
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                self.clients["openai"] = (
                    OpenAI(api_key=openai_key, timeout=120.0, max_retries=2),
                    OPENAI_CHAT_MODEL,
                )
            except Exception:
                pass

        # Cliente primario (para compatibilidad hacia atras)
        self.client = self.clients.get(primary, [None])[0]
        self.model = self.clients.get(primary, [None, ""])[1]

        # Estado de rate limiting por proveedor
        self._rate_limited: dict[str, float] = {}  # {provider: timestamp}
        self._consecutive_failures: dict[str, int] = {}

        # Imprimir estado
        self._print_status()

    def _print_status(self):
        """Imprime el estado de los proveedores disponibles."""
        available = list(self.clients.keys())
        print(f"  [LLM] Proveedores disponibles: {', '.join(available)}")
        print(f"  [LLM] Orden de fallback: {' → '.join(self.fallback_order)}")
        if not available:
            print("  [LLM] ⚠ No hay proveedores disponibles!")

    def _ollama_embed(self, text: str) -> list[float]:
        """Embedding nativo de Ollama via /api/embeddings (fallback si /v1 no funciona)."""
        import json
        from urllib import request, error
        base = OLLAMA_BASE_URL.replace("/v1", "").rstrip("/")
        url = f"{base}/api/embeddings"
        data = json.dumps({"model": OLLAMA_EMBED_MODEL, "prompt": text[:8000]}).encode("utf-8")
        req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["embedding"]
        except Exception as e:
            raise RuntimeError(f"Ollama embedding fallo: {e}")

    def _is_rate_limited(self, provider: str, cooldown: int = 60) -> bool:
        """Verifica si un proveedor esta en cooldown por rate limit."""
        ts = self._rate_limited.get(provider)
        if ts and (time.time() - ts) < cooldown:
            return True
        if ts:
            del self._rate_limited[provider]
        return False

    def _mark_rate_limited(self, provider: str):
        """Marca un proveedor como rate-limited."""
        self._rate_limited[provider] = time.time()
        self._consecutive_failures[provider] = self._consecutive_failures.get(provider, 0) + 1

    def _reset_failures(self, provider: str):
        """Resetea el contador de fallos de un proveedor."""
        self._consecutive_failures.pop(provider, None)

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list | None = None,
        tool_choice: str = "auto",
        prefer: str | None = None,
    ) -> tuple[object, str]:
        """Llama al LLM con fallback automatico entre proveedores.

        Args:
            messages: Lista de mensajes en formato OpenAI.
            temperature: Temperatura de muestreo.
            max_tokens: Maximo de tokens de salida (None = sin limite).
            tools: Tools disponibles (formato OpenAI function calling).
            tool_choice: Estrategia de seleccion de tools.
            prefer: Proveedor preferido para esta llamada (sobrescribe primary).

        Returns:
            (response_object, provider_used)
            response_object es el objeto devuelto por el SDK de OpenAI.

        Raises:
            RuntimeError: Si todos los proveedores fallan.
        """
        # Construir orden de intento
        order = list(self.fallback_order)
        if prefer and prefer in order:
            order.remove(prefer)
            order.insert(0, prefer)

        errors: list[str] = []

        for provider in order:
            if provider not in self.clients:
                continue
            if self._is_rate_limited(provider):
                cooldown = int(60 - (time.time() - self._rate_limited.get(provider, 0)))
                errors.append(f"{provider}: rate_limited (cooldown {cooldown}s)")
                continue

            client, model = self.clients[provider]
            try:
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice

                response = client.chat.completions.create(**kwargs)
                self._reset_failures(provider)
                return response, provider

            except Exception as e:
                err_type = _classify_error(e)
                err_msg = str(e)[:150]

                if err_type == "rate_limit":
                    self._mark_rate_limited(provider)
                    print(f"  [LLM] {provider}: rate_limit → fallback")
                    errors.append(f"{provider}: rate_limit")
                elif err_type == "timeout":
                    print(f"  [LLM] {provider}: timeout → fallback")
                    errors.append(f"{provider}: timeout")
                elif err_type == "connection_error":
                    print(f"  [LLM] {provider}: connection_error → fallback")
                    errors.append(f"{provider}: connection_error")
                elif err_type == "auth_error":
                    print(f"  [LLM] {provider}: auth_error → fallback")
                    errors.append(f"{provider}: auth_error")
                else:
                    print(f"  [LLM] {provider}: {err_type} → fallback")
                    errors.append(f"{provider}: {err_type}")

                # Pausa breve antes del siguiente proveedor
                time.sleep(1)

        # Todos fallaron
        raise RuntimeError(
            f"Todos los proveedores LLM fallaron:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        prefer: str | None = None,
    ):
        """Llama al LLM en modo streaming con fallback automatico.

        Genera tokens uno a uno. Si el primer proveedor falla, intenta
        el siguiente. Una vez que el primer token llega, no hay mas fallback.

        Yields:
            (token_text, provider_used)
        """
        order = list(self.fallback_order)
        if prefer and prefer in order:
            order.remove(prefer)
            order.insert(0, prefer)

        errors: list[str] = []

        for provider in order:
            if provider not in self.clients:
                continue
            if self._is_rate_limited(provider):
                cooldown = int(60 - (time.time() - self._rate_limited.get(provider, 0)))
                errors.append(f"{provider}: rate_limited (cooldown {cooldown}s)")
                continue

            client, model = self.clients[provider]
            try:
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens

                stream = client.chat.completions.create(**kwargs)
                self._reset_failures(provider)
                first_token = True
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        if first_token:
                            print(f"  [LLM] Streaming via {provider}")
                            first_token = False
                        yield chunk.choices[0].delta.content, provider
                return  # termino exitosamente

            except Exception as e:
                err_type = _classify_error(e)
                err_msg = str(e)[:150]

                if err_type == "rate_limit":
                    self._mark_rate_limited(provider)
                    print(f"  [LLM] {provider}: rate_limit → fallback")
                    errors.append(f"{provider}: rate_limit")
                elif err_type == "timeout":
                    print(f"  [LLM] {provider}: timeout → fallback")
                    errors.append(f"{provider}: timeout")
                elif err_type == "connection_error":
                    print(f"  [LLM] {provider}: connection_error → fallback")
                    errors.append(f"{provider}: connection_error")
                elif err_type == "auth_error":
                    print(f"  [LLM] {provider}: auth_error → fallback")
                    errors.append(f"{provider}: auth_error")
                else:
                    print(f"  [LLM] {provider}: {err_type} → fallback")
                    errors.append(f"{provider}: {err_type}")

                time.sleep(1)

        raise RuntimeError(
            f"Todos los proveedores LLM fallaron:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    def chat_simple(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        prefer: str | None = None,
    ) -> tuple[str, str, str]:
        """Version simplificada de chat que retorna solo el texto.

        Returns:
            (answer_text, provider_used, model_used)
        """
        response, provider = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            prefer=prefer,
        )
        answer = response.choices[0].message.content or ""
        model = self.clients[provider][1]
        return answer, provider, model

    def embeddings(
        self,
        text: str,
        max_chars: int = 8000,
        prefer: str = "mistral",
    ) -> tuple[list[float], str]:
        """Genera embeddings con fallback segun prefer (mistral → ollama → openai).

        Returns:
            (embedding_vector, provider_used)
        """
        text = text[:max_chars]

        # Ollama
        if prefer in ("ollama", None) and "ollama" in self.clients and not self._is_rate_limited("ollama"):
            try:
                emb = self._ollama_embed(text)
                return emb, "ollama"
            except Exception as e:
                print(f"  [LLM] Ollama embedding fallo: {e}")

        # Mistral
        if prefer not in ("openai", "ollama") and "mistral" in self.clients and not self._is_rate_limited("mistral"):
            try:
                client, _ = self.clients["mistral"]
                resp = client.embeddings.create(model=MISTRAL_EMBED_MODEL, input=[text])
                return resp.data[0].embedding, "mistral"
            except Exception as e:
                if _classify_error(e) == "rate_limit":
                    self._mark_rate_limited("mistral")

        # OpenAI
        if "openai" in self.clients:
            try:
                client, _ = self.clients["openai"]
                resp = client.embeddings.create(
                    model=OPENAI_EMBED_MODEL, input=[text], dimensions=1024
                )
                return resp.data[0].embedding, "openai"
            except Exception as e:
                if _classify_error(e) == "rate_limit":
                    self._mark_rate_limited("openai")

        raise RuntimeError("No se pudo generar embedding: Mistral, Ollama y OpenAI fallaron")

    def get_status(self) -> dict:
        """Retorna el estado actual de los proveedores."""
        status = {}
        for provider in self.fallback_order:
            if provider not in self.clients:
                status[provider] = "no_configured"
            elif self._is_rate_limited(provider):
                cooldown = int(60 - (time.time() - self._rate_limited.get(provider, 0)))
                status[provider] = f"rate_limited ({cooldown}s)"
            else:
                status[provider] = "available"
        return status

    def print_status(self):
        """Imprime el estado actual de los proveedores."""
        status = self.get_status()
        print("\n  [LLM] Estado de proveedores:")
        for provider, state in status.items():
            icon = "✅" if state == "available" else "⚠" if "rate_limited" in state else "❌"
            print(f"    {icon} {provider}: {state}")
