print("🔥 BOT FILE LOADED")
import logging  # noqa: E402
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("python-telegram-bot").setLevel(logging.WARNING)
import asyncio  # noqa: E402
import re  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from Prueba2PDF import (  # noqa: E402
    cola_telegram,
    buscar_en_pdf,
    aprobar_inicio_pendiente,
    rechazar_inicio_pendiente,
    obtener_unico_inicio_pendiente,
    GROUP_CHAT_ID
)
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove  # noqa: E402
from telegram.ext import (  # noqa: E402
    ApplicationBuilder,
    CallbackQueryHandler,
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
TIMEOUT_PASO_SEGUNDOS = 45
PASOS_CON_TIMEOUT = {"numero", "nombre", "telefono", "empresa"}

errores_usuario = {}
bloqueo_usuario = {}

def cambiar_paso(estado: dict, paso: str, **datos):
    estado.update(datos)
    estado["paso"] = paso
    if paso in PASOS_CON_TIMEOUT:
        estado["ultimo_paso_en"] = datetime.now()
    else:
        estado.pop("ultimo_paso_en", None)

def paso_expirado(estado: dict) -> bool:
    paso = estado.get("paso")
    inicio = estado.get("ultimo_paso_en")
    if paso not in PASOS_CON_TIMEOUT or inicio is None:
        return False
    return (datetime.now() - inicio).total_seconds() > TIMEOUT_PASO_SEGUNDOS

async def cancelar_por_timeout(update: Update, chat_id: int):
    estado_usuario[chat_id] = {"paso": "menu"}
    resetear_errores(chat_id)
    await update.message.reply_text(
        "⏱️ Tu solicitud fue cancelada por tiempo de espera.\n\n" + MSG_MENU,
        reply_markup=MENU_KEYBOARD
    )

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
    if update.effective_chat.type in ("group", "supergroup") and chat_id == GROUP_CHAT_ID:
        return True

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

        if paso_expirado(estado):
            await cancelar_por_timeout(update, chat_id)
            return

        if paso == "prevalidando":
            await update.message.reply_text(
                "⏳ El TP se está validando. Por favor espere un momento."
            )
            return

        if paso == "procesando_solicitud":
            await update.message.reply_text("⏳ Procesando solicitud. Por favor espere.")
            return

        if paso == "en_cola":
            await update.message.reply_text(
                "⏳ Tu solicitud ya fue recibida y está en espera.\n\n"
                "En este momento se están procesando solicitudes previas de otros colegas. "
                "Te avisaremos por este chat cuando comience tu atención."
            )
            return

        if paso == "procesando":
            await update.message.reply_text("⏳ Tu solicitud está siendo procesada. Por favor espere.")
            return

        if paso == "esperando_aprobacion_inicio":
            await update.message.reply_text(
                f"⏳ Tu solicitud {estado.get('numero', '')} está siendo validada.\n"
                "Favor atento a esta conversación."
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
                estado.pop("numero", None)
                cambiar_paso(estado, "numero")
                resetear_errores(chat_id)
                await update.message.reply_text(
                    "Ingrese nuevamente el número de TP:\n"
                    "_(7 dígitos numéricos. Ejemplo: 1905610)_" + MSG_VOLVER,
                    parse_mode="Markdown",
                    reply_markup=BACK_KEYBOARD
                )
                return

            if paso == "telefono":
                estado.pop("nombre", None)
                cambiar_paso(estado, "nombre")
                resetear_errores(chat_id)
                await update.message.reply_text(
                    "Ingrese nuevamente su nombre y apellido:\n"
                    "_(Ejemplo: Juan Pérez)_" + MSG_VOLVER,
                    parse_mode="Markdown",
                    reply_markup=BACK_KEYBOARD
                )
                return

            if paso == "empresa":
                estado.pop("telefono", None)
                cambiar_paso(estado, "telefono")
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
                cambiar_paso(estado, "numero", accion="iniciar")
                await update.message.reply_text(
                    "📋 *Iniciar TP*\n\n"
                    "Ingrese el número de TP:"
                    "_(Ejemplo: 1905610)_" + MSG_VOLVER,
                    parse_mode="Markdown",
                    reply_markup=BACK_KEYBOARD
                )

            elif texto in ["2️⃣ Cerrar TP", "2"]:
                resetear_errores(chat_id)
                cambiar_paso(estado, "numero", accion="cerrar")
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
                cambiar_paso(estado, "numero")

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
                cambiar_paso(estado, "numero")
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
            cambiar_paso(estado, "prevalidando")
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
                cambiar_paso(estado, "nombre")

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
            cambiar_paso(estado, "telefono")
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

            if estado.get("accion") == "cerrar":
                estado["empresa"] = ""
                cambiar_paso(estado, "procesando_solicitud")

                cola_telegram.put({
                    "accion": "cerrar",
                    "numero": estado["numero"],
                    "nombre": estado["nombre"],
                    "telefono": estado["telefono"],
                    "empresa": "",
                    "tp_info": estado.get("tp_info", {}),
                    "chat_id": chat_id,
                    "estado_ref": estado
                })

                print(f"📤 Cola PUT (cerrar) — tamaño: {cola_telegram.qsize()}")
                await update.message.reply_text(
                    f"⏳ Procesando solicitud de cierre para TP {estado['numero']}. Espere un momento...",
                    reply_markup=QUITAR_TECLADO
                )
                return

            cambiar_paso(estado, "empresa")
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
            cambiar_paso(estado, "procesando_solicitud")
            accion = estado["accion"]

            cola_telegram.put({
                "accion": accion,
                "numero": estado["numero"],
                "nombre": estado["nombre"],
                "telefono": estado["telefono"],
                "empresa": empresa,
                "tp_info": estado.get("tp_info", {}),
                "chat_id": chat_id,
                "estado_ref": estado
            })

            print(f"📤 Cola PUT ({accion}) — tamaño: {cola_telegram.qsize()}")
            await update.message.reply_text(
                f"⏳ Procesando solicitud para TP {estado['numero']}. Espere un momento...",
                reply_markup=QUITAR_TECLADO
            )
            return

    except Exception as e:
        print("ERROR BOT:", e)
        await update.message.reply_text(
            MSG_ERROR_SISTEMA,
            parse_mode="Markdown"
        )

async def aprobar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_usuario(update):
        return

    tarea_id = obtener_id_comando_admin(update, context)
    if not tarea_id:
        await update.message.reply_text("Uso: /SI INI-123")
        return

    ok, mensaje = aprobar_inicio_pendiente(tarea_id)
    await update.message.reply_text(mensaje)

async def rechazar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_usuario(update):
        return

    tarea_id = obtener_id_comando_admin(update, context)
    if not tarea_id:
        await update.message.reply_text("Uso: /NO INI-123")
        return

    ok, mensaje = rechazar_inicio_pendiente(tarea_id)
    await update.message.reply_text(mensaje)

async def responder_boton_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id if update.effective_user else chat_id
    if chat_id != GROUP_CHAT_ID and user_id not in AUTHORIZED_USERS:
        await query.message.reply_text("⛔ No tienes autorización para aprobar o rechazar solicitudes.")
        return

    try:
        accion, tarea_id = query.data.split(":", 1)
    except ValueError:
        await query.message.reply_text("⚠️ Acción no válida.")
        return

    if accion == "SI":
        ok, mensaje = aprobar_inicio_pendiente(tarea_id)
    elif accion == "NO":
        ok, mensaje = rechazar_inicio_pendiente(tarea_id)
    else:
        ok, mensaje = False, "⚠️ Acción no válida."

    await query.message.reply_text(mensaje)

async def responder_comando_admin_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_usuario(update):
        return

    texto = update.message.text.strip()
    if re.match(r"^/si(?:@\w+)?(?:\s|$)", texto, re.IGNORECASE):
        tarea_id = obtener_id_comando_admin(update, context)
        if not tarea_id:
            await update.message.reply_text("Uso: /SI INI-123")
            return
        ok, mensaje = aprobar_inicio_pendiente(tarea_id)
        await update.message.reply_text(mensaje)
        return

    if re.match(r"^/no(?:@\w+)?(?:\s|$)", texto, re.IGNORECASE):
        tarea_id = obtener_id_comando_admin(update, context)
        if not tarea_id:
            await update.message.reply_text("Uso: /NO INI-123")
            return
        ok, mensaje = rechazar_inicio_pendiente(tarea_id)
        await update.message.reply_text(mensaje)

def obtener_id_comando_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        return context.args[0].strip().upper()

    texto = getattr(update.message, "text", "") or ""
    match = re.search(r"\bINI-\d{3}\b", texto.upper())
    if match:
        return match.group(0)

    reply = getattr(update.message, "reply_to_message", None)
    texto_reply = ""
    if reply:
        texto_reply = getattr(reply, "text", "") or getattr(reply, "caption", "") or ""
    match = re.search(r"\bINI-\d{3}\b", texto_reply.upper())
    if match:
        return match.group(0)

    return obtener_unico_inicio_pendiente()

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
    app.add_handler(CallbackQueryHandler(responder_boton_admin, pattern=r"^(SI|NO):INI-\d{3}$"))
    app.add_handler(CommandHandler(["SI", "si"], aprobar_inicio))
    app.add_handler(CommandHandler(["NO", "no"], rechazar_inicio))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^/(si|no)(?:@\w+)?(?:\s|$)"), responder_comando_admin_texto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("BOT ONLINE ✅")

    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()
