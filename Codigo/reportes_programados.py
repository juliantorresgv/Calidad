"""
Generador de reportes programados del Agente de Calidad Integr@.

Genera reportes semanales o mensuales con:
- Estadisticas de uso (preguntas, tokens, costos)
- Documentos nuevos/modificados/eliminados
- Documentos vencidos/por vencer
- No conformidades abiertas/cerradas
- Evaluacion de calidad de respuestas
- Audit trail resumido

Uso manual:
    python Codigo/reportes_programados.py --periodo semanal
    python Codigo/reportes_programados.py --periodo mensual

Uso con Task Scheduler (semanal, lunes 8:00 AM):
    $action = New-ScheduledTaskAction -Execute "python" -Argument "Codigo/reportes_programados.py --periodo semanal" `
        -WorkingDirectory "C:\\Users\\1121871773\\OneDrive - agvco\\Documentos\\Agente Calidad Codigo"
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 8am
    Register-ScheduledTask -TaskName "ReporteIntegra" -Action $action -Trigger $trigger
"""
import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

LOG_PATH = Path(__file__).parent / "reportes.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("reportes")

DB_PATH = Path(__file__).parent.parent / "indice_procedimientos.db"
REPORTES_DIR = Path(__file__).parent.parent / "Reportes"


def generar_reporte(periodo: str = "semanal") -> dict:
    """Genera un reporte completo.
    periodo: 'semanal' (ultimos 7 dias) o 'mensual' (ultimos 30 dias)
    """
    if periodo == "semanal":
        dias = 7
        nombre_periodo = "Semanal"
    else:
        dias = 30
        nombre_periodo = "Mensual"

    fecha_fin = datetime.now()
    fecha_inicio = fecha_fin - timedelta(days=dias)

    log.info(f"Generando reporte {nombre_periodo.lower()} ({fecha_inicio.strftime('%Y-%m-%d')} a {fecha_fin.strftime('%Y-%m-%d')})")

    conn = sqlite3.connect(str(DB_PATH))

    reporte = {
        "periodo": nombre_periodo,
        "fecha_inicio": fecha_inicio.strftime("%Y-%m-%d"),
        "fecha_fin": fecha_fin.strftime("%Y-%m-%d"),
        "generado": fecha_fin.isoformat(),
    }

    # 1. Estadisticas de uso (audit trail)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                session_id TEXT,
                pregunta TEXT,
                respuesta TEXT,
                provider TEXT,
                confidence_nivel TEXT,
                total_time REAL,
                tokens_input INTEGER,
                tokens_output INTEGER
            )
        """)
        rows = conn.execute("""
            SELECT COUNT(*), COUNT(DISTINCT session_id),
                   AVG(total_time), SUM(tokens_input), SUM(tokens_output)
            FROM audit_trail
            WHERE timestamp >= ?
        """, (fecha_inicio.strftime("%Y-%m-%d"),)).fetchone()

        reporte["uso"] = {
            "total_interacciones": rows[0] or 0,
            "sesiones_unicas": rows[1] or 0,
            "tiempo_promedio": round(rows[2] or 0, 2),
            "tokens_input_total": rows[3] or 0,
            "tokens_output_total": rows[4] or 0,
        }
    except Exception as e:
        reporte["uso"] = {"error": str(e)}

    # 2. Documentos por estado
    try:
        rows = conn.execute("""
            SELECT estado, COUNT(*) FROM procedimientos GROUP BY estado
        """).fetchall()
        reporte["documentos_por_estado"] = {r[0] or "N/A": r[1] for r in rows}
    except Exception as e:
        reporte["documentos_por_estado"] = {"error": str(e)}

    # 3. Documentos vencidos/por vencer
    try:
        rows = conn.execute("""
            SELECT codigo, nombre, fecha_vencimiento, vigencia_dias
            FROM procedimientos
            WHERE vigencia_dias IS NOT NULL AND vigencia_dias <= 30
            ORDER BY vigencia_dias ASC
            LIMIT 50
        """).fetchall()
        reporte["documentos_vencimiento"] = [
            {"codigo": r[0], "nombre": r[1], "fecha_vencimiento": r[2], "dias_restantes": r[3]}
            for r in rows
        ]
    except Exception as e:
        reporte["documentos_vencimiento"] = {"error": str(e)}

    # 4. Sincronizaciones recientes
    try:
        rows = conn.execute("""
            SELECT fecha, nuevos, modificados, eliminados, sin_cambios
            FROM sync_log
            WHERE fecha >= ?
            ORDER BY fecha DESC
        """, (fecha_inicio.strftime("%Y-%m-%d"),)).fetchall()
        reporte["sincronizaciones"] = [
            {"fecha": r[0], "nuevos": r[1], "modificados": r[2],
             "eliminados": r[3], "sin_cambios": r[4]}
            for r in rows
        ]
    except Exception as e:
        reporte["sincronizaciones"] = {"error": str(e)}

    # 5. Feedback de usuarios
    try:
        rows = conn.execute("""
            SELECT feedback, COUNT(*) FROM feedback_usuario
            WHERE timestamp >= ?
            GROUP BY feedback
        """, (fecha_inicio.strftime("%Y-%m-%d"),)).fetchall()
        reporte["feedback"] = {r[0] or "N/A": r[1] for r in rows}
    except Exception as e:
        reporte["feedback"] = {"error": str(e)}

    # 6. Chat historial (resumen)
    try:
        rows = conn.execute("""
            SELECT COUNT(*), COUNT(DISTINCT session_id)
            FROM chat_historial
            WHERE timestamp >= ?
        """, (fecha_inicio.strftime("%Y-%m-%d"),)).fetchone()
        reporte["chat"] = {
            "total_mensajes": rows[0] or 0,
            "sesiones": rows[1] or 0,
        }
    except Exception as e:
        reporte["chat"] = {"error": str(e)}

    conn.close()

    # Guardar reporte
    REPORTES_DIR.mkdir(exist_ok=True)
    filename = f"reporte_{periodo}_{fecha_fin.strftime('%Y%m%d')}.json"
    filepath = REPORTES_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"Reporte guardado en: {filepath}")

    # Generar resumen en texto
    resumen = _generar_resumen_texto(reporte)
    resumen_path = REPORTES_DIR / f"reporte_{periodo}_{fecha_fin.strftime('%Y%m%d')}.txt"
    with open(resumen_path, "w", encoding="utf-8") as f:
        f.write(resumen)
    log.info(f"Resumen guardado en: {resumen_path}")

    return reporte


def _generar_resumen_texto(reporte: dict) -> str:
    """Genera un resumen legible del reporte."""
    lines = [
        "=" * 60,
        f"  REPORTE {reporte['periodo'].upper()} - AGENTE DE CALIDAD INTEGR@",
        f"  Periodo: {reporte['fecha_inicio']} a {reporte['fecha_fin']}",
        f"  Generado: {reporte['generado']}",
        "=" * 60,
        "",
    ]

    uso = reporte.get("uso", {})
    if "error" not in uso:
        lines.extend([
            "ESTADISTICAS DE USO",
            f"  Interacciones totales: {uso.get('total_interacciones', 0)}",
            f"  Sesiones unicas: {uso.get('sesiones_unicas', 0)}",
            f"  Tiempo promedio: {uso.get('tiempo_promedio', 0)}s",
            f"  Tokens input: {uso.get('tokens_input_total', 0):,}",
            f"  Tokens output: {uso.get('tokens_output_total', 0):,}",
            "",
        ])

    docs_estado = reporte.get("documentos_por_estado", {})
    if "error" not in docs_estado:
        lines.append("DOCUMENTOS POR ESTADO")
        for estado, count in sorted(docs_estado.items()):
            lines.append(f"  {estado}: {count}")
        lines.append("")

    venc = reporte.get("documentos_vencimiento", [])
    if isinstance(venc, list) and venc:
        lines.append(f"DOCUMENTOS VENCIDOS/POR VENCER ({len(venc)})")
        for d in venc[:10]:
            dias = d.get("dias_restantes", 0)
            status = "VENCIDO" if dias < 0 else f"por vencer en {dias} dias"
            lines.append(f"  {d['codigo']} - {d['nombre'][:50]} ({status})")
        if len(venc) > 10:
            lines.append(f"  ... y {len(venc) - 10} mas")
        lines.append("")

    syncs = reporte.get("sincronizaciones", [])
    if isinstance(syncs, list) and syncs:
        lines.append(f" SINCRONIZACIONES ({len(syncs)})")
        for s in syncs[:5]:
            lines.append(f"  {s['fecha']}: {s['nuevos']} nuevos, {s['modificados']} mod, {s['eliminados']} elim")
        lines.append("")

    fb = reporte.get("feedback", {})
    if "error" not in fb and fb:
        lines.append("FEEDBACK DE USUARIOS")
        for tipo, count in fb.items():
            lines.append(f"  {tipo}: {count}")
        lines.append("")

    chat = reporte.get("chat", {})
    if "error" not in chat:
        lines.append("CHAT")
        lines.append(f"  Mensajes totales: {chat.get('total_mensajes', 0)}")
        lines.append(f"  Sesiones: {chat.get('sesiones', 0)}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generador de reportes programados")
    parser.add_argument("--periodo", choices=["semanal", "mensual"], default="semanal",
                        help="Periodo del reporte")
    args = parser.parse_args()

    reporte = generar_reporte(periodo=args.periodo)
    log.info("Reporte generado exitosamente")


if __name__ == "__main__":
    main()
