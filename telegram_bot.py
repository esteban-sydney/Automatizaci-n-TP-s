print("🔥 BOT FILE LOADED")
import asyncio
from Prueba2PDF import cola_telegram
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from config import TELEGRAM_TOKEN

estado_usuario = {}

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    print("✅ /start ejecutado")

    mensaje = (
        "🔧 Control TP Entel\n\n"
        "1.- Iniciar TP\n"
        "2.- Cerrar TP"
    )

    estado_usuario[update.effective_chat.id] = {"paso": "menu"}

    await update.message.reply_text(mensaje)

# =========================
# RESPONDER
# =========================
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        chat_id = update.effective_chat.id
        texto = update.message.text.strip()

        if chat_id not in estado_usuario:
            estado_usuario[chat_id] = {"paso": "menu"}

        estado = estado_usuario[chat_id]
        paso = estado["paso"]

        # ── MENU ─────────────────────────────────────────
        if paso == "menu":

            if texto == "1":
                estado["accion"] = "iniciar"
                estado["paso"] = "numero"
                await update.message.reply_text("📋 Ingrese número TP:")

            elif texto == "2":
                estado["accion"] = "cerrar"
                estado["paso"] = "numero"
                await update.message.reply_text("📋 Ingrese número TP:")

            else:
                 mensaje = (
                "❌ Opción inválida en caso de problemas llamar al 22 360 2280 \n\n"
                "🔧 Control TP Entel\n\n"
                "1.- Iniciar TP\n"
                "2.- Cerrar TP"
            )

                 await update.message.reply_text(mensaje)

            return

        # ── NUMERO (común para iniciar y cerrar) ─────────
        if paso == "numero":

            if not texto.isdigit():
                await update.message.reply_text("❌ El número TP debe contener solo dígitos. Intente nuevamente:")
                return

            estado["numero"] = texto
            estado["paso"] = "nombre"
            await update.message.reply_text("👤 Ingrese su nombre:")
            return

        # ── NOMBRE (común para iniciar y cerrar) ─────────
        if paso == "nombre":

            if len(texto) < 3:
                await update.message.reply_text("❌ Nombre muy corto. Intente nuevamente:")
                return

            estado["nombre"] = texto
            estado["paso"] = "telefono"
            await update.message.reply_text("📱 Ingrese su teléfono:")
            return

        # ── TELEFONO ──────────────────────────────────────
        if paso == "telefono":

            if not texto.isdigit() or len(texto) < 8:
                await update.message.reply_text("❌ Teléfono inválido. Solo números, mínimo 8 dígitos:")
                return

            estado["telefono"] = texto

            # CERRAR: listo con 3 datos, encolar
            if estado["accion"] == "cerrar":

                resumen = (
                    f"📋 Resumen cierre:\n"
                    f"• TP: {estado['numero']}\n"
                    f"• Nombre: {estado['nombre']}\n"
                    f"• Teléfono: {estado['telefono']}\n\n"
                    f"⏳ Procesando..."
                )

                await update.message.reply_text(resumen)

                cola_telegram.put({
                    "accion": "cerrar",
                    "numero": estado["numero"],
                    "nombre": estado["nombre"],
                    "telefono": estado["telefono"],
                    "empresa": "",
                    "chat_id": chat_id
                })

                print(f"📤 Cola PUT (cerrar) — id: {id(cola_telegram)} | tamaño: {cola_telegram.qsize()}")

                estado_usuario[chat_id] = {"paso": "menu"}
                return

            # INICIAR: pedir empresa además
            estado["paso"] = "empresa"
            await update.message.reply_text("🏢 Ingrese empresa:")
            return

        # ── EMPRESA (solo para iniciar) ───────────────────
        if paso == "empresa":

            empresa = "" if texto == "-" else texto
            estado["empresa"] = empresa
            estado["paso"] = "menu"

            resumen = (
                f"📋 Resumen inicio:\n"
                f"• TP: {estado['numero']}\n"
                f"• Nombre: {estado['nombre']}\n"
                f"• Teléfono: {estado['telefono']}\n"
                f"• Empresa: {empresa if empresa else 'No aplica'}\n\n"
                f"⏳ Procesando..."
            )

            await update.message.reply_text(resumen)

            cola_telegram.put({
                "accion": "iniciar",
                "numero": estado["numero"],
                "nombre": estado["nombre"],
                "telefono": estado["telefono"],
                "empresa": empresa,
                "chat_id": chat_id
            })

            print(f"📤 Cola PUT (iniciar) — id: {id(cola_telegram)} | tamaño: {cola_telegram.qsize()}")

            estado_usuario[chat_id] = {"paso": "menu"}

    except Exception as e:
        print("ERROR BOT:", e)
        await update.message.reply_text("⚠️ Ocurrió un error. Use /start para reiniciar.")

# =========================
# INICIAR BOT
# =========================
def iniciar_bot():

    print("🔥 entrando iniciar_bot")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    print("🔥 app creada")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("BOT ONLINE ✅")

    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()