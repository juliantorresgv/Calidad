import json
import sys

from integra_db_client import IntegraDBClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    client = IntegraDBClient(server="10.238.66.14")

    print("=== Estados actuales en PROCEDIMIENTOS ===")
    result = client.query(
        "SELECT PROCEDIMIENTOS_ESTADO, COUNT(*) AS cnt FROM dbo.PROCEDIMIENTOS GROUP BY PROCEDIMIENTOS_ESTADO ORDER BY cnt DESC"
    )
    print(json.dumps(result, default=str, ensure_ascii=False, indent=2))

    print("\n=== Ejemplo de cada estado ===")
    states = ["E", "R", "A", "P", "O", "D", "Z", "Q"]
    for st in states:
        q = (
            "SELECT TOP 1 PROCEDIMIENTOS_COD, PROCEDIMIENTOS_ESTADO, "
            "PROCEDIMIENTOS_FCHELBABORACION, PROCEDIMIENTOS_FCHREVISIONPROC, "
            "PROCEDIMIENTOS_FECHREVISIONCAL, PROCEDIMIENTOS_FCHAPROGERENCIA, "
            "PROCEDIMIENTOS_FCHPUBLICACION, PROCEDIMIENTOS_FCHOBSOLETO "
            f"FROM dbo.PROCEDIMIENTOS WHERE PROCEDIMIENTOS_ESTADO='{st}'"
        )
        result = client.query(q)
        print(f"\nEstado '{st}':")
        print(json.dumps(result, default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
