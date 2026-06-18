print("🔥 BOT FILE LOADED")
import logging  # noqa: E402
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("python-telegram-bot").setLevel(logging.WARNING)
import asyncio  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from Prueba2PDF import cola_telegram, buscar_en_pdf, pendientes_wdm, validar_estado_tp  # noqa: E402
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove  # noqa: E402
from telegram.ext import (  # noqa: E402
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from config import TELEGRAM_TOKEN, AUTHORIZED_USERS  # noqa: E402


estado_usuario = {}
MSG_MENU = "Seleccione una opción:\n1: Iniciar TP\n2: Cerrar TP"
MSG_VOLVER = "\n\nEscriba *volver* o pulse el botón ↩️ Volver atrás."

# =========================
# CONFIGURACIÓN
# =========================
MAX_ERRORES = 5
BLOQUEO_MINUTOS = 10
ANEXO_OFICINA = "22 360 2280"

errores_usuario = {}
bloqueo_usuario = {}

def registrar_error(chat_id: int) -> int:
    errores_usuario[chat_id] = errores_usuario.get(chat_id, 0) + 1
    return errores_usuario[chat_id]

def resetear_errores(chat_id: int):
    errores_usuario[chat_id] = 0

def esta_bloqueado(chat_id: int) -> bool:
    if chat_id in bloqueo_usuario:
        if datetime.now() < bloqueo_usuario[chat_id]:
            return True
        else:
            del bloqueo_usuario[chat_id]
            errores_usuario[chat_id] = 0
    return False

def tiempo_restante(chat_id: int) -> str:
    if chat_id in bloqueo_usuario:
        restante = bloqueo_usuario[chat_id] - datetime.now()
        minutos = int(restante.total_seconds() // 60)
        segundos = int(restante.total_seconds() % 60)
        return f"{minutos}m {segundos}s"
    return "0s"

def intentos_restantes(chat_id: int) -> int:
    return MAX_ERRORES - errores_usuario.get(chat_id, 0)


def construir_mensaje_tp_validado(numero: str, descripcion: str) -> str:
    mensaje = f"✅ TP {numero} validado correctamente."
    if descripcion:
        mensaje += f"\n\n📄 Descripción:\n{descripcion.strip()}"
    mensaje += (
        "\n\n👤 Ingrese su nombre y apellido:\n"
        "(Ejemplo: Juan Pérez)" + MSG_VOLVER
    )
    return mensaje

# =========================
# TECLADOS
# =========================
MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("1️⃣ Iniciar TP"), KeyboardButton("2️⃣ Cerrar TP")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
    input_field_placeholder="Seleccione una opción..."
)

BACK_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("↩️ Volver atrás")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
    input_field_placeholder="Ingrese el dato o vuelva atrás..."
)

QUITAR_TECLADO = ReplyKeyboardRemove()

OPCIONES_VOLVER = [
    "↩️ volver atrás",
    "volver atrás",
    "volver",
    "atras",
    "atrás"
]

# =========================
# MENSAJE DE ERROR DE SISTEMA
# =========================
MSG_ERROR_SISTEMA = (
    "⚠️ El sistema no está disponible en este momento.\n\n"
    "Por favor contacte a la oficina al anexo:\n"
    f"📞 *{ANEXO_OFICINA}*\n\n"
    "Un operador podrá asistirle y restablecer el sistema."
)

# =========================
# VERIFICAR USUARIO
# =========================
async def verificar_usuario(update: Update) -> bool:
    chat_id = update.effective_chat.id

    if esta_bloqueado(chat_id):
        await update.message.reply_text(
            f"🔒 Tu acceso está bloqueado por {tiempo_restante(chat_id)}.\n"
            f"Intenta nuevamente más tarde."
        )
        return False

    if chat_id not in AUTHORIZED_USERS:
        print(f"⛔ Acceso denegado para chat_id: {chat_id}")
        await update.message.reply_text(
            "⛔ No tienes autorización para usar este sistema.\n"
            "Contacta al administrador."
        )
        return False

    return True

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await verificar_usuario(update):
        return

    print("✅ /start ejecutado")

    chat_id = update.effective_chat.id
    estado_usuario[chat_id] = {"paso": "menu"}

    await update.message.reply_text(
        "👋 Bienvenido al sistema de Control TP Entel.\n\n" + MSG_MENU,
        reply_markup=MENU_KEYBOARD
    )

# =========================
# RESPONDER
# =========================
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await verificar_usuario(update):
        return

    try:
        chat_id = update.effective_chat.id
        texto = update.message.text.strip()
        texto_normalizado = texto.lower()

        if chat_id not in estado_usuario:
            estado_usuario[chat_id] = {"paso": "menu"}
            await update.message.reply_text(
                MSG_MENU,
                reply_markup=MENU_KEYBOARD
            )
            return

        estado = estado_usuario[chat_id]
        paso = estado["paso"]

        # ── VOLVER ATRÁS ─────────────────────────────────
        if texto_normalizado in OPCIONES_VOLVER:

            if paso == "numero":
                estado_usuario[chat_id] = {"paso": "menu"}
                resetear_errores(chat_id)
                await update.message.reply_text(
                    MSG_MENU,
                    reply_markup=MENU_KEYBOARD
                )
                return

            if paso == "nombre":
                estado["paso"] = "numero"
                estado.pop("numero", None)
                resetear_errores(chat_id)
                await update.message.reply_text(
                    "Ingrese nuevamente el número de TP:\n"
                    "_(7 dígitos numéricos. Ejemplo: 1905610)_" + MSG_VOLVER,
                    parse_mode="Markdown",
                    reply_markup=BACK_KEYBOARD
                )
                return

            if paso == "telefono":
                estado["paso"] = "nombre"
                estado.pop("nombre", None)
                resetear_errores(chat_id)
                await update.message.reply_text(
                    "Ingrese nuevamente su nombre y apellido:\n"
                    "_(Ejemplo: Juan Pérez)_" + MSG_VOLVER,
                    parse_mode="Markdown",
                    reply_markup=BACK_KEYBOARD
                )
                return

            if paso == "empresa":
                estado["paso"] = "telefono"
                estado.pop("telefono", None)
                resetear_errores(chat_id)
                await update.message.reply_text(
                    "Ingrese nuevamente su número de teléfono:\n"
                    "_(9 dígitos, sin espacios. Ejemplo: 912345678)_" + MSG_VOLVER,
                    parse_mode="Markdown",
                    reply_markup=BACK_KEYBOARD
                )
                return

        # ── MENU ─────────────────────────────────────────
        if paso == "menu":

            if texto in ["1️⃣ Iniciar TP", "1"]:
                resetear_errores(chat_id)
                estado["accion"] = "iniciar"
                estado["paso"] = "numero"
                await update.message.reply_text(
                    "📋 *Iniciar TP*\n\n"
                    "Ingrese el número de TP:"
                    "_(Ejemplo: 1905610)_" + MSG_VOLVER,
                    parse_mode="Markdown",
                    reply_markup=BACK_KEYBOARD
                )

            elif texto in ["2️⃣ Cerrar TP", "2"]:
                resetear_errores(chat_id)
                estado["accion"] = "cerrar"
                estado["paso"] = "numero"
                await update.message.reply_text(
                    "🔒 *Cerrar TP*\n\n"
                    "Ingrese el número de TP:"
                    "_(Ejemplo: 1905610)_" + MSG_VOLVER,
                    parse_mode="Markdown",
                    reply_markup=BACK_KEYBOARD
                )

            else:
                total = registrar_error(chat_id)

                if total >= MAX_ERRORES:
                    bloqueo_usuario[chat_id] = datetime.now() + timedelta(minutes=BLOQUEO_MINUTOS)
                    await update.message.reply_text(
                        f"🔒 Demasiados intentos incorrectos.\n"
                        f"Acceso bloqueado por {BLOQUEO_MINUTOS} minutos.",
                        reply_markup=QUITAR_TECLADO
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Opción inválida. Use los botones del menú.\n\n"
                        f"⚠️ {intentos_restantes(chat_id)} intentos restantes.",
                        reply_markup=MENU_KEYBOARD
                    )
            return

        # ── NUMERO ───────────────────────────────────────
        if paso == "numero":

            if not texto.isdigit() or len(texto) != 7:
                total = registrar_error(chat_id)

                if total >= MAX_ERRORES:
                    bloqueo_usuario[chat_id] = datetime.now() + timedelta(minutes=BLOQUEO_MINUTOS)
                    await update.message.reply_text(
                        f"🔒 Demasiados intentos incorrectos.\n"
                        f"Acceso bloqueado por {BLOQUEO_MINUTOS} minutos."
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Número de TP incorrecto.\n\n"
                        f"📌 Debe ser exactamente *7 dígitos numéricos*."
                        f"📌 Ejemplo: 1905610\n\n"
                        f"⚠️ {intentos_restantes(chat_id)} intentos restantes.\n\n"
                        f"Ingrese número de TP:" + MSG_VOLVER,
                        parse_mode="Markdown",
                        reply_markup=BACK_KEYBOARD
                    )
                return
            # Validar existencia del TP en los PDFs cargados (UI)
            try:
                existe = buscar_en_pdf(texto)
            except Exception as e:
                print("ERROR validando PDF:", e)
                await update.message.reply_text(
                    MSG_ERROR_SISTEMA,
                    parse_mode="Markdown"
                )
                return

            if not existe:
                total = registrar_error(chat_id)
                await update.message.reply_text(
                    f"❌ TP {texto} no fue encontrado en los PDFs disponibles.\n\n" \
                    f"Por favor verifique el número o contacte a un operador 22 360 2280. ",
                    reply_markup=BACK_KEYBOARD
                )
                if total >= MAX_ERRORES:
                    bloqueo_usuario[chat_id] = datetime.now() + timedelta(minutes=BLOQUEO_MINUTOS)
                    await update.message.reply_text(
                        f"🔒 Demasiados intentos incorrectos.\n"
                        f"Acceso bloqueado por {BLOQUEO_MINUTOS} minutos.",
                        reply_markup=QUITAR_TECLADO
                    )
                return

            estado_info = validar_estado_tp(texto)
            estado_plataforma = str(estado_info.get("estado", "ERROR")).upper()
            descripcion_tp = str(estado_info.get("descripcion", "")).strip()

            if estado.get("accion") == "cerrar":
                if estado_plataforma == "ERROR_SESION":
                    await update.message.reply_text(
                        "⚠️ No hay sesión de navegador activa para validar el TP. "
                        "Asegúrese de que la UI del operador esté abierta y la sesión PSG activa.",
                        reply_markup=BACK_KEYBOARD
                    )
                    return

                if estado_plataforma == "ERROR":
                    await update.message.reply_text(
                        "⚠️ No se pudo validar el estado del TP en la plataforma. "
                        "Por favor inténtelo nuevamente más tarde.",
                        reply_markup=BACK_KEYBOARD
                    )
                    return

                if estado_plataforma == "NO_PDF":
                    total = registrar_error(chat_id)
                    await update.message.reply_text(
                        f"❌ TP {texto} no fue encontrado en los PDFs disponibles.\n\n"
                        f"Por favor verifique el número o contacte a un operador 22 360 2280.",
                        reply_markup=BACK_KEYBOARD
                    )
                    if total >= MAX_ERRORES:
                        bloqueo_usuario[chat_id] = datetime.now() + timedelta(minutes=BLOQUEO_MINUTOS)
                        await update.message.reply_text(
                            f"🔒 Demasiados intentos incorrectos.\n"
                            f"Acceso bloqueado por {BLOQUEO_MINUTOS} minutos.",
                            reply_markup=QUITAR_TECLADO
                        )
                    return

                estado_plataforma_sin_espacios = estado_plataforma.replace(" ", "")

                if "EJECUTADO" in estado_plataforma_sin_espacios:
                    await update.message.reply_text(
                        f"⚠️ El TP {texto} ya fue ejecutado y no puede cerrarse. "
                        "Verifique el número o consulte con un operador.",
                        reply_markup=BACK_KEYBOARD
                    )
                    return

                if "EJECUCION" not in estado_plataforma_sin_espacios:
                    await update.message.reply_text(
                        f"⚠️ El TP {texto} no está en estado EN EJECUCIÓN. "
                        f"Estado actual: {estado_plataforma}.\n\n"
                        "Solo los TP en EN EJECUCIÓN pueden cerrarse.",
                        reply_markup=BACK_KEYBOARD
                    )
                    return

            if estado.get("accion") == "iniciar":
                if estado_plataforma == "ERROR_SESION":
                    await update.message.reply_text(
                        "⚠️ No hay sesión de navegador activa para validar el TP. "
                        "Asegúrese de que la UI del operador esté abierta y la sesión PSG activa.",
                        reply_markup=BACK_KEYBOARD
                    )
                    return

                if estado_plataforma == "ERROR":
                    await update.message.reply_text(
                        "⚠️ No se pudo validar el estado del TP en la plataforma. "
                        "Por favor inténtelo nuevamente más tarde.",
                        reply_markup=BACK_KEYBOARD
                    )
                    return

                if estado_plataforma == "NO_PDF":
                    total = registrar_error(chat_id)
                    await update.message.reply_text(
                        f"❌ TP {texto} no fue encontrado en los PDFs disponibles.\n\n"
                        f"Por favor verifique el número o contacte a un operador 22 360 2280.",
                        reply_markup=BACK_KEYBOARD
                    )
                    if total >= MAX_ERRORES:
                        bloqueo_usuario[chat_id] = datetime.now() + timedelta(minutes=BLOQUEO_MINUTOS)
                        await update.message.reply_text(
                            f"🔒 Demasiados intentos incorrectos.\n"
                            f"Acceso bloqueado por {BLOQUEO_MINUTOS} minutos.",
                            reply_markup=QUITAR_TECLADO
                        )
                    return

                if estado_plataforma != "PLANIFICADO":
                    await update.message.reply_text(
                        f"⚠️ El TP {texto} no puede iniciarse. "
                        f"Estado actual: {estado_plataforma}.\n\n"
                        "Solo los TP en PLANIFICADO pueden iniciarse.",
                        reply_markup=BACK_KEYBOARD
                    )
                    return

            resetear_errores(chat_id)
            estado["numero"] = texto
            estado["paso"] = "nombre"
            await update.message.reply_text(
                construir_mensaje_tp_validado(texto, descripcion_tp),
                reply_markup=BACK_KEYBOARD
            )
            return

        # ── NOMBRE ───────────────────────────────────────
        if paso == "nombre":

            partes = texto.strip().split()
            tiene_letras = any(c.isalpha() for c in texto)
            es_valido = len(partes) >= 2 and tiene_letras and len(texto) >= 6

            if not es_valido:
                total = registrar_error(chat_id)

                if total >= MAX_ERRORES:
                    bloqueo_usuario[chat_id] = datetime.now() + timedelta(minutes=BLOQUEO_MINUTOS)
                    await update.message.reply_text(
                        f"🔒 Demasiados intentos incorrectos.\n"
                        f"Acceso bloqueado por {BLOQUEO_MINUTOS} minutos."
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Nombre incorrecto.\n"
                        f"📌 Debe ingresar *nombre y apellido*.\n"
                        f"📌 Ejemplo: Juan Pérez\n\n"
                        f"⚠️ {intentos_restantes(chat_id)} intentos restantes.\n\n"
                        f"Ingrese su nombre y apellido:" + MSG_VOLVER,
                        parse_mode="Markdown",
                        reply_markup=BACK_KEYBOARD
                    )
                return

            resetear_errores(chat_id)
            estado["nombre"] = texto
            estado["paso"] = "telefono"
            await update.message.reply_text(
                "📱 Ingrese su número de teléfono: "
                "_Ejemplo: 912345678)_" + MSG_VOLVER,
                parse_mode="Markdown",
                reply_markup=BACK_KEYBOARD
            )
            return

        # ── TELEFONO ─────────────────────────────────────
        if paso == "telefono":

            if not texto.isdigit() or len(texto) != 9:
                total = registrar_error(chat_id)

                if total >= MAX_ERRORES:
                    bloqueo_usuario[chat_id] = datetime.now() + timedelta(minutes=BLOQUEO_MINUTOS)
                    await update.message.reply_text(
                        f"🔒 Demasiados intentos incorrectos.\n"
                        f"Acceso bloqueado por {BLOQUEO_MINUTOS} minutos."
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Teléfono incorrecto.\n\n"
                        f"📌 Debe ser exactamente *9 dígitos numéricos*, sin espacios ni guiones.\n"
                        f"📌 Ejemplo: 912345678\n\n"
                        f"⚠️ {intentos_restantes(chat_id)} intentos restantes.\n\n"
                        f"Ingrese su teléfono:" + MSG_VOLVER,
                        parse_mode="Markdown",
                        reply_markup=BACK_KEYBOARD
                    )
                return

            resetear_errores(chat_id)
            estado["telefono"] = texto

            # CERRAR — listo con 3 datos
            if estado["accion"] == "cerrar":

                resumen = (
                    f"📋 *Resumen cierre:*\n"
                    f"• TP: {estado['numero']}\n"
                    f"• Nombre: {estado['nombre']}\n"
                    f"• Teléfono: {estado['telefono']}\n\n"
                    f"⏳ Procesando..."
                )

                await update.message.reply_text(resumen, parse_mode="Markdown")

                cola_telegram.put({
                    "accion": "cerrar",
                    "numero": estado["numero"],
                    "nombre": estado["nombre"],
                    "telefono": estado["telefono"],
                    "empresa": "",
                    "chat_id": chat_id
                })

                print(f"📤 Cola PUT (cerrar) — tamaño: {cola_telegram.qsize()}")
                estado_usuario[chat_id] = {"paso": "menu"}
                return
            estado["paso"] = "empresa"
            await update.message.reply_text(
                "🏢 Ingrese el nombre de su empresa:" + MSG_VOLVER,
                parse_mode="Markdown",
                reply_markup=BACK_KEYBOARD
            )
            return

        # ── EMPRESA SOLO INICIAR ─────────────────────────
        if paso == "empresa":

            empresa = "" if texto == "-" else texto
            estado["empresa"] = empresa
            estado["paso"] = "menu"

            resumen = (
                f"📋 *Resumen inicio:*\n"
                f"• TP: {estado['numero']}\n"
                f"• Nombre: {estado['nombre']}\n"
                f"• Teléfono: {estado['telefono']}\n"
                f"• Empresa: {empresa if empresa else 'No aplica'}\n\n"
                f"⏳ Procesando..."
            )

            await update.message.reply_text(resumen, parse_mode="Markdown")

            cola_telegram.put({
                "accion": "iniciar",
                "numero": estado["numero"],
                "nombre": estado["nombre"],
                "telefono": estado["telefono"],
                "empresa": empresa,
                "chat_id": chat_id
            })

            print(f"📤 Cola PUT (iniciar) — tamaño: {cola_telegram.qsize()}")
            estado_usuario[chat_id] = {"paso": "menu"}

    except Exception as e:
        print("ERROR BOT:", e)
        await update.message.reply_text(
            MSG_ERROR_SISTEMA,
            parse_mode="Markdown"
        )

# =========================
# ADMIN COMMANDS
async def aprobar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_usuario(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Uso: /aprobar <numero_TP>")
        return

    numero = args[0].strip()
    pendiente = pendientes_wdm.pop(numero, None)
    if not pendiente:
        await update.message.reply_text(f"No hay solicitud pendiente para TP {numero}.")
        return

    cola_telegram.put(pendiente)
    await update.message.reply_text(
        f"✅ TP {numero} aprobado. Se reenvía para iniciar el proceso automáticamente."
    )

    try:
        await context.bot.send_message(
            chat_id=pendiente["chat_id"],
            text=(
                f"✅ Tu TP {numero} fue aprobado por los administradores.\n"
                "Se procederá con el inicio. Si hay novedades, te avisaremos aquí."
            )
        )
    except Exception as e:
        print("ERROR enviando mensaje al usuario aprobado:", e)

async def rechazar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_usuario(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Uso: /rechazar <numero_TP>")
        return

    numero = args[0].strip()
    pendiente = pendientes_wdm.pop(numero, None)
    if not pendiente:
        await update.message.reply_text(f"No hay solicitud pendiente para TP {numero}.")
        return

    await update.message.reply_text(
        f"❌ TP {numero} rechazado. Se avisó al usuario que debe llamar al anexo."
    )

    try:
        await context.bot.send_message(
            chat_id=pendiente["chat_id"],
            text=(
                f"⚠️ Tu TP {numero} fue revisado y *no fue aprobado* para inicio automático.\n"
                f"Por favor contacta al anexo: {ANEXO_OFICINA}."
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        print("ERROR enviando mensaje al usuario rechazado:", e)

    notificar_grupo(
        f"❌ TP {numero} rechazado por administrador.\n"
        f"👤 {pendiente['nombre']} | 📱 {pendiente['telefono']}\n"
        f"📋 TP: {numero}"
    )

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
    app.add_handler(CommandHandler("aprobar", aprobar))
    app.add_handler(CommandHandler("rechazar", rechazar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("BOT ONLINE ✅")

    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()
