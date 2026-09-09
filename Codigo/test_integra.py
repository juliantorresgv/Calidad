import os
import sys

from integra_client import IntegraClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    # Acepta usuario/contraseña por variables de entorno; si no, lee credenciales.txt
    client = IntegraClient(
        base_url=os.environ.get("INTEGRA_APP_URL", "https://appcolombia.solistica.com/IntegraV2/"),
        login_url=os.environ.get("INTEGRA_LOGIN_URL", "https://appcolombia.solistica.com/IntegraV2/Login.aspx"),
        username=os.environ.get("INTEGRA_USERNAME"),
        password=os.environ.get("INTEGRA_PASSWORD"),
    )

    print("=== Prueba de conexión con Integra ===")
    print(f"URL base: {client.base_url}")
    print(f"URL login: {client.login_url}")

    try:
        form = client.discover_login_form()
        print(f"Formulario detectado: {len(form['fields'])} campos ocultos")
        print(f"Campo usuario: {form['username_field']}")
        print(f"Campo contraseña: {form['password_field']}")
        print(f"Campo submit: {form['submit_field']}")

        result = client.login()
        print("Login resultado:")
        for k, v in result.items():
            print(f"  {k}: {v}")

        if result.get("is_logged_in"):
            home = client.get_home()
            print(f"Home status: {home.status_code}, URL: {home.url}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
