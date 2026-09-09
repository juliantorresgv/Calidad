import os
import sys
from openai import OpenAI

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API_KEY = os.environ.get("MISTRAL_API_KEY")
if not API_KEY:
    raise SystemExit("Falta la variable de entorno MISTRAL_API_KEY")

client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=API_KEY)

try:
    response = client.chat.completions.create(
        model="mistral-small-latest",
        messages=[{"role": "user", "content": "Hola, di un saludo corto"}],
        max_tokens=50,
    )
    print("Respuesta de Mistral:", response.choices[0].message.content)
except Exception as e:
    print("Error al llamar a Mistral:", type(e).__name__, e)
