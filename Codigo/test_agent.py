import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from agente_integra import IntegraAgent

api_key = os.environ.get("MISTRAL_API_KEY")
agent = IntegraAgent(api_key=api_key)
query = "¿Cómo crear un procedimiento en Integra?"
print(f"Consulta: {query}\n")
answer, _ = agent.run(query)
print(f"Respuesta:\n{answer}")
