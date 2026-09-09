import json
import sys

from integra_db_client import IntegraDBClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    client = IntegraDBClient(server="10.238.66.14")
    for uid in [19705, 3278, 2554, 2534]:
        print(f"\n=== Usuario {uid} ===")
        for tbl, col in [("TUsuarioC", "UsrCdgC"), ("USUARIOT", "UsrCdg")]:
            q = f"SELECT TOP 1 * FROM dbo.{tbl} WHERE {col} = {uid}"
            result = client.query(q)
            print(tbl, json.dumps(result, default=str, ensure_ascii=False, indent=2)[:1000])


if __name__ == "__main__":
    main()
