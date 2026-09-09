import json
import sys

from integra_procedimientos import ProcedimientosClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    client = ProcedimientosClient()

    print("=== Búsqueda por nombre 'seguimiento' ===")
    resultados = client.buscar(nombre="seguimiento", limit=3)
    print(json.dumps(resultados, default=str, ensure_ascii=False, indent=2))

    if resultados:
        cod = resultados[0]["codigo"]
        print(f"\n=== Detalle de {cod} ===")
        detalle = client.detalle(cod)
        print(json.dumps(detalle, default=str, ensure_ascii=False, indent=2))

        print(f"\n=== Flujo de {cod} ===")
        flujo = client.flujo(cod)
        print(json.dumps(flujo, default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
