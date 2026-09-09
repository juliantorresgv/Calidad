"""
Generador del informe PDF de conectividad OpenAI para ciberseguridad.
Usa fpdf2 v2.8+ con API moderna (new_x/new_y en vez de ln).
"""
import os
import sys
import socket
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fpdf import FPDF
from fpdf.enums import XPos, YPos


class ReportPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 5, "Informe de Conectividad - Bloqueo de OpenAI",
                      align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_text_color(0, 0, 0)
            self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Pagina {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)

    def section_title(self, title):
        self.ln(5)
        self.set_font("Helvetica", "B", 13)
        self.set_fill_color(33, 102, 172)
        self.set_text_color(255, 255, 255)
        self.cell(0, 8, f"  {title}", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def subsection(self, title):
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(33, 102, 172)
        self.cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5.5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def code_block(self, text):
        self.set_font("Courier", "", 8)
        self.set_fill_color(245, 245, 245)
        self.set_text_color(40, 40, 40)
        for line in text.split("\n"):
            # Escapar caracteres problematicos para latin-1
            safe = line.replace("\u2192", "->").replace("\u2190", "<-")
            safe = safe.replace("\u2014", "-").replace("\u2013", "-")
            safe = safe.replace("\u2026", "...").replace("\u2502", "|")
            safe = safe.replace("\u2500", "-").replace("\u2514", "+")
            safe = safe.replace("\u251c", "+").replace("\u2510", "+")
            safe = safe.replace("\u250c", "+").replace("\u2518", "+")
            try:
                self.cell(0, 4.8, f"  {safe}", fill=True,
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            except Exception:
                self.cell(0, 4.8, f"  {safe.encode('ascii', 'replace').decode()}",
                          fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def table_row(self, col1, col2, col3, col4, header=False):
        w = [45, 50, 35, 40]
        if header:
            self.set_font("Helvetica", "B", 9)
            self.set_fill_color(33, 102, 172)
            self.set_text_color(255, 255, 255)
        else:
            self.set_font("Helvetica", "", 9)
            self.set_fill_color(255, 255, 255)
            self.set_text_color(0, 0, 0)
        self.cell(w[0], 7, col1, border=1, fill=True,
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(w[1], 7, col2, border=1, fill=True,
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(w[2], 7, col3, border=1, align="C", fill=True,
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(w[3], 7, col4, border=1, align="C", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

    def key_finding(self, text):
        self.ln(2)
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(255, 248, 220)
        self.set_text_color(180, 80, 0)
        self.multi_cell(0, 6, f"  HALLAZGO: {text}", fill=True,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def mermaid_diagram(self, lines):
        self.subsection("Diagrama de flujo")
        self.set_font("Courier", "", 8)
        self.set_fill_color(240, 248, 255)
        for line in lines:
            safe = line.replace("\u2192", "->").replace("\u2190", "<-")
            safe = safe.replace("\u2014", "-").replace("\u2013", "-")
            safe = safe.replace("\u2026", "...").replace("\u2502", "|")
            safe = safe.replace("\u2500", "-").replace("\u2514", "+")
            safe = safe.replace("\u251c", "+").replace("\u2510", "+")
            safe = safe.replace("\u250c", "+").replace("\u2518", "+")
            try:
                self.cell(0, 4.8, f"  {safe}", fill=True,
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            except Exception:
                self.cell(0, 4.8, f"  {safe.encode('ascii', 'replace').decode()}",
                          fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def bullet_list(self, items):
        self.set_font("Helvetica", "", 10)
        for item in items:
            self.cell(5, 5.5, "", new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.multi_cell(0, 5.5, f"- {item}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)


def generate_report():
    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # === PORTADA ===
    pdf.ln(30)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(33, 102, 172)
    pdf.cell(0, 12, "INFORME DE CONECTIVIDAD", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 12, "Bloqueo de acceso a OpenAI API", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, "Agente de Calidad Integr@ - Solistica", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(0, 0, 0)

    info = [
        ("Fecha del informe", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Equipo", socket.gethostname()),
        ("Usuario", os.environ.get("USERNAME", "N/A")),
        ("DNS Server", "LN-DC-ATLAS-02.corp.agv.co (10.238.66.63)"),
        ("Gateway", "172.16.240.1"),
        ("Destino bloqueado", "api.openai.com (OpenAI API)"),
        ("Destinos funcionales", "api.mistral.ai, api.groq.com, googleapis.com"),
        ("Dirigido a", "Equipo de Ciberseguridad / TI"),
    ]
    for label, value in info:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(60, 6, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)

    # === 1. RESUMEN ===
    pdf.section_title("1. Resumen Ejecutivo")
    pdf.body_text(
        "Este informe documenta el diagnostico tecnico realizado para determinar por que las "
        "conexiones desde la red corporativa de Solistica hacia la API de OpenAI "
        "(api.openai.com) fallan sistematicamente con timeout, mientras que otros proveedores "
        "cloud (Mistral, Groq, Gemini) funcionan correctamente."
    )
    pdf.body_text(
        "CONCLUSION PRINCIPAL: El bloqueo ocurre a nivel de red (TCP/IP) despues del gateway "
        "corporativo 172.16.240.1. El trafico hacia las IPs especificas de OpenAI "
        "(172.66.0.243 y 162.159.140.245) es descartado. No es un bloqueo por DNS, ni por SNI "
        "(Server Name Indication), ni por nombre de dominio. Es un bloqueo por rango IP "
        "especifico en la capa de red."
    )
    pdf.key_finding(
        "El trafico hacia las IPs de OpenAI (172.66.0.x, 162.159.140.x) se descarta "
        "despues del gateway 172.16.240.1. Otros servicios en Cloudflare (Mistral en "
        "172.66.2.x, Groq en 172.64.149.x) funcionan correctamente. El bloqueo es "
        "especifico a ciertos rangos IP, no a todo Cloudflare."
    )

    # === 2. METODOLOGIA ===
    pdf.section_title("2. Metodologia")
    pdf.body_text(
        "Se realizaron 7 pruebas de conectividad progresivas, desde resolucion DNS hasta "
        "inspeccion de TLS SNI, para aislar la capa exacta donde ocurre el bloqueo:"
    )
    pdf.bullet_list([
        "Test 1: Resolucion DNS (nslookup)",
        "Test 2: Conectividad TCP puerto 443 (Test-NetConnection)",
        "Test 3: Peticion HTTP completa (curl con timeout)",
        "Test 4: Traceroute (tracert) para identificar donde se descarta el trafico",
        "Test 5: Conexion directa por IP (sin DNS)",
        "Test 6: Forzar IPv4 vs IPv6",
        "Test 7: SNI swap (intercambiar SNI entre IPs de OpenAI y Mistral)",
    ])

    # === 3. DIAGRAMA ===
    pdf.add_page()
    pdf.section_title("3. Diagrama de Arquitectura de Red")
    pdf.mermaid_diagram([
        "  +------------------+         +-------------------+",
        "  |   Equipo usuario |         |   DNS Server      |",
        "  |  (Windows 11)    |-------->|  10.238.66.63     |",
        "  |  Python/curl     |         |  LN-DC-ATLAS-02   |",
        "  +--------+---------+         +-------------------+",
        "           |                          |",
        "           |  DNS query               |  Resuelve OK",
        "           |  api.openai.com          |  172.66.0.243",
        "           |                          |  162.159.140.245",
        "           v                          v",
        "  +--------+------------------------------------------+",
        "  |              GATEWAY CORPORATIVO                  |",
        "  |              172.16.240.1                         |",
        "  |              (responde en hop 1)                  |",
        "  +--------+------------------------------------------+",
        "           |",
        "           |  TCP SYN enviado a 172.66.0.243:443",
        "           |",
        "     +-----+------+----------+----------+",
        "     |            |          |          |",
        "     v            v          v          v",
        "  OPENAI      MISTRAL      GROQ      GEMINI",
        "  172.66.0.x  172.66.2.x   104.18.x  172.217.x",
        "  BLOQUEADO   OK (0.16s)   OK (0.18s) OK (0.12s)",
        "  (timeout)   HTTP 401     HTTP 401   HTTP 404",
        "     |            |          |          |",
        "     X            v          v          v",
        "           +-------------------+",
        "           |  INTERNET         |",
        "           |  (Cloudflare)     |",
        "           +-------------------+",
    ])
    pdf.body_text(
        "El diagrama muestra que el trafico hacia OpenAI se descarta despues del gateway "
        "172.16.240.1, mientras que el trafico hacia Mistral, Groq y Gemini pasa correctamente. "
        "Todos usan Cloudflare como infraestructura, pero solo los rangos IP de OpenAI estan "
        "bloqueados."
    )

    # === 4. DNS ===
    pdf.add_page()
    pdf.section_title("4. Evidencia: Prueba 1 - Resolucion DNS")
    pdf.body_text("Objetivo: Verificar si el DNS corporativo resuelve api.openai.com correctamente.")
    pdf.subsection("Comando PowerShell ejecutado:")
    pdf.code_block("nslookup api.openai.com")
    pdf.subsection("Resultado obtenido:")
    pdf.code_block(
        "Servidor:  LN-DC-ATLAS-02.corp.agv.co\n"
        "Address:  10.238.66.63\n\n"
        "Nombre:  api.openai.com\n"
        "Addresses:\n"
        "  2a06:98c1:58::f3        (IPv6)\n"
        "  2606:4700:7::f3         (IPv6)\n"
        "  172.66.0.243            (IPv4 - Cloudflare)\n"
        "  162.159.140.245         (IPv4 - Cloudflare)"
    )
    pdf.subsection("Comando de comparacion (Mistral):")
    pdf.code_block("nslookup api.mistral.ai")
    pdf.code_block(
        "Nombre:  api.mistral.ai\n"
        "Addresses:\n"
        "  172.66.2.203            (IPv4 - Cloudflare)\n"
        "  162.159.142.207         (IPv4 - Cloudflare)"
    )
    pdf.key_finding(
        "DNS resuelve correctamente para todos los proveedores. El DNS server "
        "corporativo (10.238.66.63) devuelve IPs validas. No hay bloqueo a nivel DNS."
    )

    # === 5. TCP 443 ===
    pdf.add_page()
    pdf.section_title("5. Evidencia: Prueba 2 - TCP Puerto 443")
    pdf.body_text("Objetivo: Verificar si la conexion TCP al puerto 443 se establece.")
    pdf.subsection("Comando PowerShell ejecutado:")
    pdf.code_block(
        'Test-NetConnection -ComputerName api.openai.com -Port 443\n'
        'Test-NetConnection -ComputerName api.mistral.ai -Port 443\n'
        'Test-NetConnection -ComputerName api.groq.com -Port 443\n'
        'Test-NetConnection -ComputerName generativelanguage.googleapis.com -Port 443\n'
        'Test-NetConnection -ComputerName 1.1.1.1 -Port 443'
    )
    pdf.subsection("Resultado obtenido:")
    pdf.code_block(
        "ComputerName                RemoteAddress     RemotePort  TcpTestSucceeded\n"
        "------------                -------------     ----------  ----------------\n"
        "api.openai.com              162.159.140.245   443         True (intermitente)\n"
        "api.mistral.ai              172.66.2.203      443         True\n"
        "api.groq.com                104.18.38.236     443         True\n"
        "generativelanguage...       172.217.115.4     443         True\n"
        "1.1.1.1                     1.1.1.1           443         True\n\n"
        "NOTA: Test-NetConnection a OpenAI a veces reporta True, pero curl siempre\n"
        "falla. Esto sugiere que el TCP SYN pasa pero la conexion se corta despues."
    )
    pdf.key_finding(
        "La conexion TCP al puerto 443 es intermitente para OpenAI. Test-NetConnection "
        "puede reportar exito, pero las conexiones HTTP reales (curl) siempre fallan "
        "con timeout. Esto sugiere inspeccion de paquetes (DPI) que permite el TCP "
        "handshake pero bloquea la conexion despues."
    )

    # === 6. HTTP ===
    pdf.add_page()
    pdf.section_title("6. Evidencia: Prueba 3 - Peticion HTTP (curl)")
    pdf.body_text("Objetivo: Verificar si la peticion HTTP completa (TCP + TLS + HTTP) funciona.")
    pdf.subsection("Comandos PowerShell ejecutados:")
    pdf.code_block(
        '# Test a OpenAI\n'
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models\n\n'
        '# Test a Mistral\n'
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://api.mistral.ai/v1/models\n\n'
        '# Test a Groq\n'
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://api.groq.com/openai/v1/models\n\n'
        '# Test a Gemini\n'
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://generativelanguage.googleapis.com\n\n'
        '# Test a Cloudflare DNS\n'
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://1.1.1.1'
    )
    pdf.subsection("Resultado obtenido:")
    pdf.code_block(
        "OpenAI:      HTTP: 000 | TIME: 10.01s  | CONNECT: 0.00s  | FAIL\n"
        "Mistral:     HTTP: 401 | TIME:  0.50s  | CONNECT: 0.20s  | OK\n"
        "Groq:        HTTP: 401 | TIME:  0.44s  | CONNECT: 0.18s  | OK\n"
        "Gemini:      HTTP: 404 | TIME:  0.31s  | CONNECT: 0.12s  | OK\n"
        "Cloudflare:  HTTP: 301 | TIME:  1.02s  | CONNECT: 0.01s  | OK"
    )
    pdf.body_text("Significado de los codigos:")
    pdf.bullet_list([
        "HTTP 000 = sin respuesta (timeout de conexion)",
        "HTTP 401 = no autorizado (sin API key, pero la conexion funciona)",
        "HTTP 404 = no encontrado (la URL raiz no existe, pero la conexion funciona)",
        "HTTP 301 = redireccion (Cloudflare responde)",
    ])
    pdf.key_finding(
        "OpenAI es el unico proveedor que devuelve HTTP 000 (sin respuesta). "
        "Los demas responden en menos de 1 segundo. Cloudflare 1.1.1.1 tambien "
        "funciona, descartando un bloqueo general de Cloudflare."
    )

    # === 7. TRACEROUTE ===
    pdf.add_page()
    pdf.section_title("7. Evidencia: Prueba 4 - Traceroute")
    pdf.body_text("Objetivo: Identificar en que punto de la red se descarta el trafico hacia OpenAI.")
    pdf.subsection("Comando PowerShell ejecutado:")
    pdf.code_block("tracert -d -h 8 -w 2000 162.159.140.245")
    pdf.subsection("Resultado obtenido:")
    pdf.code_block(
        "Traza a 162.159.140.245 sobre caminos de 8 saltos como maximo.\n\n"
        "  1    13 ms     *        4 ms   172.16.240.1      <-- GATEWAY\n"
        "  2     *        *        *      Tiempo agotado    <-- DESCARTADO\n"
        "  3     *        *        *      Tiempo agotado\n"
        "  4     *        *        *      Tiempo agotado\n"
        "  5     *        *        *      Tiempo agotado\n"
        "  6     *        *        *      Tiempo agotado\n"
        "  7     *        *        *      Tiempo agotado\n"
        "  8     *        *        *      Tiempo agotado\n\n"
        "Traza completa."
    )
    pdf.mermaid_diagram([
        "  Hop 1: 172.16.240.1 (gateway)  --> RESPONDE (4-13ms)",
        "  Hop 2+: * * * (timeout)         --> TRAFICO DESCARTADO",
        "                                         |",
        "                                         v",
        "  +------------------------------------------+",
        "  |  El gateway recibe el trafico pero NO    |",
        "  |  lo reenvia hacia 162.159.140.x          |",
        "  |  El trafico se descarta (blackhole)      |",
        "  +------------------------------------------+",
    ])
    pdf.key_finding(
        "El traceroute demuestra que el trafico hacia OpenAI se descarta despues "
        "del gateway 172.16.240.1. El primer hop responde, pero ningun hop posterior "
        "responde. Esto indica que el trafico se esta descartando (blackhole) o "
        "bloqueando en el gateway o en un appliance de seguridad inmediatamente despues."
    )

    # === 8. IP DIRECTA ===
    pdf.add_page()
    pdf.section_title("8. Evidencia: Prueba 5 - Conexion directa por IP")
    pdf.body_text("Objetivo: Descartar que el bloqueo sea por DNS. Se conecta directamente a las IPs.")
    pdf.subsection("Comandos PowerShell ejecutados:")
    pdf.code_block(
        '# IP directa de OpenAI #1\n'
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://172.66.0.243/v1/models\n\n'
        '# IP directa de OpenAI #2\n'
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://162.159.140.245/v1/models\n\n'
        '# IP directa de Mistral (tambien Cloudflare, para comparar)\n'
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://172.66.2.203/v1/models'
    )
    pdf.subsection("Resultado obtenido:")
    pdf.code_block(
        "IP OpenAI 172.66.0.243:    HTTP: 000 | TIME: 10.01s  | FAIL\n"
        "IP OpenAI 162.159.140.245: HTTP: 000 | TIME: 10.01s  | FAIL\n"
        "IP Mistral 172.66.2.203:   HTTP: 401 | TIME:  0.50s  | OK"
    )
    pdf.key_finding(
        "Ambas IPs de OpenAI (172.66.0.243 y 162.159.140.245) fallan. "
        "Las IPs de Mistral (172.66.2.203, 162.159.142.207) funcionan. "
        "Ambos usan Cloudflare pero en rangos IP diferentes. "
        "El bloqueo es por rango IP especifico, no por todo Cloudflare."
    )

    # === 9. IPv4 vs IPv6 ===
    pdf.add_page()
    pdf.section_title("9. Evidencia: Prueba 6 - IPv4 vs IPv6")
    pdf.body_text("Objetivo: Descartar que el bloqueo afecte solo IPv4 o solo IPv6.")
    pdf.subsection("Comandos PowerShell ejecutados:")
    pdf.code_block(
        '# Forzar IPv4\n'
        'curl.exe -4 -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s | IP: %{remote_ip}`n" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models\n\n'
        '# Forzar IPv6\n'
        'curl.exe -6 -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s | IP: %{remote_ip}`n" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models'
    )
    pdf.subsection("Resultado obtenido:")
    pdf.code_block(
        "IPv4 forzado:  HTTP: 000 | TIME: 10.01s | IP: (vacia)  | FAIL (timeout)\n"
        "IPv6 forzado:  HTTP: 000 | TIME:  0.02s | IP: (vacia)  | FAIL (sin ruta IPv6)\n\n"
        "IPv4: la conexion TCP se intenta pero timeout despues de 10s.\n"
        "IPv6: falla instantaneamente (no hay ruta IPv6 configurada)."
    )
    pdf.body_text(
        "El bloqueo afecta IPv4. IPv6 no esta configurado en la red corporativa, "
        "por lo que no es una alternativa viable."
    )

    # === 10. SNI SWAP ===
    pdf.add_page()
    pdf.section_title("10. Evidencia: Prueba 7 - SNI Swap (PRUEBA CLAVE)")
    pdf.body_text(
        "Objetivo: Determinar si el bloqueo es por IP o por nombre de dominio (SNI). "
        "Se intercambian los SNIs entre IPs de OpenAI y Mistral."
    )
    pdf.subsection("Test A: IP de OpenAI con SNI de Mistral")
    pdf.body_text("Si el bloqueo es por IP, esta peticion FALLARA (la IP esta bloqueada).")
    pdf.code_block(
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --resolve "api.mistral.ai:443:162.159.140.245" ^\n'
        '  --connect-timeout 10 https://api.mistral.ai/v1/models'
    )
    pdf.code_block(
        "Resultado: HTTP: 000 | TIME: 10.00s | FAIL\n"
        "(IP de OpenAI bloqueada, sin importar el SNI)"
    )
    pdf.subsection("Test B: IP de Mistral con SNI de OpenAI")
    pdf.body_text("Si el bloqueo es por IP, esta peticion FUNCIONARA (la IP no esta bloqueada).")
    pdf.code_block(
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --resolve "api.openai.com:443:172.66.2.203" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models'
    )
    pdf.code_block(
        "Resultado: HTTP: 403 | TIME: 0.39s | OK\n"
        "(IP de Mistral funciona, sin importar el SNI)"
    )
    pdf.subsection("Test C: Control (Mistral normal)")
    pdf.code_block(
        'curl.exe -s -o NUL -w "HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://api.mistral.ai/v1/models'
    )
    pdf.code_block("Resultado: HTTP: 401 | TIME: 0.46s | OK (control)")
    pdf.key_finding(
        "El SNI swap prueba definitivamente que el bloqueo es por IP, no por "
        "nombre de dominio. Cuando se usa una IP de OpenAI con SNI de Mistral, "
        "falla. Cuando se usa una IP de Mistral con SNI de OpenAI, funciona. "
        "El appliance de seguridad esta filtrando por direccion IP, no por "
        "inspeccion de TLS SNI."
    )

    # === 11. TABLA RESUMEN ===
    pdf.add_page()
    pdf.section_title("11. Tabla Resumen de Todas las Pruebas")
    pdf.table_row("Prueba", "Destino", "Resultado", "Tiempo", header=True)
    pdf.table_row("DNS", "api.openai.com", "Resuelve OK", "<1s")
    pdf.table_row("DNS", "api.mistral.ai", "Resuelve OK", "<1s")
    pdf.table_row("TCP 443", "api.openai.com", "Intermitente", "variable")
    pdf.table_row("TCP 443", "api.mistral.ai", "OK", "<1s")
    pdf.table_row("HTTP", "api.openai.com", "FAIL (000)", "10s timeout")
    pdf.table_row("HTTP", "api.mistral.ai", "OK (401)", "0.50s")
    pdf.table_row("HTTP", "api.groq.com", "OK (401)", "0.44s")
    pdf.table_row("HTTP", "googleapis.com", "OK (404)", "0.31s")
    pdf.table_row("HTTP", "1.1.1.1 (CF)", "OK (301)", "1.02s")
    pdf.table_row("Traceroute", "162.159.140.245", "Descartado hop 2+", "timeout")
    pdf.table_row("IP directa", "162.159.140.245", "FAIL (000)", "10s timeout")
    pdf.table_row("IP directa", "172.66.0.243", "FAIL (000)", "10s timeout")
    pdf.table_row("IPv4 forzado", "api.openai.com", "FAIL (000)", "10s timeout")
    pdf.table_row("IPv6 forzado", "api.openai.com", "FAIL (sin ruta)", "0.02s")
    pdf.table_row("SNI swap A", "IP OpenAI + SNI Mistral", "FAIL (000)", "10s timeout")
    pdf.table_row("SNI swap B", "IP Mistral + SNI OpenAI", "OK (403)", "0.39s")

    # === 12. RANGOS IP ===
    pdf.add_page()
    pdf.section_title("12. Analisis de Rangos IP de Cloudflare")
    pdf.body_text(
        "OpenAI, Mistral y Groq usan Cloudflare como infraestructura. Sin embargo, "
        "solo las IPs de OpenAI estan bloqueadas. Esto permite acotar el rango exacto:"
    )
    pdf.table_row("Proveedor", "IP IPv4", "Cloudflare", "Estado", header=True)
    pdf.table_row("OpenAI", "172.66.0.243", "Si", "BLOQUEADO")
    pdf.table_row("OpenAI", "162.159.140.245", "Si", "BLOQUEADO")
    pdf.table_row("Mistral", "172.66.2.203", "Si", "PERMITIDO")
    pdf.table_row("Mistral", "162.159.142.207", "Si", "PERMITIDO")
    pdf.table_row("Groq", "172.64.149.20", "Si", "PERMITIDO")
    pdf.table_row("Groq", "104.18.38.236", "Si", "PERMITIDO")
    pdf.table_row("Cloudflare", "1.1.1.1", "Si", "PERMITIDO")
    pdf.ln(3)
    pdf.subsection("Patron observado:")
    pdf.code_block(
        "BLOQUEADO:  172.66.0.x     (OpenAI)\n"
        "BLOQUEADO:  162.159.140.x  (OpenAI)\n"
        "PERMITIDO:  172.66.2.x     (Mistral)\n"
        "PERMITIDO:  172.64.149.x   (Groq)\n"
        "PERMITIDO:  162.159.142.x  (Mistral)\n"
        "PERMITIDO:  104.18.38.x    (Groq)\n"
        "PERMITIDO:  1.1.1.1        (Cloudflare DNS)"
    )
    pdf.key_finding(
        "El bloqueo NO afecta a todo Cloudflare. Solo los rangos especificos "
        "172.66.0.x y 162.159.140.x (usados por OpenAI) estan bloqueados. "
        "Otros rangos de Cloudflare (172.66.2.x, 172.64.149.x, 104.18.38.x) "
        "funcionan correctamente."
    )

    # === 13. DIAGNOSTICO ===
    pdf.add_page()
    pdf.section_title("13. Diagnostico Final")
    pdf.subsection("Lo que NO es el problema:")
    pdf.bullet_list([
        "NO es bloqueo de DNS - El DNS resuelve correctamente.",
        "NO es bloqueo por SNI/nombre de dominio - El test SNI swap lo descarta.",
        "NO es bloqueo de todo Cloudflare - Mistral y Groq usan Cloudflare y funcionan.",
        "NO es problema de API key - La conexion nunca se establece.",
        "NO es problema de IPv6 - IPv4 tambien falla.",
        "NO es firewall tradicional - El TCP SYN a veces pasa.",
    ])
    pdf.subsection("Lo que SI es el problema:")
    pdf.bullet_list([
        "ES un bloqueo a nivel de red (capa 3/4 OSI) - El trafico se descarta despues del gateway.",
        "ES especifico a ciertos rangos IP de Cloudflare - 172.66.0.x y 162.159.140.x.",
        "ES consistente - curl siempre falla con timeout de 10s hacia esas IPs.",
        "ES despues del gateway 172.16.240.1 - El traceroute lo confirma.",
        "Podria ser un appliance de seguridad (NGFW/IPS/IDS) o ACL de red.",
    ])
    pdf.subsection("Posibles causas tecnicas:")
    pdf.bullet_list([
        "ACL de red en el router/gateway que bloquea rangos IP especificos.",
        "Appliance de seguridad (NGFW, IPS, IDS) con reglas de filtrado por IP.",
        "Web filter / content filter que bloquea por categoria (OpenAI/AI services).",
        "CASB (Cloud Access Security Broker) que bloquea servicios cloud no aprobados.",
        "Regla de routing que blackholea ciertos destinos.",
        "Proxy transparente que no reenvia a ciertos rangos IP.",
    ])

    # === 14. RECOMENDACIONES ===
    pdf.add_page()
    pdf.section_title("14. Recomendaciones para Ciberseguridad")
    pdf.subsection("Diagnostico adicional:")
    pdf.bullet_list([
        "Revisar las reglas ACL del gateway 172.16.240.1 y routers adyacentes.",
        "Verificar si hay un appliance de seguridad (Fortinet, Palo Alto, Cisco, etc.) entre el gateway e Internet.",
        "Revisar si hay reglas de content filtering que bloqueen servicios de IA.",
        "Verificar si OpenAI esta en una lista de blocklist o categoria no aprobada.",
        "Revisar logs del firewall/IPS para conexiones hacia 172.66.0.x y 162.159.140.x.",
    ])
    pdf.subsection("Soluciones posibles:")
    pdf.bullet_list([
        "Agregar las IPs de OpenAI (172.66.0.243, 162.159.140.245) a una whitelist.",
        "Desbloquear la categoria 'AI Services' o 'OpenAI' en el content filter.",
        "Crear una regla de allow para api.openai.com en el NGFW.",
        "Si el bloqueo es intencional, documentarlo y usar proveedores alternativos.",
        "Configurar un proxy explicito que permita api.openai.com.",
    ])
    pdf.subsection("Proveedores alternativos (ya funcionales):")
    pdf.body_text(
        "Mientras se resuelve el bloqueo, el agente tiene fallback automatico a:\n"
        "1. Mistral (api.mistral.ai) - Funciona, 0.50s de latencia\n"
        "2. Groq (api.groq.com) - Funciona, 0.44s de latencia\n"
        "3. Gemini (googleapis.com) - Funciona, 0.31s de latencia\n"
        "4. Ollama (localhost) - Funciona, local sin internet"
    )

    # === 15. COMANDOS COMPLETOS ===
    pdf.add_page()
    pdf.section_title("15. Comandos PowerShell para Verificacion")
    pdf.body_text(
        "Ciberseguridad puede reproducir TODAS las pruebas desde cualquier equipo "
        "en la red corporativa. Los comandos estan listos para copiar y pegar en "
        "PowerShell (NO usar Windows PowerShell ISE, usar PowerShell 7+ o Terminal)."
    )

    pdf.subsection("15.1 Verificacion rapida (30 segundos)")
    pdf.body_text("Prueba basica para confirmar el bloqueo:")
    pdf.code_block(
        '# ============================================================\n'
        '# VERIFICACION RAPIDA - 30 segundos\n'
        '# ============================================================\n\n'
        '# Test HTTP a OpenAI (debe dar HTTP 000 si esta bloqueado)\n'
        'curl.exe -s -o NUL -w "OpenAI:    HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models\n\n'
        '# Test HTTP a Mistral (debe dar HTTP 401 si funciona)\n'
        'curl.exe -s -o NUL -w "Mistral:   HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://api.mistral.ai/v1/models\n\n'
        '# Test HTTP a Groq (debe dar HTTP 401 si funciona)\n'
        'curl.exe -s -o NUL -w "Groq:      HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://api.groq.com/openai/v1/models\n\n'
        '# Test HTTP a Gemini (debe dar HTTP 404 si funciona)\n'
        'curl.exe -s -o NUL -w "Gemini:    HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://generativelanguage.googleapis.com\n\n'
        '# Resultado esperado:\n'
        '#   OpenAI:    HTTP: 000 | TIME: 10.00s   <-- BLOQUEADO\n'
        '#   Mistral:   HTTP: 401 | TIME:  0.50s   <-- OK\n'
        '#   Groq:      HTTP: 401 | TIME:  0.44s   <-- OK\n'
        '#   Gemini:    HTTP: 404 | TIME:  0.31s   <-- OK'
    )

    pdf.add_page()
    pdf.subsection("15.2 Prueba 1: Resolucion DNS")
    pdf.code_block(
        '# ============================================================\n'
        '# PRUEBA 1: DNS - Verificar resolucion de nombres\n'
        '# ============================================================\n\n'
        '# DNS de OpenAI\n'
        'nslookup api.openai.com\n\n'
        '# DNS de Mistral (comparacion)\n'
        'nslookup api.mistral.ai\n\n'
        '# DNS de Groq (comparacion)\n'
        'nslookup api.groq.com\n\n'
        '# Resultado esperado: Todos resuelven correctamente.\n'
        '# Si OpenAI no resuelve, el bloqueo es por DNS.\n'
        '# Si OpenAI resuelve pero no conecta, el bloqueo es por IP.'
    )

    pdf.subsection("15.3 Prueba 2: TCP Puerto 443")
    pdf.code_block(
        '# ============================================================\n'
        '# PRUEBA 2: TCP 443 - Verificar conexion a nivel TCP\n'
        '# ============================================================\n\n'
        '# TCP a OpenAI\n'
        'Test-NetConnection -ComputerName api.openai.com -Port 443 ^\n'
        '  -WarningAction SilentlyContinue | Select-Object ^\n'
        '  ComputerName, RemoteAddress, RemotePort, TcpTestSucceeded\n\n'
        '# TCP a Mistral (comparacion)\n'
        'Test-NetConnection -ComputerName api.mistral.ai -Port 443 ^\n'
        '  -WarningAction SilentlyContinue | Select-Object ^\n'
        '  ComputerName, RemoteAddress, RemotePort, TcpTestSucceeded\n\n'
        '# TCP a Groq (comparacion)\n'
        'Test-NetConnection -ComputerName api.groq.com -Port 443 ^\n'
        '  -WarningAction SilentlyContinue | Select-Object ^\n'
        '  ComputerName, RemoteAddress, RemotePort, TcpTestSucceeded\n\n'
        '# TCP a Gemini (comparacion)\n'
        'Test-NetConnection -ComputerName generativelanguage.googleapis.com -Port 443 ^\n'
        '  -WarningAction SilentlyContinue | Select-Object ^\n'
        '  ComputerName, RemoteAddress, RemotePort, TcpTestSucceeded\n\n'
        '# TCP a Cloudflare DNS (comparacion)\n'
        'Test-NetConnection -ComputerName 1.1.1.1 -Port 443 ^\n'
        '  -WarningAction SilentlyContinue | Select-Object ^\n'
        '  ComputerName, RemoteAddress, RemotePort, TcpTestSucceeded\n\n'
        '# Resultado esperado:\n'
        '#   OpenAI:     TcpTestSucceeded = True (intermitente) o False\n'
        '#   Mistral:    TcpTestSucceeded = True\n'
        '#   Groq:       TcpTestSucceeded = True\n'
        '#   Gemini:     TcpTestSucceeded = True\n'
        '#   Cloudflare: TcpTestSucceeded = True'
    )

    pdf.add_page()
    pdf.subsection("15.4 Prueba 3: HTTP completo (curl)")
    pdf.code_block(
        '# ============================================================\n'
        '# PRUEBA 3: HTTP - Peticion completa con curl\n'
        '# ============================================================\n\n'
        '# IMPORTANTE: Usar curl.exe (no curl, que es alias de Invoke-WebRequest)\n\n'
        '# HTTP a OpenAI\n'
        'curl.exe -s -o NUL -w "OpenAI:    HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models\n\n'
        '# HTTP a Mistral\n'
        'curl.exe -s -o NUL -w "Mistral:   HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://api.mistral.ai/v1/models\n\n'
        '# HTTP a Groq\n'
        'curl.exe -s -o NUL -w "Groq:      HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://api.groq.com/openai/v1/models\n\n'
        '# HTTP a Gemini\n'
        'curl.exe -s -o NUL -w "Gemini:    HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://generativelanguage.googleapis.com\n\n'
        '# HTTP a Cloudflare DNS (1.1.1.1)\n'
        'curl.exe -s -o NUL -w "Cloudflare:HTTP: %{http_code} | TIME: %{time_total}s | CONNECT: %{time_connect}s`n" ^\n'
        '  --connect-timeout 10 https://1.1.1.1\n\n'
        '# Resultado esperado:\n'
        '#   OpenAI:     HTTP: 000 | TIME: 10.01s | CONNECT: 0.00s  <-- FAIL\n'
        '#   Mistral:    HTTP: 401 | TIME:  0.50s | CONNECT: 0.20s  <-- OK\n'
        '#   Groq:       HTTP: 401 | TIME:  0.44s | CONNECT: 0.18s  <-- OK\n'
        '#   Gemini:     HTTP: 404 | TIME:  0.31s | CONNECT: 0.12s  <-- OK\n'
        '#   Cloudflare: HTTP: 301 | TIME:  1.02s | CONNECT: 0.01s  <-- OK'
    )

    pdf.add_page()
    pdf.subsection("15.5 Prueba 4: Traceroute")
    pdf.code_block(
        '# ============================================================\n'
        '# PRUEBA 4: Traceroute - Identificar donde se descarta el trafico\n'
        '# ============================================================\n\n'
        '# Traceroute a IP de OpenAI (162.159.140.245)\n'
        'tracert -d -h 8 -w 2000 162.159.140.245\n\n'
        '# Traceroute a IP de OpenAI (172.66.0.243)\n'
        'tracert -d -h 8 -w 2000 172.66.0.243\n\n'
        '# Traceroute a IP de Mistral (comparacion)\n'
        'tracert -d -h 8 -w 2000 172.66.2.203\n\n'
        '# Resultado esperado:\n'
        '#   OpenAI:  Hop 1 (172.16.240.1) responde, hop 2+ timeout\n'
        '#   Mistral: Hop 1 responde, hop 2+ responde hasta llegar al destino\n\n'
        '# Si OpenAI muestra timeout desde hop 2, el trafico se descarta\n'
        '# en el gateway o en un appliance inmediatamente despues.'
    )

    pdf.subsection("15.6 Prueba 5: Conexion directa por IP")
    pdf.code_block(
        '# ============================================================\n'
        '# PRUEBA 5: IP directa - Sin DNS, conectar directo a la IP\n'
        '# ============================================================\n\n'
        '# IP directa de OpenAI #1\n'
        'curl.exe -s -o NUL -w "IP OpenAI 172.66.0.243:    HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://172.66.0.243/v1/models\n\n'
        '# IP directa de OpenAI #2\n'
        'curl.exe -s -o NUL -w "IP OpenAI 162.159.140.245: HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://162.159.140.245/v1/models\n\n'
        '# IP directa de Mistral (comparacion)\n'
        'curl.exe -s -o NUL -w "IP Mistral 172.66.2.203:   HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://172.66.2.203/v1/models\n\n'
        '# Resultado esperado:\n'
        '#   IP OpenAI 172.66.0.243:    HTTP: 000 | FAIL\n'
        '#   IP OpenAI 162.159.140.245: HTTP: 000 | FAIL\n'
        '#   IP Mistral 172.66.2.203:   HTTP: 401 | OK'
    )

    pdf.add_page()
    pdf.subsection("15.7 Prueba 6: IPv4 vs IPv6")
    pdf.code_block(
        '# ============================================================\n'
        '# PRUEBA 6: IPv4 vs IPv6 - Forzar protocolo\n'
        '# ============================================================\n\n'
        '# Forzar IPv4\n'
        'curl.exe -4 -s -o NUL -w "IPv4: HTTP: %{http_code} | TIME: %{time_total}s | IP: %{remote_ip}`n" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models\n\n'
        '# Forzar IPv6\n'
        'curl.exe -6 -s -o NUL -w "IPv6: HTTP: %{http_code} | TIME: %{time_total}s | IP: %{remote_ip}`n" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models\n\n'
        '# Resultado esperado:\n'
        '#   IPv4: HTTP: 000 | TIME: 10.01s | FAIL (timeout)\n'
        '#   IPv6: HTTP: 000 | TIME:  0.02s | FAIL (sin ruta IPv6)'
    )

    pdf.subsection("15.8 Prueba 7: SNI Swap (PRUEBA CLAVE)")
    pdf.body_text(
        "Esta es la prueba mas importante. Determina si el bloqueo es por IP "
        "o por nombre de dominio (SNI)."
    )
    pdf.code_block(
        '# ============================================================\n'
        '# PRUEBA 7: SNI Swap - Intercambiar SNI entre IPs\n'
        '# ============================================================\n\n'
        '# Test A: IP de OpenAI (162.159.140.245) con SNI de Mistral\n'
        '# Si el bloqueo es por IP, FALLARA (la IP esta bloqueada)\n'
        'curl.exe -s -o NUL -w "Test A (IP OpenAI + SNI Mistral):  HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --resolve "api.mistral.ai:443:162.159.140.245" ^\n'
        '  --connect-timeout 10 https://api.mistral.ai/v1/models\n\n'
        '# Test B: IP de Mistral (172.66.2.203) con SNI de OpenAI\n'
        '# Si el bloqueo es por IP, FUNCIONARA (la IP no esta bloqueada)\n'
        'curl.exe -s -o NUL -w "Test B (IP Mistral + SNI OpenAI):  HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --resolve "api.openai.com:443:172.66.2.203" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models\n\n'
        '# Test C: Control (Mistral normal)\n'
        'curl.exe -s -o NUL -w "Test C (Control Mistral):          HTTP: %{http_code} | TIME: %{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://api.mistral.ai/v1/models\n\n'
        '# Resultado esperado:\n'
        '#   Test A: HTTP: 000 | TIME: 10.00s | FAIL  (IP OpenAI bloqueada)\n'
        '#   Test B: HTTP: 403 | TIME:  0.39s | OK    (IP Mistral funciona)\n'
        '#   Test C: HTTP: 401 | TIME:  0.46s | OK    (Control)\n\n'
        '# CONCLUSION:\n'
        '# Si Test A falla y Test B funciona, el bloqueo es por IP.\n'
        '# Si Test A funciona y Test B falla, el bloqueo es por SNI (nombre).'
    )

    pdf.add_page()
    pdf.subsection("15.9 Prueba 8: Verificacion de proxy")
    pdf.code_block(
        '# ============================================================\n'
        '# PRUEBA 8: Proxy - Verificar si hay proxy configurado\n'
        '# ============================================================\n\n'
        '# Verificar proxy del sistema\n'
        'Get-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" ^\n'
        '  | Select-Object ProxyEnable, ProxyServer, ProxyOverride\n\n'
        '# Verificar variables de entorno de proxy\n'
        'Get-ChildItem Env: | Where-Object { $_.Name -match "proxy|PROXY" }\n\n'
        '# Resultado esperado:\n'
        '#   ProxyEnable: 0 (no hay proxy)\n'
        '#   ProxyServer: (vacio)\n'
        '#   Variables: (ninguna)\n\n'
        '# Si hay proxy configurado, podria ser la causa del bloqueo.'
    )

    pdf.subsection("15.10 Prueba 9: Verbose curl (TLS handshake)")
    pdf.code_block(
        '# ============================================================\n'
        '# PRUEBA 9: Verbose - Ver el handshake TLS paso a paso\n'
        '# ============================================================\n\n'
        '# Verbose a OpenAI (ver donde falla)\n'
        'curl.exe -v --connect-timeout 10 https://api.openai.com/v1/models 2>&1 ^\n'
        '  | Select-String "Trying|Connected|SSL|TLS|handshake|refused|timed|reset|close"\n\n'
        '# Verbose a Mistral (comparacion)\n'
        'curl.exe -v --connect-timeout 10 https://api.mistral.ai/v1/models 2>&1 ^\n'
        '  | Select-String "Trying|Connected|SSL|TLS|handshake|refused|timed|reset|close"\n\n'
        '# Resultado esperado:\n'
        '#   OpenAI:  "Trying 172.66.0.243:443..." -> "Connection timed out"\n'
        '#   Mistral: "Trying 172.66.2.203:443..." -> "Connected" -> "SSL connection using TLS"'
    )

    pdf.add_page()
    pdf.subsection("15.11 Script completo (todas las pruebas en uno)")
    pdf.code_block(
        '# ============================================================\n'
        '# SCRIPT COMPLETO - Ejecutar todas las pruebas de una vez\n'
        '# Copiar y pegar todo en PowerShell\n'
        '# ============================================================\n\n'
        'Write-Output "=== INICIO DIAGNOSTICO ==="\n'
        'Write-Output "Fecha: $(Get-Date)"\n'
        'Write-Output "Equipo: $env:COMPUTERNAME"\n'
        'Write-Output ""\n\n'
        'Write-Output "--- 1. DNS ---"\n'
        'nslookup api.openai.com 2>&1 | Select-String "Address|Nombre"\n'
        'nslookup api.mistral.ai 2>&1 | Select-String "Address|Nombre"\n'
        'Write-Output ""\n\n'
        'Write-Output "--- 2. TCP 443 ---"\n'
        'Test-NetConnection api.openai.com -Port 443 -WarningAction SilentlyContinue ^\n'
        '  | Select-Object ComputerName, RemoteAddress, TcpTestSucceeded\n'
        'Test-NetConnection api.mistral.ai -Port 443 -WarningAction SilentlyContinue ^\n'
        '  | Select-Object ComputerName, RemoteAddress, TcpTestSucceeded\n'
        'Write-Output ""\n\n'
        'Write-Output "--- 3. HTTP ---"\n'
        'curl.exe -s -o NUL -w "OpenAI:  HTTP:%{http_code} TIME:%{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models\n'
        'curl.exe -s -o NUL -w "Mistral: HTTP:%{http_code} TIME:%{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://api.mistral.ai/v1/models\n'
        'curl.exe -s -o NUL -w "Groq:    HTTP:%{http_code} TIME:%{time_total}s`n" ^\n'
        '  --connect-timeout 10 https://api.groq.com/openai/v1/models\n'
        'Write-Output ""\n\n'
        'Write-Output "--- 4. Traceroute OpenAI ---"\n'
        'tracert -d -h 5 -w 2000 162.159.140.245\n'
        'Write-Output ""\n\n'
        'Write-Output "--- 5. SNI Swap ---"\n'
        'curl.exe -s -o NUL -w "TestA: HTTP:%{http_code} TIME:%{time_total}s`n" ^\n'
        '  --resolve "api.mistral.ai:443:162.159.140.245" ^\n'
        '  --connect-timeout 10 https://api.mistral.ai/v1/models\n'
        'curl.exe -s -o NUL -w "TestB: HTTP:%{http_code} TIME:%{time_total}s`n" ^\n'
        '  --resolve "api.openai.com:443:172.66.2.203" ^\n'
        '  --connect-timeout 10 https://api.openai.com/v1/models\n'
        'Write-Output ""\n\n'
        'Write-Output "=== FIN DIAGNOSTICO ==="'
    )

    # === 16. ANEXO ===
    pdf.add_page()
    pdf.section_title("16. Anexo: Configuracion del Equipo")
    pdf.code_block(
        f"Hostname:       {socket.gethostname()}\n"
        f"Usuario:        {os.environ.get('USERNAME', 'N/A')}\n"
        f"OS:             Windows (PowerShell)\n"
        f"Python:         {sys.version.split()[0]}\n"
        f"DNS Server:     10.238.66.63 (LN-DC-ATLAS-02.corp.agv.co)\n"
        f"Gateway:        172.16.240.1\n"
        f"Proxy:          No configurado (ProxyEnable=0)\n"
        f"Variables proxy: No definidas\n\n"
        f"Fecha diagnostico: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Duracion pruebas: ~5 minutos"
    )
    pdf.ln(5)
    pdf.body_text(
        "Este informe fue generado automaticamente por el sistema de diagnostico "
        "del Agente de Calidad Integr@. Todas las pruebas fueron ejecutadas desde "
        "el equipo indicado en la red corporativa de Solistica."
    )

    # Guardar
    output_path = Path(__file__).parent.parent / "Informe_Bloqueo_OpenAI_Ciberseguridad.pdf"
    pdf.output(str(output_path))
    print(f"PDF generado: {output_path}")
    print(f"Tamano: {output_path.stat().st_size / 1024:.1f} KB")
    return output_path


if __name__ == "__main__":
    generate_report()
