import json
import sys

from integra_procedimientos import ProcedimientosClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    client = ProcedimientosClient()
    for cod in ["MAC-27-02", "MAC-35-01", "PGC-16-15"]:
        print(f"\n=== Flujo {cod} ===")
        print(json.dumps(client.flujo(cod), default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
