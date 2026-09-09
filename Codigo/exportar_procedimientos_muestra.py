import csv
import re
import subprocess
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from integra_db_client import IntegraDBClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
EDGE_PROFILE = Path(__file__).parent / "_edge_profile"


def safe_filename(text: str) -> str:
    name = re.sub(r"[^\w\-]+", "_", text.strip()).strip("_")
    return name or "procedimiento"


def html_to_pdf(html_path: Path, pdf_path: Path, timeout: int = 60) -> bool:
    """Convierte HTML a PDF usando Edge headless."""
    if not EDGE_PATH.exists():
        print(f"  [PDF] Edge no encontrado en {EDGE_PATH}")
        return False
    url = html_path.as_uri()
    args = [
        str(EDGE_PATH),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--user-data-dir={EDGE_PROFILE}",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}",
        url,
    ]
    try:
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  [PDF] Timeout convirtiendo {html_path.name}")
        return False
    return pdf_path.exists() and pdf_path.stat().st_size > 0


def main():
    client = IntegraDBClient(server="10.238.66.14")
    conn = client.connect()
    cur = conn.cursor()

    query = """
    SELECT TOP 5
        TRIM(p.PROCEDIMIENTOS_COD) AS codigo,
        TRIM(p.PROCEDIMIENTOS_NOMBRE) AS nombre,
        p.PROCEDIMIENTOS_ESTADO AS estado,
        TRIM(pr.ProcesoNom) AS proceso,
        td.TipoDocumento_Descr AS tipo_documento,
        p.PROCEDIMIENTOS_VIGENCIA AS vigencia_dias,
        p.PROCEDIMIENTOS_FCHELBABORACION AS fecha_elaboracion,
        p.PROCEDIMIENTOS_FCHREVISIONPROC AS fecha_revision_proc,
        p.PROCEDIMIENTOS_FECHREVISIONCAL AS fecha_revision_calidad,
        p.PROCEDIMIENTOS_FCHAPROGERENCIA AS fecha_aprob_gerencia,
        p.PROCEDIMIENTOS_FCHPUBLICACION AS fecha_publicacion,
        p.PROCEDIMIENTOS_FCHOBSOLETO AS fecha_obsoleto,
        p.PROCEDIMIENTOS_OBSERVACION AS observacion,
        p.PROCEDIMIENTOS_WORD AS contenido_html,
        TRIM(el.UsrDscC) AS elaborador,
        TRIM(rev.UsrDscC) AS revisor_proceso,
        TRIM(revcal.UsrDscC) AS revisor_calidad,
        TRIM(apro.UsrDscC) AS aprobador_gerencia,
        TRIM(pub.UsrDscC) AS publicador
    FROM dbo.PROCEDIMIENTOS p
    LEFT JOIN dbo.Proceso pr ON TRIM(p.ProcesoCod) = TRIM(pr.ProcesoCod)
    LEFT JOIN dbo.TipoDocumento td ON p.TipoDocumento_Id = td.TipoDocumento_Id
    LEFT JOIN dbo.TUsuarioC el ON p.PROCEDIMIENTOS_ELABORADOR = el.UsrCdgC
    LEFT JOIN dbo.TUsuarioC rev ON p.PROCEDIMIENTOS_REVISORPROC = rev.UsrCdgC
    LEFT JOIN dbo.TUsuarioC revcal ON p.PROCEDIMIENTOS_REVISIONCALIDAD = revcal.UsrCdgC
    LEFT JOIN dbo.TUsuarioC apro ON p.PROCEDIMIENTOS_APROGERENCIA = apro.UsrCdgC
    LEFT JOIN dbo.TUsuarioC pub ON p.PROCEDIMIENTOS_PUBLICACION = pub.UsrCdgC
    WHERE p.PROCEDIMIENTOS_ESTADO = 'P'
    ORDER BY p.PROCEDIMIENTOS_FCHPUBLICACION DESC
    """
    cur.execute(query)
    rows = cur.fetchall()

    if not rows:
        print("No se encontraron procedimientos publicados.")
        return

    base_dir = Path(__file__).parent.parent / "Muestra_Procedimientos"
    html_dir = base_dir / "html"
    pdf_dir = base_dir / "pdf"
    html_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    columns = [d[0] for d in cur.description]
    fieldnames = [
        "codigo",
        "nombre",
        "estado",
        "proceso",
        "tipo_documento",
        "vigencia_dias",
        "fecha_elaboracion",
        "fecha_revision_proc",
        "fecha_revision_calidad",
        "fecha_aprob_gerencia",
        "fecha_publicacion",
        "fecha_obsoleto",
        "observacion",
        "elaborador",
        "revisor_proceso",
        "revisor_calidad",
        "aprobador_gerencia",
        "publicador",
        "archivo_html",
        "archivo_pdf",
    ]

    csv_path = base_dir / "procedimientos_muestra.csv"
    xlsx_path = base_dir / "procedimientos_muestra.xlsx"

    records = []
    for row in rows:
        record = dict(zip(columns, row))
        codigo = record["codigo"].strip()
        nombre = record["nombre"].strip()
        html = record.get("contenido_html") or ""

        safe_name = safe_filename(f"{codigo}_{nombre}")
        html_file = html_dir / f"{safe_name}.html"
        html_file.write_text(
            f"<!DOCTYPE html>\n<html lang=\"es\">\n<head>\n"
            f"<meta charset=\"utf-8\">\n<title>{codigo}</title>\n"
            f"</head>\n<body>\n{html}\n</body>\n</html>",
            encoding="utf-8",
        )

        out = {k: record.get(k, "") for k in fieldnames if k != "archivo_html"}
        # Limpieza básica de fechas nulas de SQL
        for k in out:
            v = out[k]
            if isinstance(v, str) and v.strip().startswith("1753-"):
                out[k] = None
            if hasattr(v, "strftime"):
                out[k] = v.strftime("%Y-%m-%d %H:%M:%S") if v.year > 1900 else None
        out["archivo_html"] = html_file.relative_to(base_dir).as_posix()

        # Convertir HTML a PDF
        pdf_file = pdf_dir / f"{safe_name}.pdf"
        print(f"  [PDF] Convirtiendo {codigo}...")
        if html_to_pdf(html_file, pdf_file):
            out["archivo_pdf"] = pdf_file.relative_to(base_dir).as_posix()
            print(f"  [PDF] OK: {pdf_file.name} ({pdf_file.stat().st_size} bytes)")
        else:
            out["archivo_pdf"] = ""
            print(f"  [PDF] Falló la conversión de {codigo}")

        records.append(out)

    # CSV
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    # Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Procedimientos"
    ws.append(fieldnames)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for rec in records:
        ws.append([rec.get(k, "") for k in fieldnames])
    wb.save(xlsx_path)

    print(f"Generados {len(records)} registros.")
    print(f"CSV: {csv_path}")
    print(f"Excel: {xlsx_path}")
    print(f"HTML individuales en: {html_dir}")
    print(f"PDF individuales en: {pdf_dir}")
    for r in records:
        print(f"  - {r['codigo']}: {r['nombre']}")


if __name__ == "__main__":
    main()
