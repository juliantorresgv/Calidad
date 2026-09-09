import requests
import urllib3
import sys

urllib3.disable_warnings()

def probe(url):
    try:
        r = requests.get(url, timeout=20, verify=False, allow_redirects=True)
        print(f"URL: {url}")
        print(f"  status: {r.status_code}")
        print(f"  final_url: {r.url}")
        print(f"  len: {len(r.text)}")
        # Print first part of response to identify forms / error pages
        snippet = r.text.replace('\n', ' ').replace('\r', '')[:500]
        print(f"  snippet: {snippet}")
    except Exception as e:
        print(f"URL: {url}\n  ERROR: {type(e).__name__}: {e}")

urls = [
    "https://colaboradores.solistica.com/",
    "https://colaboradores.solistica.com/Integra",
    "https://appcolombia.solistica.com/IntegraV2/",
    "https://appcolombia.solistica.com/IntegraV2/Login.aspx",
    "https://appcolombia.solistica.com/IntegraV2/Account/Login",
    "https://appcolombia.solistica.com/IntegraV2/Home",
]

for u in urls:
    probe(u)
    print("-" * 60)
