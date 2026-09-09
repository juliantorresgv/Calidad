import subprocess
import sys
from pathlib import Path


def convert_html_to_pdf(edge_path: Path, html_path: Path, pdf_path: Path, timeout: int = 60):
    """Convierte un HTML a PDF usando Microsoft Edge en modo headless."""
    url = html_path.as_uri()
    user_data_dir = Path(__file__).parent / "_edge_profile"
    args = [
        str(edge_path),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--user-data-dir={user_data_dir}",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}",
        url,
    ]
    print("Ejecutando:", " ".join(args))
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    return pdf_path.exists() and pdf_path.stat().st_size > 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    html_dir = Path(r"C:\Users\1121871773\OneDrive - agvco\Documentos\Agente Calidad Codigo\Muestra_Procedimientos\html")

    # Buscar el primer HTML disponible
    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        print("No se encontraron archivos HTML en", html_dir)
        sys.exit(1)

    html = html_files[0]
    pdf = html.with_suffix(".pdf")
    print(f"Convirtiendo: {html.name}")
    ok = convert_html_to_pdf(edge, html, pdf)
    print("PDF generado:", ok, "->", pdf)
