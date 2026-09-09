from pathlib import Path
from docx import Document

p = Path(r"C:\Users\1121871773\OneDrive - agvco\Documentos\Agente Calidad Codigo\Reunión\Integra.docx")
doc = Document(str(p))
lines = [para.text for para in doc.paragraphs if para.text.strip()]

out = Path(r"C:\Users\1121871773\OneDrive - agvco\Documentos\Agente Calidad Codigo\Codigo\transcripcion.txt")
out.write_text("\n".join(lines), encoding="utf-8", errors="ignore")
print(f"Transcripción guardada en {out}")
