import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from agente_integra import IntegraAgent

api_key = os.environ.get("MISTRAL_API_KEY")
agent = IntegraAgent(api_key=api_key)

queries = [
    "Resumen de procedimientos",
    "Busca el procedimiento PGC-16-15",
    "Muestra el detalle del procedimiento PGC-16-15",
]

messages = None
for q in queries:
    print(f"\n=== {q} ===")
    answer, messages = agent.run(q, messages)
    print(answer)
