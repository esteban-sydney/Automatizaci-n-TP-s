print("🔥 BOT FILE LOADED")
import logging  # noqa: E402
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("python-telegram-bot").setLevel(logging.WARNING)
import asyncio  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from Prueba2PDF import (  # noqa: E402
    cola_telegram,
    buscar_en_pdf,
    pendientes_wdm,
    pendientes_aprobacion,
    notificar_grupo
)
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
MSG_MENU = (
    "Gestor de TP NOC Transporte, favor recordar que trabajo a iniciar NO debe tener afectación de servicio, "
    "de ser así, llamar al anexo de Transporte.\n\n"
    "Seleccione una opción:\n"
    "1: Iniciar TP\n"
    "2: Cerrar TP"
)
MSG_VOLVER = "\n\nEscriba *volver* o pulse el botón ↩️ Volver atrás."

# =========================
# CONFIGURACIÓN
# =========================
MAX_ERRORES = 5
BLOQUEO_MINUTOS = 10
ANEXO_OFICINA = "22 360 2288"

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

def mensaje_espera_aprobacion(numero: str, accion: str) -> str:
    if accion == "cerrar":
        return (
            f"⏳ Tu solicitud de cierre para el TP {numero} fue enviada a aprobación de administradores. "
            "Favor de tener en cuenta de la cantidad de trabajos que pueden haber en este momento. "
            "Por favor espere."
        )

    return (
        f"⏳ Tu TP {numero} fue enviado a aprobación de administradores. "
        "Favor de tener en cuenta de la cantidad de trabajos que pueden haber en este momento. "
        "Por favor espere."
    )

def mensaje_procesando_aprobado(numero: str, accion: str) -> str:
    accion_texto = "inicio" if accion == "iniciar" else "cierre"
    return (
        f"✅ Tu solicitud para el TP {numero} fue aprobada.\n"
        f"🕐 TP está procesando {accion_texto}..."
    )

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
    user_id = update.effective_user.id if update.effective_user else chat_id
    auth_id = user_id if update.effective_chat.type in ("group", "supergroup") else chat_id

    if esta_bloqueado(auth_id):
        await update.message.reply_text(
            f"🔒 Tu acceso está bloqueado por {tiempo_restante(auth_id)}.\n"
            f"Intenta nuevamente más tarde."
        )
        return False

    if auth_id not in AUTHORIZED_USERS:
        print(f"⛔ Acceso denegado para chat_id: {chat_id} | user_id: {user_id}")
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

        if paso == "prevalidando":
            await update.message.reply_text(
                "⏳ El TP se está validando. Por favor espere un momento."
            )
            return

        if paso == "procesando_solicitud":
            await update.message.reply_text("⏳ Procesando solicitud. Por favor espere.")
            return

        if paso == "esperando_aprobacion":
            await update.message.reply_text(
                estado.get("mensaje_espera", mensaje_espera_aprobacion(estado.get("numero", ""), estado.get("accion", "")))
            )
            return

        if paso == "procesando_aprobado":
            await update.message.reply_text(
                mensaje_procesando_aprobado(estado.get("numero", ""), estado.get("accion", "iniciar"))
            )
            return

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
                    "_(Puede ingresar el número o contacto que corresponda)_" + MSG_VOLVER,
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
                    f"Por favor verifique el número o contacte a un operador {ANEXO_OFICINA}. ",
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

            resetear_errores(chat_id)
            estado["numero"] = texto
            estado["paso"] = "prevalidando"
            cola_telegram.put({
                "tipo": "prevalidar",
                "accion": estado["accion"],
                "numero": texto,
                "chat_id": chat_id,
                "estado_ref": estado
            })
            await update.message.reply_text(
                f"⏳ Validando TP {texto}. Espere un momento..."
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
                "_Puede ingresar el número o contacto que corresponda_" + MSG_VOLVER,
                parse_mode="Markdown",
                reply_markup=BACK_KEYBOARD
            )
            return

        # ── TELEFONO ─────────────────────────────────────
        if paso == "telefono":
            resetear_errores(chat_id)
            estado["telefono"] = texto

            estado["paso"] = "empresa"
            await update.message.reply_text(
                "🏢 Ingrese el nombre de su empresa:" + MSG_VOLVER,
                parse_mode="Markdown",
                reply_markup=BACK_KEYBOARD
            )
            return

        # ── EMPRESA ──────────────────────────────────────
        if paso == "empresa":

            empresa = "" if texto == "-" else texto
            estado["empresa"] = empresa
            estado["paso"] = "procesando_solicitud"
            accion = estado["accion"]

            cola_telegram.put({
                "accion": accion,
                "numero": estado["numero"],
                "nombre": estado["nombre"],
                "telefono": estado["telefono"],
                "empresa": empresa,
                "chat_id": chat_id,
                "estado_ref": estado
            })

            print(f"📤 Cola PUT ({accion}) — tamaño: {cola_telegram.qsize()}")
            return

    except Exception as e:
        print("ERROR BOT:", e)
        await update.message.reply_text(
            MSG_ERROR_SISTEMA,
            parse_mode="Markdown"
        )

# =========================
# ADMIN COMMANDS
async def aceptar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_usuario(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Uso: /aceptar <ID_solicitud>")
        return

    solicitud_id = args[0].strip()
    pendiente = pendientes_aprobacion.pop(solicitud_id, None)

    if pendiente:
        pendiente["aprobado"] = True
        cola_telegram.put(pendiente)
        numero = pendiente["numero"]
        accion_texto = "inicio" if pendiente["accion"] == "iniciar" else "cierre"
        estado_ref = pendiente.get("estado_ref")
        if isinstance(estado_ref, dict):
            estado_ref.clear()
            estado_ref.update({
                "paso": "procesando_aprobado",
                "accion": pendiente["accion"],
                "numero": numero
            })

        await update.message.reply_text(
            f"✅ TP {numero} se enviará a {accion_texto} en el programa, espere..."
        )

        try:
            await context.bot.send_message(
                chat_id=pendiente["chat_id"],
                text=(
                    f"✅ Tu solicitud para el TP {numero} fue aprobada.\n"
                    f"🕐 TP está procesando {'inicio' if pendiente['accion'] == 'iniciar' else 'cierre'}..."
                )
            )
        except Exception as e:
            print("ERROR enviando mensaje al usuario aprobado:", e)
        return

    # Compatibilidad con solicitudes antiguas guardadas por número de TP.
    pendiente = pendientes_wdm.pop(solicitud_id, None)
    if not pendiente:
        await update.message.reply_text(f"No hay solicitud pendiente con ID/TP {solicitud_id}.")
        return

    numero = pendiente["numero"]
    pendiente["aprobado"] = True
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

async def aprobar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await aceptar(update, context)

async def rechazar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_usuario(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Uso: /rechazar <ID_solicitud>")
        return

    solicitud_id = args[0].strip()
    pendiente = pendientes_aprobacion.pop(solicitud_id, None)

    if pendiente:
        numero = pendiente["numero"]
        estado_ref = pendiente.get("estado_ref")
        if isinstance(estado_ref, dict):
            estado_ref.clear()
            estado_ref.update({"paso": "menu"})

        await update.message.reply_text(
            f"❌ Solicitud TP {numero} rechazada. Se avisó al usuario."
        )

        try:
            await context.bot.send_message(
                chat_id=pendiente["chat_id"],
                text=(
                    f"⚠️ Tu solicitud para el TP {numero} fue revisada y *no fue aprobada*.\n"
                    f"Por favor contacta al anexo: {ANEXO_OFICINA}."
                ),
                parse_mode="Markdown",
                reply_markup=MENU_KEYBOARD
            )
        except Exception as e:
            print("ERROR enviando mensaje al usuario rechazado:", e)

        notificar_grupo(
            f"❌ Solicitud #{solicitud_id} rechazada por administrador.\n"
            f"👤 {pendiente['nombre']} | 📱 {pendiente['telefono']}\n"
            f"📋 TP: {numero}"
        )
        return

    # Compatibilidad con solicitudes antiguas guardadas por número de TP.
    pendiente = pendientes_wdm.pop(solicitud_id, None)
    if not pendiente:
        await update.message.reply_text(f"No hay solicitud pendiente con ID/TP {solicitud_id}.")
        return

    numero = pendiente["numero"]
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
    app.add_handler(CommandHandler("aceptar", aceptar))
    app.add_handler(CommandHandler("aprobar", aprobar))
    app.add_handler(CommandHandler("rechazar", rechazar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("BOT ONLINE ✅")

    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()
