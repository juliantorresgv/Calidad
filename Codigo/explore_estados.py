import json
import sys

from integra_db_client import IntegraDBClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    client = IntegraDBClient(server="10.238.66.14")

    print("=== Secuencia de estados para 10 procedimientos ===")
    result = client.query(
        "SELECT TOP 50 Procecod, ProceEstado, ProceEstaCns, ProceEstUsurio, ProceEstadFch "
        "FROM dbo.ProcedimientoEstado ORDER BY Procecod, ProceEstaCns"
    )
    print(json.dumps(result, default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
