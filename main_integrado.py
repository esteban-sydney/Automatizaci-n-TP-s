import threading
import Prueba2PDF
from telegram_bot import iniciar_bot

def run_bot():
    print("🚀 Iniciando bot...")
    iniciar_bot()

# ✅ Bot en hilo separado (misma memoria = misma cola)
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

print("✅ UI lista")

# ✅ UI corre en hilo principal (requerido por tkinter)
Prueba2PDF.main()