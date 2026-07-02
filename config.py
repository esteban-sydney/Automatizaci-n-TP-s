import os
from dotenv import load_dotenv

# Carga las variables desde .env
load_dotenv()

SITIO = {
    "url": "http://portalpsg.gred.entelpcs.cl/index.php",
    "post_login_url": "http://portalpsg.gred.entelpcs.cl/tp/ver_planned.php?id=",
    "selector_user": 'input[name="usuario"]',
    "selector_pass": 'input[name="password"]',
    "selector_btn_login": 'input[type="submit"]'
}

USUARIO_PORTAL = ""
PASSWORD_PORTAL = ""

# ✅ Leídos desde .env — nunca hardcodeados
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AUTHORIZED_USERS = [
    int(uid.strip())
    for uid in os.getenv("AUTHORIZED_USERS", "").split(",")
    if uid.strip().isdigit()
]

# Validación al arrancar
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no encontrado. Verifica tu archivo .env")

#if not AUTHORIZED_USERS:
#    raise ValueError("❌ AUTHORIZED_USERS no encontrado. Verifica tu archivo .env")