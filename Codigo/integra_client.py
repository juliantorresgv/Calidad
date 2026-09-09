import os
import re
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Rutas conocidas de Integra según la documentación
PORTAL_URL = os.environ.get("INTEGRA_PORTAL_URL", "https://colaboradores.solistica.com/")
APP_BASE_URL = os.environ.get("INTEGRA_APP_URL", "https://appcolombia.solistica.com/IntegraV2/")
DEFAULT_LOGIN_URL = os.environ.get("INTEGRA_LOGIN_URL", urllib.parse.urljoin(APP_BASE_URL, "Login.aspx"))


def _load_credentials(path: Optional[Path] = None) -> tuple[str, str]:
    """Carga usuario y contraseña de un archivo de dos líneas."""
    if path is None:
        path = Path(r"C:\Users\1121871773\OneDrive - agvco\Documentos\Agente Calidad Codigo\credenciales.txt")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("El archivo de credenciales debe contener al menos usuario y contraseña.")
    return lines[0], lines[1]


class IntegraClient:
    """Cliente HTTP para la plataforma web Integr@.

    Soporta autenticación en formularios ASP.NET WebForms detectando los
    campos ocultos (__VIEWSTATE, __EVENTVALIDATION, etc.) y los campos de
    usuario/contraseña de forma automática.
    """

    def __init__(
        self,
        base_url: str = APP_BASE_URL,
        login_url: str = DEFAULT_LOGIN_URL,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.login_url = login_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = False

        if username is None or password is None:
            self.username, self.password = _load_credentials()
        else:
            self.username, self.password = username, password

    def _absolute_url(self, url: str) -> str:
        return urllib.parse.urljoin(self.base_url, url)

    def get(self, url: str, **kwargs) -> requests.Response:
        full_url = self._absolute_url(url)
        return self.session.get(full_url, timeout=self.timeout, **kwargs)

    def post(self, url: str, data=None, **kwargs) -> requests.Response:
        full_url = self._absolute_url(url)
        return self.session.post(full_url, data=data, timeout=self.timeout, **kwargs)

    def discover_login_form(self) -> dict:
        """Obtiene el formulario de login e identifica los campos necesarios."""
        resp = self.session.get(self.login_url, timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        form = soup.find("form")
        if not form:
            raise RuntimeError("No se encontró un formulario en la página de login.")

        action = form.get("action") or self.login_url
        fields: dict[str, str] = {}
        username_field: Optional[str] = None
        password_field: Optional[str] = None
        submit_field: Optional[str] = None

        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            value = inp.get("value", "")
            itype = (inp.get("type") or "").lower()

            if itype in ("hidden",):
                fields[name] = value
                continue

            if itype == "password":
                password_field = name
                continue

            if itype in ("text", "email", "tel", "number"):
                if username_field is None:
                    username_field = name
                # Preferimos un campo cuyo nombre indique usuario
                lowered = name.lower()
                if any(k in lowered for k in ("user", "usuario", "cedula", "login", "email", "correo", "cuenta")):
                    username_field = name
                continue

            if itype in ("submit", "button"):
                if submit_field is None:
                    submit_field = name
                    fields[name] = value or "Ingresar"

        # Botones ASP.NET que suelen ser <a> o <input> con name termina en .x/.y
        if not submit_field:
            for inp in form.find_all("input"):
                name = inp.get("name", "")
                if re.search(r"(?:Login|Ingresar|Entrar|Aceptar)(?:\.x)?$", name, re.I):
                    submit_field = name
                    fields[name] = inp.get("value", "")

        return {
            "action": self._absolute_url(action),
            "fields": fields,
            "username_field": username_field,
            "password_field": password_field,
            "submit_field": submit_field,
            "raw_html": resp.text[:1000],
        }

    def login(self) -> dict:
        """Intenta iniciar sesión y devuelve el resultado.

        El cliente guarda las cookies en ``self.session`` para peticiones
        posteriores.
        """
        form_info = self.discover_login_form()
        username_field = form_info["username_field"]
        password_field = form_info["password_field"]

        if not username_field or not password_field:
            raise RuntimeError(
                f"No se pudieron detectar los campos de login. "
                f"Campos detectados: usuario={username_field}, contraseña={password_field}"
            )

        payload = dict(form_info["fields"])
        payload[username_field] = self.username
        payload[password_field] = self.password

        if form_info["submit_field"]:
            payload[form_info["submit_field"]] = form_info["fields"].get(form_info["submit_field"], "Ingresar")

        resp = self.session.post(
            form_info["action"],
            data=payload,
            timeout=self.timeout,
            allow_redirects=True,
        )

        return {
            "status_code": resp.status_code,
            "final_url": resp.url,
            "is_logged_in": self._looks_logged_in(resp),
            "snippet": resp.text.replace("\n", " ")[:500],
        }

    def _looks_logged_in(self, resp: requests.Response) -> bool:
        text = resp.text.lower()
        indicators = ["cerrar sesión", "cerrar sesion", "logout", "bienvenid", "inicio", "home"]
        negative = ["usuario o contraseña incorrect", "credenciales", "login", "autenticaci"]
        score = sum(1 for i in indicators if i in text) - sum(1 for n in negative if n in text)
        return score > 0

    def get_home(self) -> requests.Response:
        return self.get("Home.aspx")

    def get_program(self, internal_name: str) -> requests.Response:
        """Solicita una página de programa usando su nombre interno.

        El nombre interno es el que aparece en la URL de la plataforma.
        """
        url = f"{internal_name}.aspx" if not internal_name.endswith(".aspx") else internal_name
        return self.get(url)


if __name__ == "__main__":
    client = IntegraClient()
    print(f"Intentando login en {client.login_url} ...")
    try:
        result = client.login()
        print("Resultado:", result)
    except Exception as e:
        print("Error:", type(e).__name__, e)
