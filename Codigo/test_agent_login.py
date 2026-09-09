import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from agente_integra import IntegraAgent

api_key = os.environ.get("MISTRAL_API_KEY")
agent = IntegraAgent(api_key=api_key)
query = "Intenta conectar con Integra"
print(f"Consulta: {query}\n")
answer, messages = agent.run(query)
print(f"Respuesta:\n{answer}\n")
print("=== Mensajes enviados ===")
for i, m in enumerate(messages):
    role = m.get("role")
    content = m.get("content", "")[:200]
    print(f"{i}. {role}: {content}...")
