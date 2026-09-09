import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from integra_db_client import IntegraDBClient


def main():
    server = os.environ.get("INTEGRA_DB_SERVER")
    if not server:
        print("Define la variable de entorno INTEGRA_DB_SERVER, ejemplo:")
        print("  $env:INTEGRA_DB_SERVER=\"servidor\\instancia\"")
        return

    client = IntegraDBClient(server=server)
    print(client.test())
    try:
        client.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
