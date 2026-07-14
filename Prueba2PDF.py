from queue import Queue
cola_telegram = Queue()

import tkinter as tk  # noqa: E402
from tkinter import messagebox, filedialog, ttk  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from PyPDF2 import PdfReader  # noqa: E402
import re  # noqa: E402
from datetime import datetime  # noqa: E402
import os  # noqa: E402
import requests  # noqa: E402
import random  # noqa: E402
from config import TELEGRAM_TOKEN  # noqa: E402
import logging  # noqa: E402

# Logging básico
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# =====================
# CONFIGURACIÓN
# =====================
sitio = {
    "url": "http://portalpsg.gred.entelpcs.cl/index.php",
    "usuario": "",
    "password": "",
    "selector_user": 'input[name="usuario"]',
    "selector_pass": 'input[name="password"]',
    "selector_btn_login": 'input[type="submit"]',
    "post_login_url": "http://portalpsg.gred.entelpcs.cl/tp/ver_planned.php?id="
}

# =====================
# VARIABLES GLOBALES
# =====================
playwright_inst = None
browser = None
page = None

ruta_pdf_1 = ""
ruta_pdf_2 = ""

tp_validado = False
tp_iniciado = False
ui_activa = False

texto_bitacora = ""
datos_tp_actual = {}
cola_tareas = Queue()
procesando_tarea = False
ids_tareas_activas = set()
pendientes_inicio = {}
MAX_TAREAS_ACTIVAS = 10

# =====================
# TELEGRAM
# =====================

ANEXO_TRANSPORTE = "22 360 2288"
GROUP_CHAT_ID = -1003951764888

MSG_SITIO_MOVIL = (
    "El TP ingresado no puede ser iniciado por nosotros, ya que hay un Sitio Móvil involucrado. "
    "Favor de contactar a Primera Linea de RAN Telegram: +56 9 8761 0440 donde le atenderá un ingeniero especializado."
)

def enviar_mensaje_telegram(chat_id, mensaje, reply_markup=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": mensaje}
        if reply_markup is None:
            payload["text"] = (
                f"{mensaje}\n\n"
                "Seleccione una opción:\n"
                "1: Iniciar TP\n"
                "2: Cerrar TP"
            )
            payload["reply_markup"] = teclado_menu_telegram()
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        requests.post(url, json=payload)
    except Exception as e:
        print("Error Telegram:", e)

def notificar_grupo(mensaje):
    """Notificaciones al grupo deshabilitadas para reiniciar el flujo base."""
    return

def notificar_admin(mensaje, reply_markup=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": GROUP_CHAT_ID, "text": mensaje}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        requests.post(url, json=payload)
    except Exception as e:
        print("Error notificacion admin:", e)

def teclado_menu_telegram():
    return {
        "keyboard": [[{"text": "1️⃣ Iniciar TP"}, {"text": "2️⃣ Cerrar TP"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
        "input_field_placeholder": "Seleccione una opción..."
    }

def teclado_volver_telegram():
    return {
        "keyboard": [[{"text": "↩️ Volver atrás"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
        "input_field_placeholder": "Ingrese el dato o vuelva atrás..."
    }

def aplicacion_disponible():
    return ui_activa

def cerrar_aplicacion():
    global ui_activa
    ui_activa = False
    ventana.destroy()

# =====================
# LOGIN
# =====================
def mostrar_login():
    login = tk.Toplevel()
    login.title("Login Operador")
    login.geometry("320x220")
    login.resizable(False, False)
    login.grab_set()

    tk.Label(login, text="Usuario Portal").pack(pady=(20, 5))
    entry_user = tk.Entry(login)
    entry_user.pack()

    tk.Label(login, text="Contraseña Portal").pack(pady=(10, 5))
    entry_pass = tk.Entry(login, show="*")
    entry_pass.pack()

    def ingresar():
        user = entry_user.get().strip()
        pwd = entry_pass.get().strip()

        if not user or not pwd:
            messagebox.showwarning("Atención", "Ingrese usuario y contraseña")
            return

        sitio["usuario"] = user
        sitio["password"] = pwd

        try:
            iniciar_navegador()
            login.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"No fue posible iniciar sesión:\n{str(e)}")

    ttk.Button(login, text="Ingresar", command=ingresar).pack(pady=20)

# =====================
# PLAYWRIGHT
# =====================
def hacer_login():
    page.goto(sitio["url"])
    page.fill(sitio["selector_user"], sitio["usuario"])
    page.fill(sitio["selector_pass"], sitio["password"])
    page.click(sitio["selector_btn_login"])
    page.wait_for_timeout(2000)

def iniciar_navegador():
    global playwright_inst, browser, page

    playwright_inst = sync_playwright().start()

    browser = playwright_inst.chromium.launch(
        channel="msedge",
        headless=False,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled"
        ],
        ignore_default_args=["--enable-automation"]
    )

    context = browser.new_context(no_viewport=True)
    page = context.new_page()
    page.set_default_timeout(10000)
    hacer_login()

def restaurar_sesion():
    try:
        hacer_login()
        messagebox.showinfo("Sesión", "Sesión restaurada correctamente ✅")
    except Exception as e:
        logger.exception("Error al restaurar sesión: %s", e)
        try:
            if browser:
                browser.close()
            if playwright_inst:
                playwright_inst.stop()
        except Exception as e2:
            logger.exception("Error cerrando navegador: %s", e2)
        iniciar_navegador()

# =====================
# PDF
# =====================
def buscar_en_pdf(numero):
    rutas = [ruta_pdf_1, ruta_pdf_2]

    for ruta in rutas:
        if not ruta:
            continue
        try:
            reader = PdfReader(ruta)
            texto = ""
            for p in reader.pages:
                contenido = p.extract_text()
                if contenido:
                    texto += contenido
            if numero in texto:
                return True
        except Exception as e:
            logger.exception("Error leyendo PDF %s: %s", ruta, e)

    return False

def cargar_pdf_1():
    global ruta_pdf_1
    archivo = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
    if archivo:
        ruta_pdf_1 = archivo
        label_pdf_1.config(text=f"📄 {os.path.basename(archivo)}", fg="green")

def cargar_pdf_2():
    global ruta_pdf_2
    archivo = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
    if archivo:
        ruta_pdf_2 = archivo
        label_pdf_2.config(text=f"📄 {os.path.basename(archivo)}", fg="green")

# =====================
# EXTRACCIÓN DATOS
# =====================
def extraer_valor_por_encabezado(nombre_encabezado):
    try:
        return page.evaluate(
            """(nombre) => {
                const limpiar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
                const normalizar = (txt) => limpiar(txt).toLowerCase();
                const objetivo = normalizar(nombre);

                for (const tabla of Array.from(document.querySelectorAll('table'))) {
                    const filas = Array.from(tabla.querySelectorAll('tr')).map((fila) =>
                        Array.from(fila.querySelectorAll('th,td')).map((celda) => limpiar(celda.innerText))
                    );

                    for (let f = 0; f < filas.length; f++) {
                        for (let c = 0; c < filas[f].length; c++) {
                            if (normalizar(filas[f][c]) === objetivo) {
                                const valores = [];
                                for (let siguiente = f + 1; siguiente < filas.length; siguiente++) {
                                    const valor = filas[siguiente][c];
                                    if (valor && !valores.includes(valor)) valores.push(valor);
                                }

                                if (valores.length) return valores.join(' | ');

                                const valorDerecha = filas[f][c + 1];
                                if (valorDerecha) return valorDerecha;
                            }
                        }
                    }
                }

                return 'N/A';
            }""",
            nombre_encabezado
        )
    except Exception as e:
        logger.exception("Error extrayendo encabezado %s: %s", nombre_encabezado, e)
        return "N/A"

def extraer_datos_trabajo():
    titulo = page.locator("h1").inner_text().strip()
    m = re.search(r"\d+", titulo)
    if not m:
        logger.error("No se encontró número TP en título: %s", titulo)
        raise ValueError("Número TP no encontrado en título")
    numero = m.group()

    tabla = page.locator("table.sample").first
    fila = tabla.locator("tr").nth(1)

    desc_raw = fila.locator("td").nth(0).inner_text().strip()
    match = re.search(r":\s*(.*?)\s*:", desc_raw)
    descripcion = match.group(1) if match else desc_raw

    try:
        rpn = int(fila.locator("td").nth(2).inner_text().strip())
    except Exception as e:
        logger.exception("Error parseando RPN: %s", e)
        rpn = 0

    try:
        fecha_raw = fila.locator("td").nth(4).inner_text().strip()
        fecha_obj = datetime.strptime(fecha_raw, "%Y-%m-%d %H:%M:%S")
        fecha_plan = fecha_obj.strftime("%Y-%m-%d")
    except Exception as e:
        logger.exception("Error parseando fecha: %s", e)
        fecha_plan = "N/A"

    estado = fila.locator("td").nth(3).inner_text().strip().upper()
    lugar = extraer_valor_por_encabezado("Lugar")

    return {
        "numero": numero,
        "titulo": titulo,
        "descripcion": descripcion,
        "rpn": rpn,
        "fecha_plan": fecha_plan,
        "estado": estado,
        "lugar": lugar
    }

def obtener_aviso_lugar():
    lugar = datos_tp_actual.get("lugar", "N/A")
    if lugar and lugar != "N/A":
        return f"📍 Lugar: {lugar}\n"
    return "📍 Lugar: No encontrado\n"

def validar_fecha_plan_hoy(datos=None):
    info = datos or datos_tp_actual
    fecha_plan = info.get("fecha_plan", "N/A")
    fecha_hoy = datetime.now().date()
    try:
        fecha_tp = datetime.strptime(fecha_plan, "%Y-%m-%d").date()
    except Exception:
        return False, fecha_plan, fecha_hoy.strftime("%Y-%m-%d")
    return fecha_tp == fecha_hoy, fecha_plan, fecha_hoy.strftime("%Y-%m-%d")

def mensaje_fecha_plan_no_corresponde(numero_tp):
    _, fecha_plan, fecha_hoy = validar_fecha_plan_hoy()
    return (
        f"⚠️ TP {numero_tp} no corresponde a la fecha actual.\n\n"
        f"📅 Fecha planificación: {fecha_plan}\n"
        f"📅 Fecha actual: {fecha_hoy}\n\n"
        "Solo se pueden iniciar TP planificados para el día de hoy."
    )

def obtener_aviso_rpn():
    rpn = datos_tp_actual.get("rpn", "N/A")
    return f"🔢 RPN: {rpn}\n"

def obtener_aviso_rpn_bloqueado():
    if rpn_es_2500():
        return "🔢 RPN: 2500\n"
    return ""

def rpn_es_2500():
    return datos_tp_actual.get("rpn") == 2500

def lugar_es_sitios():
    lugar = datos_tp_actual.get("lugar", "")
    lugares = [valor.strip().upper() for valor in lugar.split("|")]
    return "SITIOS" in lugares

PALABRAS_BLOQUEO_TP = [
    "WDM",
    "RTN",
    "SATELITAL",
    "MHL3000",
    "OSN1800",
    "OSN 1800",
    "OSN3500",
    "OSN 3500",
    "OSN9800",
    "OSN 9800",
    "OSN8800",
    "OSN 8800",
    "Red Acceso FO RM",
    "Intervencion de Mufa",
    "OLT",
    "RED GPON",
]

def obtener_aviso_wdm():
    try:
        texto_pagina = page.locator("body").inner_text().upper()
    except Exception as e:
        logger.exception("Error leyendo página para aviso palabras bloqueo TP: %s", e)
        try:
            texto_pagina = page.content().upper()
        except Exception as e2:
            logger.exception("Error obteniendo contenido de página: %s", e2)
            texto_pagina = ""

    try:
        titulo = page.locator("h1").inner_text().upper()
        texto_pagina += " " + titulo
    except Exception:
        pass

    for palabra in PALABRAS_BLOQUEO_TP:
        if palabra in texto_pagina:
            return f"🔎 {palabra}: Detectado en la página del TP\n"

    return ""

# =====================
# VALIDAR TP — retorna estado string
# =====================
def ejecutar_validacion(event=None):
    global tp_validado, datos_tp_actual

    numero = entry_trabajo.get().strip()

    if not numero:
        messagebox.showwarning("Atención", "Ingrese número TP")
        return None

    if not ruta_pdf_1 and not ruta_pdf_2:
        messagebox.showwarning("Atención", "Debe cargar al menos un PDF")
        return "SIN_PDF"

    if not buscar_en_pdf(numero):
        label_resultado.config(text="❌ TP no existe en PDFs", fg="red")
        return "NO_PDF"

    try:
        page.goto(sitio["post_login_url"] + numero)
        page.wait_for_timeout(2000)

        datos = extraer_datos_trabajo()
        datos_tp_actual = datos
        estado = datos["estado"]

        btn_iniciar.config(state="disabled")
        btn_finalizar.config(state="disabled")

        if estado == "POSPUESTO":
            label_resultado.config(text="❌ TP POSPUESTO", fg="orange")
            return "POSPUESTO"

        if estado == "EN GESTION":
            label_resultado.config(text="❌ TP EN GESTION", fg="orange")
            return "EN_GESTION"

        if estado == "EJECUTADO":
            label_resultado.config(text="❌ TP EJECUTADO", fg="red")
            return "EJECUTADO"

        if "EJECUCION" in estado:
            label_resultado.config(text="⚠️ TP EN EJECUCIÓN", fg="orange")
            label_rpn.config(
                text=f"RPN: {datos['rpn']} | 📅 {datos['fecha_plan']}",
                fg="blue"
            )
            btn_finalizar.config(state="normal")
            tp_validado = True
            return "EN_EJECUCION"

        color_fecha = "green"
        try:
            fecha_tp = datetime.strptime(datos["fecha_plan"], "%Y-%m-%d").date()
            if fecha_tp != datetime.now().date():
                color_fecha = "red"
        except:  # noqa: E722
            pass

        label_resultado.config(text=f"✅ TP VALIDADO ({estado})", fg="green")
        label_rpn.config(
            text=f"RPN: {datos['rpn']} | 📅 {datos['fecha_plan']}",
            fg=color_fecha
        )

        if "PLANIFICADO" in estado:
            btn_iniciar.config(state="normal")

        tp_validado = True
        return "PLANIFICADO"

    except Exception as e:
        messagebox.showerror("Error", f"No fue posible validar TP:\n{str(e)}")
        return "ERROR"

# =====================
# BITÁCORA INICIO
# =====================
def insertar_bitacora():
    global texto_bitacora

    nombre = entry_nombre.get().strip()
    telefono = entry_telefono.get().strip()
    empresa = entry_empresa.get().strip()

    if not nombre or not telefono:
        messagebox.showwarning("Atención", "Nombre y teléfono obligatorios")
        return False

    hora = datetime.now().strftime("%H:%M")
    texto_bitacora = f"{nombre}, Cel {telefono}"

    if empresa:
        texto_bitacora += f", Empresa {empresa}"

    texto_bitacora += f" inicia TP a las {hora} hrs"

    try:
        page.click("text=Documentar desarrollo de trabajo")
        page.wait_for_timeout(1500)

        textarea = page.locator("textarea").first
        textarea.click()
        page.keyboard.type(texto_bitacora, delay=20)
        page.click("input[type='submit']")
        page.wait_for_timeout(2000)

        return True

    except Exception as e:
        messagebox.showerror("Bitácora", f"No fue posible documentar:\n{str(e)}")
        return False

# =====================
# INICIAR TP
# =====================
def iniciar_tp():
    global tp_iniciado

    if not tp_validado:
        messagebox.showwarning("Atención", "Debe validar TP")
        return False

    try:
        datos = extraer_datos_trabajo()
        fecha_ok, fecha_plan, fecha_hoy = validar_fecha_plan_hoy(datos)
        if not fecha_ok:
            messagebox.showerror(
                "Bloqueado",
                "No puede iniciar un TP que no corresponde a la fecha actual.\n\n"
                f"Fecha planificación: {fecha_plan}\n"
                f"Fecha actual: {fecha_hoy}"
            )
            return False
    except Exception as e:
        logger.exception("No fue posible validar fecha de planificación: %s", e)
        messagebox.showerror("Bloqueado", "No fue posible validar la fecha de planificación del TP")
        return False

    try:
        page.click("text=Iniciar Ejecucion")
        page.wait_for_timeout(1500)
        page.click("input[type='submit']")
        page.wait_for_timeout(2000)

        ok = insertar_bitacora()
        if not ok:
            return False

        tp_iniciado = True
        btn_iniciar.config(state="disabled")
        btn_finalizar.config(state="normal")
        return True

    except Exception as e:
        messagebox.showerror("Error", f"No fue posible iniciar TP:\n{str(e)}")
        return False

# =====================
# MODAL FINALIZAR TP (uso manual desde UI)
# =====================
def mostrar_finalizar_tp(nombre_inicial="", telefono_inicial="", auto_confirmar=False, on_result=None, mostrar_error=True):
    if not auto_confirmar and not nombre_inicial:
        nombre_inicial = entry_nombre.get().strip()
    if not auto_confirmar and not telefono_inicial:
        telefono_inicial = entry_telefono.get().strip()

    if not tp_validado:
        if mostrar_error:
            messagebox.showwarning("Atención", "Debe validar TP primero")
        if on_result:
            on_result(False)
        return

    datos = extraer_datos_trabajo()

    if "EJECUCION" not in datos["estado"]:
        if mostrar_error:
            messagebox.showwarning("Estado inválido", "El TP no está en ejecución")
        if on_result:
            on_result(False)
        return

    ventana_cierre = tk.Toplevel()
    ventana_cierre.title("Finalizar TP")
    ventana_cierre.geometry("320x240")
    ventana_cierre.resizable(False, False)
    ventana_cierre.grab_set()

    tk.Label(ventana_cierre, text="Nombre quien finaliza").pack(pady=(20, 5))
    entry_nombre_cierre = tk.Entry(ventana_cierre)
    entry_nombre_cierre.pack(fill="x", padx=20)
    if nombre_inicial:
        entry_nombre_cierre.insert(0, nombre_inicial)

    tk.Label(ventana_cierre, text="Teléfono").pack(pady=(12, 5))
    entry_telefono_cierre = tk.Entry(ventana_cierre)
    entry_telefono_cierre.pack(fill="x", padx=20)
    if telefono_inicial:
        entry_telefono_cierre.insert(0, telefono_inicial)

    def confirmar_cierre():
        nombre = entry_nombre_cierre.get().strip()
        telefono = entry_telefono_cierre.get().strip()

        if not nombre or not telefono:
            if mostrar_error:
                messagebox.showwarning("Atención", "Debe ingresar nombre y teléfono")
            if on_result:
                on_result(False)
            return

        ok = finalizar_tp(nombre, telefono, mostrar_error=mostrar_error)
        ventana_cierre.destroy()
        if on_result:
            on_result(ok)

    ttk.Button(ventana_cierre, text="🔒 Confirmar cierre", command=confirmar_cierre).pack(pady=28)
    if auto_confirmar:
        ventana_cierre.after(500, confirmar_cierre)


def completar_formulario_cierre(nombre, telefono, texto_cierre):
    """Completa el formulario web de cierre usando campos separados o textarea."""
    comentario = page.locator("textarea[name='comentario']").first
    inventario_datos = page.locator("textarea[name='inventario_datos']").first

    comentario_ok = comentario.count() > 0
    inventario_ok = inventario_datos.count() > 0

    if comentario_ok:
        comentario.fill(texto_cierre)

    if inventario_ok:
        inventario_datos.fill("..")

    if comentario_ok or inventario_ok:
        return

    campos_nombre = [
        "input[name*='nombre' i]",
        "input[id*='nombre' i]",
        "input[name*='responsable' i]",
        "input[id*='responsable' i]",
        "input[name*='usuario' i]",
        "input[id*='usuario' i]",
    ]
    campos_telefono = [
        "input[name*='fono' i]",
        "input[id*='fono' i]",
        "input[name*='telef' i]",
        "input[id*='telef' i]",
        "input[name*='cel' i]",
        "input[id*='cel' i]",
    ]

    nombre_ok = False
    telefono_ok = False

    for selector in campos_nombre:
        campo = page.locator(selector).first
        if campo.count() > 0:
            campo.fill(nombre)
            nombre_ok = True
            break

    for selector in campos_telefono:
        campo = page.locator(selector).first
        if campo.count() > 0:
            campo.fill(telefono)
            telefono_ok = True
            break

    if nombre_ok or telefono_ok:
        return

    textarea_final = page.locator("textarea").first
    textarea_final.click()
    page.keyboard.type(texto_cierre, delay=20)


def click_primero_disponible(selectores):
    for selector in selectores:
        locator = page.locator(selector).first
        if locator.count() > 0:
            locator.click()
            return True
    return False

# =====================
# FINALIZAR TP (llamado directo desde Telegram o modal)
# =====================
def finalizar_tp(nombre, telefono, mostrar_error=True):
    hora = datetime.now().strftime("%H:%M")
    texto_cierre = f"{nombre}, Cel {telefono} finaliza TP a las {hora} hrs"

    try:
        print(f"🔒 Iniciando cierre TP con nombre={nombre} telefono={telefono}")
        datos = extraer_datos_trabajo()
        numero_tp = datos["numero"]

        # Documentar en bitácora
        page.click("text=Documentar desarrollo de trabajo")
        page.wait_for_timeout(1500)

        textarea = page.locator("textarea").first
        textarea.click()
        page.keyboard.type(texto_cierre, delay=20)
        page.click("input[type='submit']")
        page.wait_for_timeout(2000)

        # Volver al TP y finalizar
        page.goto(sitio["post_login_url"] + numero_tp)
        page.wait_for_timeout(2000)

        if not click_primero_disponible([
            "text=Finalizar Ejecucion",
            "text=Finalizar Ejecución",
            "input[value*='Finalizar Ejecucion' i]",
            "input[value*='Finalizar Ejecución' i]",
            "button:has-text('Finalizar Ejecucion')",
            "button:has-text('Finalizar Ejecución')",
        ]):
            raise Exception("No se encontró el botón Finalizar Ejecucion")
        page.wait_for_timeout(1500)

        completar_formulario_cierre(nombre, telefono, texto_cierre)

        if not click_primero_disponible([
            "input[name='accion'][value='Confirmar']",
            "input[value*='Confirmar' i]",
            "button:has-text('Confirmar')",
            "text=Confirmar",
        ]):
            raise Exception("No se encontró el botón Confirmar")
        page.wait_for_timeout(2500)

        btn_finalizar.config(state="disabled")
        print(f"✅ Cierre TP {numero_tp} completado")
        return True

    except Exception as e:
        logger.exception("No fue posible finalizar TP: %s", e)
        if mostrar_error:
            messagebox.showerror("Error", f"No fue posible finalizar TP:\n{str(e)}")
        return False

# =====================
# EXPORTAR TXT
# =====================
def exportar_txt():
    if not tp_iniciado:
        messagebox.showwarning("Atención", "Debe iniciar TP primero")
        return

    try:
        datos = extraer_datos_trabajo()
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bitacora_tp.txt")

        linea = (
            f"TP {datos['numero']} {datos['descripcion']}:\n"
            f"{texto_bitacora}\n\n"
        )

        with open(ruta, "a", encoding="utf-8") as archivo:
            archivo.write(linea)

        os.startfile(ruta)

    except Exception as e:
        messagebox.showerror("Error", f"No se pudo exportar:\n{str(e)}")

def marcar_tp_finalizado_txt(numero_tp):
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bitacora_tp.txt")

    try:
        if not os.path.exists(ruta):
            logger.warning("No existe bitacora_tp.txt para marcar TP %s como finalizado", numero_tp)
            return False

        with open(ruta, "r", encoding="utf-8") as archivo:
            lineas = archivo.readlines()

        marcador = "//finalizado"
        actualizado = False
        patron_tp = re.compile(rf"\bTP\s+{re.escape(str(numero_tp))}\b")

        for i, linea in enumerate(lineas):
            if patron_tp.search(linea) and marcador not in linea:
                lineas[i] = linea.rstrip("\r\n") + f" {marcador}\n"
                actualizado = True
                break

        if not actualizado:
            logger.warning("No se encontró TP %s sin marcar en bitacora_tp.txt", numero_tp)
            return False

        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.writelines(lineas)

        return True

    except Exception as e:
        logger.exception("No se pudo marcar TP %s como finalizado en TXT: %s", numero_tp, e)
        return False

# =====================
# PROCESAR COLA TELEGRAM
# =====================
def actualizar_estado_telegram(estado_ref, **nuevo_estado):
    if isinstance(estado_ref, dict):
        estado_ref.clear()
        if nuevo_estado.get("paso") in {"numero", "nombre", "telefono", "empresa"}:
            nuevo_estado["ultimo_paso_en"] = datetime.now()
        estado_ref.update(nuevo_estado)

def generar_id_tarea(accion):
    prefijo = "INI" if accion == "iniciar" else "CIE"
    for _ in range(900):
        tarea_id = f"{prefijo}-{random.randint(100, 999)}"
        if tarea_id not in ids_tareas_activas:
            ids_tareas_activas.add(tarea_id)
            return tarea_id
    timestamp = datetime.now().strftime("%H%M%S")
    tarea_id = f"{prefijo}-{timestamp[-3:]}"
    ids_tareas_activas.add(tarea_id)
    return tarea_id

def total_tareas_activas():
    return cola_tareas.qsize() + len(pendientes_inicio) + (1 if procesando_tarea else 0)

def enviar_solicitud_inicio_admin(datos):
    tp_info = datos.get("tp_info", {})
    empresa = datos.get("empresa", "") or "No informada"
    tarea_id = datos["tarea_id"]
    accion_texto = "inicio" if datos.get("accion") == "iniciar" else "cierre"
    notificar_admin(
        f"Solicitud de {accion_texto} de TP {datos['numero']} ID {tarea_id}\n\n"
        f"📄 Descripción: {tp_info.get('descripcion', 'N/A')}\n"
        f"🔢 RPN: {tp_info.get('rpn', 'N/A')}\n"
        f"📅 Fecha plan: {tp_info.get('fecha_plan', 'N/A')}\n"
        f"👤 Solicitante: {datos['nombre']}\n"
        f"📱 Teléfono: {datos['telefono']}\n"
        f"🏢 Empresa: {empresa}\n\n"
        f"Responder:\n"
        f"/SI {tarea_id}\n"
        f"/NO {tarea_id}",
        reply_markup={
            "inline_keyboard": [[
                {"text": f"✅ SI {tarea_id}", "callback_data": f"SI:{tarea_id}"},
                {"text": f"❌ NO {tarea_id}", "callback_data": f"NO:{tarea_id}"}
            ]]
        }
    )

def aprobar_inicio_pendiente(tarea_id):
    tarea_id = tarea_id.strip().upper()
    datos = pendientes_inicio.pop(tarea_id, None)
    if not datos:
        return False, f"No hay solicitud pendiente con ID {tarea_id}."

    datos["aprobado_admin"] = True
    cola_telegram.put(datos)
    accion_admin = "INICIO_APROBADO" if datos.get("accion") == "iniciar" else "CIERRE_APROBADO"
    print(f"✅ {accion_admin} {tarea_id} enviado a cola_telegram — tamaño: {cola_telegram.qsize()}")
    notificar_admin(f"✅ {accion_admin} {tarea_id} TP {datos['numero']}")
    return True, f"✅ Solicitud {tarea_id} aprobada. Entró al flujo de atención."

def obtener_unico_inicio_pendiente():
    if len(pendientes_inicio) == 1:
        return next(iter(pendientes_inicio))
    return None

def rechazar_inicio_pendiente(tarea_id):
    tarea_id = tarea_id.strip().upper()
    datos = pendientes_inicio.pop(tarea_id, None)
    if not datos:
        return False, f"No hay solicitud pendiente con ID {tarea_id}."

    ids_tareas_activas.discard(tarea_id)
    actualizar_estado_telegram(datos.get("estado_ref"), paso="menu")
    enviar_mensaje_telegram(
        datos.get("chat_id"),
        f"⚠️ Tu solicitud {datos['numero']} no fue aprobada.\n"
        f"Por favor contacta al anexo {ANEXO_TRANSPORTE}."
    )
    accion_admin = "INICIO_RECHAZADO" if datos.get("accion") == "iniciar" else "CIERRE_RECHAZADO"
    notificar_admin(f"❌ {accion_admin} {tarea_id} TP {datos['numero']}")
    return True, f"❌ Solicitud {tarea_id} rechazada."

def recibir_tarea_telegram(datos):
    if total_tareas_activas() >= MAX_TAREAS_ACTIVAS:
        actualizar_estado_telegram(datos.get("estado_ref"), paso="menu")
        enviar_mensaje_telegram(
            datos.get("chat_id"),
            "⚠️ En este momento hay muchas solicitudes en espera.\n\n"
            f"Por favor intenta nuevamente en unos minutos. Si es urgente, contacta al anexo {ANEXO_TRANSPORTE}."
        )
        return

    tarea_id = datos.get("tarea_id") or generar_id_tarea(datos.get("accion"))
    datos["tarea_id"] = tarea_id

    if datos.get("accion") in ("iniciar", "cerrar") and not datos.get("aprobado_admin"):
        pendientes_inicio[tarea_id] = datos
        actualizar_estado_telegram(
            datos.get("estado_ref"),
            paso="esperando_aprobacion_inicio",
            accion=datos.get("accion"),
            numero=datos.get("numero"),
            tarea_id=tarea_id
        )
        enviar_solicitud_inicio_admin(datos)
        enviar_mensaje_telegram(
            datos.get("chat_id"),
            f"⏳ Tu solicitud {datos['numero']} está siendo validada.\n"
            "Favor atento a esta conversación.",
            reply_markup={"remove_keyboard": True}
        )
        return

    cola_tareas.put(datos)
    print(f"📥 Tarea {tarea_id} en cola_tareas — tamaño: {cola_tareas.qsize()}")
    actualizar_estado_telegram(
        datos.get("estado_ref"),
        paso="en_cola",
        accion=datos.get("accion"),
        numero=datos.get("numero"),
        tarea_id=tarea_id
    )

    if procesando_tarea:
        enviar_mensaje_telegram(
            datos.get("chat_id"),
            f"⏳ Solicitud {tarea_id} recibida.\n\n"
            "En este momento se están procesando solicitudes previas de otros colegas. "
            "Te avisaremos por este chat cuando comience tu atención.",
            reply_markup={"remove_keyboard": True}
        )
    else:
        enviar_mensaje_telegram(
            datos.get("chat_id"),
            f"✅ Solicitud {tarea_id} recibida.\n\n"
            "Será procesada a continuación.",
            reply_markup={"remove_keyboard": True}
        )

def finalizar_tarea(datos):
    global procesando_tarea
    tarea_id = datos.get("tarea_id")
    if tarea_id:
        ids_tareas_activas.discard(tarea_id)
    procesando_tarea = False
    ventana.after(500, procesar_cola_telegram)

def responder_prevalidacion_telegram(datos):
    chat_id = datos.get("chat_id")
    estado_ref = datos.get("estado_ref")
    numero_tp = datos.get("numero")
    accion = datos.get("accion")

    entry_trabajo.delete(0, tk.END)
    entry_trabajo.insert(0, numero_tp)

    estado_tp = ejecutar_validacion()
    aviso_wdm = ""
    aviso_lugar = ""
    aviso_rpn_general = ""
    aviso_rpn = ""

    if estado_tp not in ("SIN_PDF", "NO_PDF", None):
        aviso_wdm = obtener_aviso_wdm()
        aviso_lugar = obtener_aviso_lugar()
        aviso_rpn_general = obtener_aviso_rpn()
        aviso_rpn = obtener_aviso_rpn_bloqueado()

    def volver_menu(mensaje):
        actualizar_estado_telegram(estado_ref, paso="menu")
        enviar_mensaje_telegram(
            chat_id,
            f"{mensaje}\n\nSeleccione una opción:\n1: Iniciar TP\n2: Cerrar TP",
            reply_markup=teclado_menu_telegram()
        )

    def continuar_flujo(mensaje):
        actualizar_estado_telegram(
            estado_ref,
            paso="nombre",
            accion=accion,
            numero=numero_tp,
            tp_info={
                "descripcion": datos_tp_actual.get("descripcion", "N/A"),
                "rpn": datos_tp_actual.get("rpn", "N/A"),
                "fecha_plan": datos_tp_actual.get("fecha_plan", "N/A"),
                "lugar": datos_tp_actual.get("lugar", "N/A"),
            }
        )
        enviar_mensaje_telegram(chat_id, mensaje, reply_markup=teclado_volver_telegram())

    if estado_tp == "SIN_PDF":
        volver_menu(
            "⚠️ El sistema no está disponible en este momento.\n\n"
            "No hay PDFs cargados para validar el TP.\n"
            f"Por favor contacte a la oficina al anexo: {ANEXO_TRANSPORTE}"
        )
        return

    if estado_tp == "NO_PDF":
        volver_menu(f"❌ TP {numero_tp} no fue encontrado en los PDFs disponibles.")
        return

    if estado_tp in ("ERROR", None):
        volver_menu(
            "⚠️ El sistema no está disponible en este momento.\n\n"
            f"Por favor contacte a la oficina al anexo: {ANEXO_TRANSPORTE}"
        )
        return

    if accion == "iniciar":
        if estado_tp == "POSPUESTO":
            volver_menu(f"⚠️ TP {numero_tp} se encuentra POSPUESTO. No es posible iniciarlo.")
            return

        if estado_tp == "EN_GESTION":
            volver_menu(f"TP requiere ser iniciado llamando al número de transporte: {ANEXO_TRANSPORTE}")
            return

        if estado_tp == "EJECUTADO":
            volver_menu(f"ℹ️ TP {numero_tp} ya fue EJECUTADO y cerrado anteriormente.")
            return

        if estado_tp == "EN_EJECUCION":
            volver_menu(f"⚠️ TP {numero_tp} ya se encuentra iniciado. No es posible iniciarlo nuevamente.")
            return

        if estado_tp == "PLANIFICADO":
            fecha_ok, _, _ = validar_fecha_plan_hoy()
            if not fecha_ok:
                volver_menu(mensaje_fecha_plan_no_corresponde(numero_tp))
                return

            if lugar_es_sitios():
                volver_menu(MSG_SITIO_MOVIL)
                return

            if aviso_wdm or rpn_es_2500():
                volver_menu(
                    f"TP requiere ser iniciado llamando al número de transporte: {ANEXO_TRANSPORTE}"
                )
                return

            continuar_flujo(
                f"✅ TP {numero_tp} validado correctamente.\n"
                f"📄 Descripción: {datos_tp_actual.get('descripcion', 'N/A')}\n"
                "\n👤 Ingrese su nombre y apellido:\n"
                "(Ejemplo: Juan Pérez)\n\n"
                "Escriba volver o pulse el botón ↩️ Volver atrás."
            )
            return

    if accion == "cerrar":
        if estado_tp == "EN_EJECUCION":
            if aviso_wdm or lugar_es_sitios() or rpn_es_2500():
                volver_menu(
                    f"TP requiere ser cerrado llamando al número de transporte: {ANEXO_TRANSPORTE}"
                )
                return

            continuar_flujo(
                f"✅ TP {numero_tp} validado para cierre.\n"
                f"📄 Descripción: {datos_tp_actual.get('descripcion', 'N/A')}\n"
                "\n👤 Ingrese su nombre y apellido:\n"
                "(Ejemplo: Juan Pérez)\n\n"
                "Escriba volver o pulse el botón ↩️ Volver atrás."
            )
            return

        if estado_tp == "PLANIFICADO":
            volver_menu(f"⚠️ TP {numero_tp} aún no ha sido iniciado. No es posible cerrarlo.")
            return

        if estado_tp == "EJECUTADO":
            volver_menu(f"ℹ️ TP {numero_tp} ya fue cerrado anteriormente.")
            return

        if estado_tp == "POSPUESTO":
            volver_menu(f"⚠️ TP {numero_tp} se encuentra POSPUESTO. No es posible cerrarlo.")
            return

        if estado_tp == "EN_GESTION":
            volver_menu(f"TP requiere ser gestionado llamando al número de transporte: {ANEXO_TRANSPORTE}")
            return

    volver_menu(f"⚠️ TP {numero_tp} no se encuentra en un estado válido para esta operación.")

def procesar_cola_telegram():
    global tp_validado, procesando_tarea

    if procesando_tarea:
        if not cola_telegram.empty():
            datos_entrada = cola_telegram.get()
            if datos_entrada.get("tipo") == "prevalidar":
                actualizar_estado_telegram(datos_entrada.get("estado_ref"), paso="menu")
                enviar_mensaje_telegram(
                    datos_entrada.get("chat_id"),
                    "⏳ En este momento se están procesando solicitudes previas de otros colegas.\n\n"
                    "Por favor intenta nuevamente en unos minutos."
                )
            else:
                recibir_tarea_telegram(datos_entrada)
        ventana.after(1000, procesar_cola_telegram)
        return

    if not cola_tareas.empty():
        datos = cola_tareas.get()
        procesando_tarea = True
        chat_id = datos.get("chat_id")
        actualizar_estado_telegram(
            datos.get("estado_ref"),
            paso="procesando",
            accion=datos.get("accion"),
            numero=datos.get("numero"),
            tarea_id=datos.get("tarea_id")
        )
        enviar_mensaje_telegram(
            chat_id,
            f"✅ Solicitud {datos.get('tarea_id')} en atención.\n\n"
            f"Estamos procesando tu TP {datos.get('numero')}.",
            reply_markup={"remove_keyboard": True}
        )
    elif not cola_telegram.empty():

        datos = cola_telegram.get()
        chat_id = datos.get("chat_id")

        print("📩 Datos desde Telegram:", datos)

        if datos.get("tipo") == "prevalidar":
            responder_prevalidacion_telegram(datos)
            ventana.after(1000, procesar_cola_telegram)
            return

        if datos.get("aprobado_admin"):
            print(f"📥 Solicitud aprobada recibida por UI: {datos.get('tarea_id')} TP {datos.get('numero')}")

        recibir_tarea_telegram(datos)
        ventana.after(1000, procesar_cola_telegram)
        return
    else:
        ventana.after(1000, procesar_cola_telegram)
        return

    print("📩 Procesando tarea:", datos)
    if True:

        # Cargar número en UI y validar
        entry_trabajo.delete(0, tk.END)
        entry_trabajo.insert(0, datos["numero"])

        entry_nombre.delete(0, tk.END)
        entry_telefono.delete(0, tk.END)
        entry_empresa.delete(0, tk.END)

        if datos["accion"] == "iniciar":
            entry_nombre.insert(0, datos["nombre"])
            entry_telefono.insert(0, datos["telefono"])
            entry_empresa.insert(0, datos.get("empresa", ""))

        estado_tp = ejecutar_validacion()

        hora = datetime.now().strftime("%H:%M")
        accion_texto = "INICIAR" if datos["accion"] == "iniciar" else "CERRAR"
        aviso_wdm = ""
        aviso_lugar = ""
        aviso_rpn = ""

        if estado_tp not in ("SIN_PDF", "NO_PDF", None):
            aviso_wdm = obtener_aviso_wdm()
            aviso_lugar = obtener_aviso_lugar()
            aviso_rpn = obtener_aviso_rpn_bloqueado()

        MSG_SISTEMA_NO_DISPONIBLE = (
            "⚠️ El sistema no está disponible en este momento.\n\n"
            "Por favor contacte a la oficina al anexo:\n"
            f"📞 {ANEXO_TRANSPORTE}\n\n"
            "Un operador podrá asistirle y restablecer el sistema."
        )

        # ── INICIAR ──────────────────────────────────────
        if datos["accion"] == "iniciar":

            if estado_tp == "SIN_PDF":
                enviar_mensaje_telegram(chat_id, MSG_SISTEMA_NO_DISPONIBLE)
                notificar_grupo(
                    f"⚠️ Solicitud fallida — Sin PDF cargado\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "NO_PDF":
                enviar_mensaje_telegram(chat_id,
                    f"❌ TP {datos['numero']} no fue encontrado en los PDFs del día.")
                notificar_grupo(
                    f"❌ TP no encontrado en PDFs\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "POSPUESTO":
                enviar_mensaje_telegram(chat_id,
                    f"⚠️ TP {datos['numero']} se encuentra POSPUESTO. No es posible iniciarlo.")
                notificar_grupo(
                    f"⚠️ TP POSPUESTO\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"{aviso_wdm}{aviso_lugar}"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "EN_GESTION":
                enviar_mensaje_telegram(chat_id,
                    f"TP requiere ser iniciado llamando al número de transporte: {ANEXO_TRANSPORTE}")
                notificar_grupo(
                    f"⚠️ TP EN GESTION\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"{aviso_wdm}{aviso_lugar}"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "EJECUTADO":
                enviar_mensaje_telegram(chat_id,
                    f"ℹ️ TP {datos['numero']} ya fue EJECUTADO y cerrado anteriormente.")
                notificar_grupo(
                    f"ℹ️ TP ya EJECUTADO\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"{aviso_wdm}{aviso_lugar}"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "EN_EJECUCION":
                enviar_mensaje_telegram(chat_id,
                    f"⚠️ Estimado {datos['nombre']}, el TP {datos['numero']} ya se encuentra iniciado (EN EJECUCIÓN).")
                notificar_grupo(
                    f"⚠️ TP ya EN EJECUCIÓN\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"{aviso_wdm}{aviso_lugar}"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "PLANIFICADO":
                fecha_ok, _, _ = validar_fecha_plan_hoy()
                if not fecha_ok:
                    mensaje_fecha = mensaje_fecha_plan_no_corresponde(datos["numero"])
                    enviar_mensaje_telegram(chat_id, mensaje_fecha)
                    notificar_admin(
                        f"❌ ERROR {datos.get('tarea_id')} TP {datos['numero']}\n"
                        "Fecha de planificación no corresponde al día actual."
                    )
                    finalizar_tarea(datos)
                    return

                if lugar_es_sitios():
                    enviar_mensaje_telegram(
                        chat_id,
                        MSG_SITIO_MOVIL
                    )
                    notificar_grupo(
                        f"⛔ TP NO INICIADO AUTOMÁTICAMENTE\n"
                        f"Motivo: Lugar Sitios detectado\n"
                        f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                        f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                        f"📄 Descripción: {datos_tp_actual.get('descripcion', 'N/A')}\n"
                        f"🔢 RPN: {datos_tp_actual.get('rpn', 'N/A')}\n"
                        f"📅 Fecha plan: {datos_tp_actual.get('fecha_plan', 'N/A')}\n"
                        f"{aviso_wdm}{aviso_lugar}{aviso_rpn}"
                        f"🕐 {hora} hrs"
                    )
                    finalizar_tarea(datos)
                    return

                if rpn_es_2500():
                    enviar_mensaje_telegram(
                        chat_id,
                        f"TP requiere ser iniciado llamando al número de transporte: {ANEXO_TRANSPORTE}"
                    )
                    notificar_grupo(
                        f"⛔ TP NO INICIADO AUTOMÁTICAMENTE\n"
                        f"Motivo: condición especial detectada\n"
                        f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                        f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                        f"📄 Descripción: {datos_tp_actual.get('descripcion', 'N/A')}\n"
                        f"🔢 RPN: {datos_tp_actual.get('rpn', 'N/A')}\n"
                        f"📅 Fecha plan: {datos_tp_actual.get('fecha_plan', 'N/A')}\n"
                        f"{aviso_wdm}{aviso_lugar}{aviso_rpn}"
                        f"🕐 {hora} hrs"
                    )
                    finalizar_tarea(datos)
                    return

                def run_inicio():
                    ok = iniciar_tp()
                    if ok:
                        exportar_txt()
                        hora_fin = datetime.now().strftime("%H:%M")
                        actualizar_estado_telegram(datos.get("estado_ref"), paso="menu")
                        enviar_mensaje_telegram(chat_id, "TP iniciado.")
                        notificar_admin(
                            f"✅ INICIO_EXITOSO {datos.get('tarea_id')} TP {datos['numero']}\n"
                            f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                            f"📥 Cola pendiente: {cola_tareas.qsize()}"
                        )
                        notificar_grupo(
                            f"✅ TP INICIADO a las {hora_fin} hrs."
                        )
                    else:
                        enviar_mensaje_telegram(chat_id, MSG_SISTEMA_NO_DISPONIBLE)
                        notificar_admin(
                            f"❌ ERROR {datos.get('tarea_id')} TP {datos['numero']}\n"
                            "No fue posible iniciar el TP."
                        )
                        notificar_grupo(
                            f"❌ Error al iniciar TP\n"
                            f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                            f"📋 TP: {datos['numero']}\n"
                            f"{aviso_wdm}{aviso_lugar}"
                            f"🕐 {hora} hrs"
                        )
                    finalizar_tarea(datos)
                ventana.after(1500, run_inicio)
                return

            elif estado_tp in ("ERROR", None):
                enviar_mensaje_telegram(chat_id, MSG_SISTEMA_NO_DISPONIBLE)
                notificar_grupo(
                    f"❌ Error de sistema\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"{aviso_wdm}{aviso_lugar}"
                    f"🕐 {hora} hrs"
                )

        # ── CERRAR ───────────────────────────────────────
        else:

            if estado_tp == "SIN_PDF":
                enviar_mensaje_telegram(chat_id, MSG_SISTEMA_NO_DISPONIBLE)
                notificar_grupo(
                    f"⚠️ Solicitud fallida — Sin PDF cargado\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "NO_PDF":
                enviar_mensaje_telegram(chat_id,
                    f"❌ TP {datos['numero']} no fue encontrado en los PDFs del día.")
                notificar_grupo(
                    f"❌ TP no encontrado en PDFs\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "EJECUTADO":
                enviar_mensaje_telegram(chat_id,
                    f"ℹ️ TP {datos['numero']} ya fue cerrado anteriormente.")
                notificar_grupo(
                    f"ℹ️ TP ya EJECUTADO\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"{aviso_wdm}{aviso_lugar}"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "PLANIFICADO":
                enviar_mensaje_telegram(chat_id,
                    f"⚠️ TP {datos['numero']} aún no ha sido iniciado. No es posible cerrarlo.")
                notificar_grupo(
                    f"⚠️ TP aún no iniciado\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"{aviso_wdm}{aviso_lugar}"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "POSPUESTO":
                enviar_mensaje_telegram(chat_id,
                    f"⚠️ TP {datos['numero']} se encuentra POSPUESTO.")
                notificar_grupo(
                    f"⚠️ TP POSPUESTO\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"{aviso_wdm}{aviso_lugar}"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "EN_GESTION":
                enviar_mensaje_telegram(chat_id,
                    f"TP requiere ser gestionado llamando al número de transporte: {ANEXO_TRANSPORTE}")
                notificar_grupo(
                    f"⚠️ TP EN GESTION\n"
                    f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                    f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                    f"{aviso_wdm}{aviso_lugar}"
                    f"🕐 {hora} hrs"
                )

            elif estado_tp == "EN_EJECUCION":
                if aviso_wdm or lugar_es_sitios() or rpn_es_2500():
                    enviar_mensaje_telegram(
                        chat_id,
                        f"TP requiere ser cerrado llamando al número de transporte: {ANEXO_TRANSPORTE}"
                    )
                    notificar_grupo(
                        f"⛔ TP NO CERRADO AUTOMÁTICAMENTE\n"
                        f"Motivo: condición especial detectada\n"
                        f"👤 {datos['nombre']} | 📱 {datos['telefono']}\n"
                        f"📋 TP: {datos['numero']} | ⚙️ {accion_texto}\n"
                        f"📄 Descripción: {datos_tp_actual.get('descripcion', 'N/A')}\n"
                        f"🔢 RPN: {datos_tp_actual.get('rpn', 'N/A')}\n"
                        f"📅 Fecha plan: {datos_tp_actual.get('fecha_plan', 'N/A')}\n"
                        f"{aviso_wdm}{aviso_lugar}{aviso_rpn}"
                        f"🕐 {hora} hrs"
                    )
                    finalizar_tarea(datos)
                    return

                nombre_cierre = datos["nombre"]
                telefono_cierre = datos["telefono"]

                def run_cierre():
                    enviar_mensaje_telegram(
                        chat_id,
                        f"🔒 Validación correcta. Cerrando TP {datos['numero']}...",
                        reply_markup={"remove_keyboard": True}
                    )

                    def responder_resultado_cierre(ok):
                        if ok:
                            hora_fin = datetime.now().strftime("%H:%M")
                            marcar_tp_finalizado_txt(datos["numero"])
                            actualizar_estado_telegram(datos.get("estado_ref"), paso="menu")
                            enviar_mensaje_telegram(chat_id,
                                f"✅ TP {datos['numero']} finalizado correctamente.\n"
                                f"Operador: {nombre_cierre} | Tel: {telefono_cierre}")
                            notificar_admin(
                                f"✅ CIERRE_EXITOSO {datos.get('tarea_id')}\n" 
                                f" TP {datos['numero']}\n"
                                f" Descripción: {datos_tp_actual.get('descripcion', 'N/A')}\n"
                                f"👤 {nombre_cierre} | 📱 {telefono_cierre}"
                            )
                            notificar_grupo(
                                f"🔒 TP CERRADO a las {hora_fin} hrs."
                            )
                        else:
                            enviar_mensaje_telegram(chat_id, MSG_SISTEMA_NO_DISPONIBLE)
                            notificar_admin(
                                f"❌ ERROR {datos.get('tarea_id')} TP {datos['numero']}\n"
                                "No fue posible cerrar el TP."
                            )
                            notificar_grupo(
                                f"❌ Error al cerrar TP\n"
                                f"👤 {nombre_cierre} | 📱 {telefono_cierre}\n"
                                f"📋 TP: {datos['numero']}\n"
                                f"{aviso_wdm}{aviso_lugar}"
                                f"🕐 {hora} hrs"
                            )
                        finalizar_tarea(datos)

                    mostrar_finalizar_tp(
                        nombre_inicial=nombre_cierre,
                        telefono_inicial=telefono_cierre,
                        auto_confirmar=True,
                        on_result=responder_resultado_cierre,
                        mostrar_error=False
                    )

                ventana.after(1500, run_cierre)
                return

            elif estado_tp in ("ERROR", None):
                enviar_mensaje_telegram(chat_id, MSG_SISTEMA_NO_DISPONIBLE)

    finalizar_tarea(datos)

# =====================
# MAIN
# =====================
def main():
    global ui_activa
    global ventana, entry_trabajo, entry_nombre, entry_telefono, entry_empresa
    global label_pdf_1, label_pdf_2, label_resultado, label_rpn
    global btn_iniciar, btn_finalizar

    ventana = tk.Tk()
    ui_activa = True
    ventana.title("Validador Trabajo Programado")
    ventana.protocol("WM_DELETE_WINDOW", cerrar_aplicacion)
    ventana.geometry("520x700")
    ventana.resizable(False, False)
    ventana.configure(bg="#f3f4f6")

    card = tk.Frame(ventana, bg="white", padx=24, pady=20, bd=1, relief="solid")
    card.place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(card, text="Validador TP", font=("Segoe UI", 14, "bold"), bg="white").pack(anchor="w")
    tk.Label(card, text="Control Trabajo Programado", font=("Segoe UI", 9), fg="#6b7280", bg="white").pack(anchor="w", pady=(0, 12))

    tk.Label(card, text="Número TP", bg="white").pack(anchor="w")
    entry_trabajo = tk.Entry(card, font=("Segoe UI", 10))
    entry_trabajo.pack(fill="x", ipady=3, pady=(2, 8))
    entry_trabajo.bind("<Return>", ejecutar_validacion)

    ttk.Button(card, text="📎 Cargar PDF 1", command=cargar_pdf_1).pack(fill="x")
    label_pdf_1 = tk.Label(card, text="❌ Sin PDF 1", fg="red", bg="white", font=("Segoe UI", 9))
    label_pdf_1.pack(anchor="w", pady=(4, 8))

    ttk.Button(card, text="📎 Cargar PDF 2", command=cargar_pdf_2).pack(fill="x")
    label_pdf_2 = tk.Label(card, text="❌ Sin PDF 2", fg="red", bg="white", font=("Segoe UI", 9))
    label_pdf_2.pack(anchor="w", pady=(4, 6))

    ttk.Button(card, text="✅ Validar TP", command=ejecutar_validacion).pack(fill="x", pady=(0, 10))

    label_resultado = tk.Label(
        card, text="", font=("Segoe UI", 10, "bold"),
        bg="#f9fafb", padx=10, pady=6,
        wraplength=460, justify="center", relief="solid", bd=1
    )
    label_resultado.pack(fill="x", pady=(0, 8))

    label_rpn = tk.Label(
        card, text="", bg="#eef2ff", fg="#1e3a8a",
        font=("Segoe UI", 9, "bold"), padx=10, pady=5, relief="solid", bd=1
    )
    label_rpn.pack(fill="x", pady=(0, 14))

    tk.Label(card, text="Nombre", bg="white").pack(anchor="w")
    entry_nombre = tk.Entry(card)
    entry_nombre.pack(fill="x", ipady=3, pady=(2, 6))

    tk.Label(card, text="Teléfono", bg="white").pack(anchor="w")
    entry_telefono = tk.Entry(card)
    entry_telefono.pack(fill="x", ipady=3, pady=(2, 6))

    tk.Label(card, text="Empresa (Opcional)", bg="white").pack(anchor="w")
    entry_empresa = tk.Entry(card)
    entry_empresa.pack(fill="x", ipady=3, pady=(2, 10))

    btn_iniciar = ttk.Button(card, text="🚀 Iniciar TP", command=iniciar_tp, state="disabled")
    btn_iniciar.pack(fill="x", pady=(0, 6))

    btn_finalizar = ttk.Button(card, text="🔒 Finalizar TP", command=mostrar_finalizar_tp, state="disabled")
    btn_finalizar.pack(fill="x", pady=(0, 6))

    ttk.Button(card, text="📄 Exportar TXT", command=exportar_txt).pack(fill="x", pady=(0, 6))

    footer = tk.Frame(card, bg="white")
    footer.pack(fill="x", pady=(6, 0))

    ttk.Button(footer, text="🔄 Restaurar sesión", command=restaurar_sesion).pack(side="left", expand=True, fill="x", padx=(0, 4))
    ttk.Button(footer, text="Cerrar", command=cerrar_aplicacion).pack(side="right", expand=True, fill="x", padx=(4, 0))

    ventana.after(200, mostrar_login)
    ventana.after(1000, procesar_cola_telegram)
    ventana.mainloop()

if __name__ == "__main__":
    main()
