import json
import sys
from collections import defaultdict
from pathlib import Path

from integra_db_client import IntegraDBClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def build_schema(client: IntegraDBClient) -> dict:
    conn = client.connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE,
               CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE,
               IS_NULLABLE, ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo'
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """
    )
    schema: dict[str, list[dict]] = defaultdict(list)
    for row in cursor.fetchall():
        schema[row.TABLE_NAME].append(
            {
                "column": row.COLUMN_NAME,
                "type": row.DATA_TYPE,
                "max_length": row.CHARACTER_MAXIMUM_LENGTH,
                "numeric_precision": row.NUMERIC_PRECISION,
                "numeric_scale": row.NUMERIC_SCALE,
                "is_nullable": row.IS_NULLABLE,
                "ordinal": row.ORDINAL_POSITION,
            }
        )
    return dict(schema)


def main():
    client = IntegraDBClient(server="10.238.66.14")
    print("Leyendo esquema de la base de datos...")
    schema = build_schema(client)
    print(f"Tablas dbo mapeadas: {len(schema)}")

    out_json = Path(__file__).with_name("schema_map.json")
    out_json.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Mapa JSON guardado en: {out_json}")

    # Resumen en texto plano
    out_txt = Path(__file__).with_name("schema_summary.txt")
    lines = []
    for table, columns in sorted(schema.items()):
        lines.append(f"{table} ({len(columns)} columnas)")
        for col in columns:
            type_str = col["type"]
            if col["max_length"]:
                type_str += f"({col['max_length']})"
            elif col["numeric_precision"] is not None:
                scale = col["numeric_scale"] or 0
                type_str += f"({col['numeric_precision']},{scale})"
            lines.append(f"  - {col['column']}: {type_str}")
        lines.append("")
    out_txt.write_text("\n".join(lines), encoding="utf-8")
    print(f"Resumen guardado en: {out_txt}")


if __name__ == "__main__":
    main()
