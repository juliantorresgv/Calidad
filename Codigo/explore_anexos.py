import json
import sys

from integra_db_client import IntegraDBClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    client = IntegraDBClient(server="10.238.66.14")
    for cod in ["AC-634-RP-IQ, OQ, PQ-2588 V.01", "PGC-16-15"]:
        print(f"\n=== Anexos de {cod} ===")
        q = (
            "SELECT TOP 3 PROCEDIMIENTOS_COD, ANEXO_COD, ANEXO_NOM, ANEXO_TIPO, ANEXO_NOMBARCH, "
            "DATALENGTH(ANEXO_ARCHIVO) AS size "
            "FROM dbo.PROCEDIMIENTOSANEXO WHERE TRIM(PROCEDIMIENTOS_COD)=?"
        )
        result = client.query(q, (cod,))
        print(json.dumps(result, default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
