"""Cliente PSG. Se utiliza únicamente desde el hilo de trabajo del navegador."""

import json
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import TimeoutError as BrowserTimeout
from playwright.sync_api import sync_playwright

HOST = "portalpsg.gred.entelpcs.cl"
TIMEOUT = 20000


class ErrorAplicacion(Exception):
    """Error con una explicación apta para mostrar al operador."""


class CredencialesRequeridas(ErrorAplicacion):
    """PSG necesita acceso y no quedan credenciales reutilizables en memoria."""


def explicar_error(error):
    if isinstance(error, ErrorAplicacion):
        return str(error)
    if isinstance(error, PermissionError):
        return "No se pudo acceder al archivo. Revise sus permisos o elija otra carpeta; no necesita ejecutar como administrador."
    if isinstance(error, sqlite3.Error):
        return "No se pudo acceder al registro local de operaciones en la carpeta del usuario. Revise permisos, espacio y estado del disco. No se enviarán nuevas acciones sin ese registro."
    texto = str(error).upper()
    casos = {
        "ERR_BLOCKED_BY_CLIENT": "Edge o una política de seguridad bloqueó el acceso. Compruebe el portal en Edge y consulte a TI si persiste. La app no desactiva esa protección.",
        "ERR_BLOCKED_BY_ADMINISTRATOR": "La política corporativa de Edge bloqueó el portal. El acceso debe revisarlo TI.",
        "ERR_NAME_NOT_RESOLVED": "No se puede resolver el nombre de PSG. Compruebe la red corporativa, la VPN y el DNS.",
        "ERR_PROXY": "Falló la conexión mediante el proxy corporativo. Revise su configuración con TI.",
        "ERR_TUNNEL": "El proxy no permite establecer la conexión. Revise el acceso corporativo con TI.",
        "ERR_CERT": "El certificado HTTPS no es válido o no es de confianza. TI debe revisar el certificado; la app no lo ignora.",
        "ERR_CONNECTION_REFUSED": "PSG rechazó la conexión. Compruebe si el portal admite el protocolo seleccionado y si está disponible.",
        "ERR_CONNECTION": "Se interrumpió la conexión con PSG. Compruebe la VPN y el estado del portal.",
        "TARGET PAGE": "La ventana de Edge se cerró. Use Restaurar sesión para abrirla de nuevo.",
        "EXECUTABLE DOESN": "No se encontró Microsoft Edge. Instálelo o repárelo mediante TI.",
    }
    for clave, mensaje in casos.items():
        if clave in texto:
            return mensaje
    if isinstance(error, BrowserTimeout) or "TIMEOUT" in texto:
        return "PSG no respondió a tiempo o su pantalla cambió. Revise el portal. Si había enviado una acción, confirme su estado antes de repetirla."
    if isinstance(error, OSError):
        return "No se pudo leer o guardar un archivo. Revise disponibilidad, espacio, permisos y sincronización de OneDrive."
    return "No se pudo completar la operación. Revise PSG y use Diagnóstico. No repita una acción sin comprobar antes su resultado."


@dataclass(frozen=True)
class Configuracion:
    permitir_http: bool = False

    @property
    def base(self):
        return f"{'http' if self.permitir_http else 'https'}://{HOST}/"

    def validar_url(self, url):
        try:
            partes = urlsplit(url)
            puerto = partes.port
        except ValueError as error:
            raise ErrorAplicacion("PSG devolvió una dirección inválida.") from error
        esquemas = ("https", "http") if self.permitir_http else ("https",)
        if (
            partes.scheme not in esquemas
            or partes.hostname != HOST
            or partes.username is not None
            or partes.password is not None
            or puerto not in (None, 80 if partes.scheme == "http" else 443)
        ):
            raise ErrorAplicacion(
                "Se bloqueó una dirección distinta del portal y protocolo autorizados. No se enviaron credenciales a ese destino."
            )
        return url


def normalizar_estado(texto):
    return " ".join(
        "".join(
            c for c in unicodedata.normalize("NFD", texto.upper()) if not unicodedata.combining(c)
        ).split()
    )


def validar_numero(numero):
    if not re.fullmatch(r"[0-9]{1,20}", numero):
        raise ErrorAplicacion("Ingrese un TP de 1 a 20 dígitos.")
    return numero


def validar_operador(nombre, telefono, empresa=""):
    valores = [nombre.strip(), telefono.strip(), empresa.strip()]
    if not valores[0] or not valores[1]:
        raise ErrorAplicacion("Nombre y teléfono son obligatorios.")
    if any(len(v) > limite for v, limite in zip(valores, (120, 30, 120))):
        raise ErrorAplicacion(
            "Nombre o empresa demasiado largos, o teléfono de más de 30 caracteres."
        )
    if any(any(ord(c) < 32 or ord(c) == 127 for c in v) for v in valores):
        raise ErrorAplicacion(
            "Los datos del operador no pueden contener saltos de línea ni caracteres de control."
        )
    if not re.fullmatch(r"\+?[0-9 ()-]{5,30}", valores[1]):
        raise ErrorAplicacion(
            "Ingrese un teléfono válido, con dígitos y, si corresponde, prefijo +."
        )
    return tuple(valores)


class ClientePSG:
    def __init__(
        self, headless=False, pausa_paso_ms=1500, pausa_guardado_ms=2500, demora_tecla_ms=25
    ):
        self.headless = headless
        self.pausa_paso_ms = pausa_paso_ms
        self.pausa_guardado_ms = pausa_guardado_ms
        self.demora_tecla_ms = demora_tecla_ms
        self.marco_formulario = None
        self.playwright = self.browser = self.context = self.page = None
        self.config = Configuracion()
        self.ultimo_estado_http = None
        self.destino_bloqueado = False
        self._credenciales = None

    def cerrar(self, olvidar_credenciales=True):
        try:
            if self.browser:
                self.browser.close()
        finally:
            try:
                if self.playwright:
                    self.playwright.stop()
            finally:
                self.playwright = self.browser = self.context = self.page = None
                self.marco_formulario = None
                if olvidar_credenciales:
                    self._credenciales = None

    def _ruta(self, ruta):
        peticion = ruta.request
        if peticion.is_navigation_request() or peticion.method not in ("GET", "HEAD"):
            try:
                self.config.validar_url(peticion.url)
            except ErrorAplicacion:
                self.destino_bloqueado = True
                ruta.abort("blockedbyclient")
                return
        ruta.continue_()

    def _respuesta(self, respuesta):
        if respuesta.request.is_navigation_request() and respuesta.frame == self.page.main_frame:
            self.ultimo_estado_http = respuesta.status

    def abrir(self, config):
        if self.browser and self.browser.is_connected() and self.context and self.config == config:
            if self.page and not self.page.is_closed():
                return
            try:
                # Una pestaña cerrada no obliga a perder las cookies del contexto.
                self._preparar_pagina(self.context.new_page())
                return
            except BrowserError:
                # El contexto pudo cerrarse aunque Edge continúe conectado.
                pass
        self.cerrar(olvidar_credenciales=False)
        self.config = config
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                channel="msedge", headless=self.headless, args=["--start-maximized"]
            )
            self.context = self.browser.new_context(
                no_viewport=True, accept_downloads=False, service_workers="block"
            )
            self.context.route("**/*", self._ruta)
            self._preparar_pagina(self.context.new_page())
        except Exception:
            self.cerrar()
            raise

    def _preparar_pagina(self, pagina):
        self.page = pagina
        self.marco_formulario = None
        self.ultimo_estado_http = None
        self.destino_bloqueado = False
        self.page.set_default_timeout(TIMEOUT)
        self.page.set_default_navigation_timeout(TIMEOUT)
        self.page.on("response", self._respuesta)

    def comprobar_pagina(self, autenticada=True):
        if not self.page or self.page.is_closed():
            raise ErrorAplicacion("Edge no está conectado. Use Restaurar sesión.")
        self.config.validar_url(self.page.url)
        if self.destino_bloqueado:
            raise ErrorAplicacion(
                "PSG intentó abrir un destino no autorizado. Revise el acceso con TI."
            )
        if self.ultimo_estado_http in (401, 403):
            raise ErrorAplicacion(
                "PSG denegó el acceso (401/403). Revise su sesión y permisos con el administrador del portal."
            )
        if self.ultimo_estado_http and self.ultimo_estado_http >= 400:
            raise ErrorAplicacion(
                f"PSG respondió con error HTTP {self.ultimo_estado_http}. No se confirmó la operación."
            )
        if autenticada and self._campos_clave_visibles():
            raise ErrorAplicacion(
                "La sesión expiró o PSG solicita acceso. Use Restaurar sesión y valide nuevamente el TP."
            )

    def navegar(self, url, reintentar=True):
        self.config.validar_url(url)
        if not self.page or self.page.is_closed():
            raise ErrorAplicacion("Edge no está conectado. Use Restaurar sesión.")
        intentos = 2 if reintentar else 1
        for intento in range(intentos):
            self.destino_bloqueado = False
            try:
                respuesta = self.page.goto(url, wait_until="domcontentloaded")
                self.ultimo_estado_http = respuesta.status if respuesta else None
                if self.ultimo_estado_http in (502, 503, 504) and intento + 1 < intentos:
                    continue
                self.comprobar_pagina(autenticada=False)
                return
            except BrowserError as error:
                transitorio = isinstance(error, BrowserTimeout) or any(
                    c in str(error)
                    for c in ("ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED", "ERR_TIMED_OUT")
                )
                if not transitorio or intento + 1 == intentos or self.destino_bloqueado:
                    raise

    def _formulario(self, campo):
        self.comprobar_pagina(autenticada=False)
        formulario = campo.locator("xpath=ancestor::form[1]")
        if formulario.count() != 1:
            raise ErrorAplicacion("Cambió el formulario del portal. No se envió información.")
        base = campo.evaluate("(elemento) => elemento.ownerDocument.baseURI")
        self.config.validar_url(base)
        destino = urljoin(base, formulario.get_attribute("action") or base)
        self.config.validar_url(destino)
        if (formulario.get_attribute("method") or "get").lower() != "post":
            raise ErrorAplicacion(
                "El formulario no usa POST. No se enviaron credenciales ni cambios mediante la URL."
            )
        return formulario

    def _marcos_portal(self):
        for marco in self.page.frames:
            try:
                self.config.validar_url(marco.url)
            except ErrorAplicacion:
                continue
            yield marco

    def _campos_clave_visibles(self):
        return [
            campo
            for marco in self._marcos_portal()
            for campo in marco.locator('input[type="password"], input[name="password"]').all()
            if campo.is_visible()
        ]

    def diagnostico_estructura(self):
        """Solo conteos: no captura HTML, textos, URLs, cookies ni valores."""
        marcos = []
        if self.page and not self.page.is_closed():
            for marco in self._marcos_portal():
                marcos.append(
                    {
                        "principal": marco == self.page.main_frame,
                        "campos_clave_visibles": marco.locator(
                            'input[type="password"], input[name="password"]'
                        )
                        .filter(visible=True)
                        .count(),
                        "enlaces": marco.locator("a").count(),
                        "tablas_trabajo": marco.locator("table.sample").count(),
                    }
                )
        return {"version": 1, "estado_http": self.ultimo_estado_http, "marcos": marcos}

    def guardar_diagnostico_acceso(self):
        try:
            from registro_local import carpeta_datos

            carpeta = carpeta_datos()
            carpeta.mkdir(parents=True, exist_ok=True)
            ruta = carpeta / "diagnostico_acceso.json"
            ruta.write_text(
                json.dumps(self.diagnostico_estructura(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return ruta
        except Exception:
            # El diagnóstico nunca debe sustituir el error original del acceso.
            return None

    def login(self, usuario, password, config):
        # Un acceso fallido no debe dejar una clave anterior para futuros intentos.
        self._credenciales = None
        try:
            return self._login(usuario, password, config)
        except (ErrorAplicacion, BrowserError) as error:
            ruta = self.guardar_diagnostico_acceso()
            if ruta:
                tipo_error = (
                    CredencialesRequeridas
                    if isinstance(error, CredencialesRequeridas)
                    else ErrorAplicacion
                )
                raise tipo_error(
                    f"{explicar_error(error)}\n\nDiagnóstico sin credenciales: {ruta}"
                ) from error
            raise

    def _login(self, usuario, password, config):
        if not usuario.strip() or not password:
            raise ErrorAplicacion("Ingrese usuario y contraseña.")
        self.abrir(config)
        self.navegar(urljoin(config.base, "index.php"))
        self.page.wait_for_load_state("load")
        campos = self._campos_clave_visibles()
        enviadas = False
        if campos:
            if len(campos) != 1:
                raise CredencialesRequeridas(
                    "PSG solicita un cambio de clave o muestra varios formularios. Complete ese paso en Edge."
                )
            clave = campos[0]
            formulario = self._formulario(clave)
            if formulario.locator('input[name="usuario"]').count() != 1:
                raise CredencialesRequeridas(
                    "PSG solicita una verificación o cambio de clave. Complete ese paso en Edge."
                )
            formulario.locator('input[name="usuario"]').fill(usuario.strip())
            clave.fill(password)
            formulario.locator('input[type="submit"], button[type="submit"]').first.click()
            try:
                clave.wait_for(state="hidden", timeout=TIMEOUT)
            except BrowserTimeout as error:
                self.comprobar_pagina(autenticada=False)
                raise CredencialesRequeridas(
                    "PSG no confirmó el acceso. Revise en Edge las credenciales, el bloqueo de cuenta o una verificación adicional. No se reintentó el acceso automáticamente."
                ) from error
            except BrowserError as error:
                if "frame was detached" not in str(error).lower():
                    raise
            enviadas = True
        self.page.wait_for_load_state("load")
        self.comprobar_pagina()
        if enviadas:
            self._credenciales = (usuario.strip(), password)
        return "Conexión preparada. Cargue un PDF y valide el TP para comprobar el acceso."

    def restaurar_sesion(self, config):
        """Reutiliza cookies; reautentica una vez solo si PSG vuelve a pedir clave."""
        credenciales = self._credenciales
        self.abrir(config)
        self.navegar(urljoin(config.base, "index.php"))
        self.page.wait_for_load_state("load")
        if self._campos_clave_visibles():
            if not credenciales:
                raise CredencialesRequeridas(
                    "PSG solicita acceso nuevamente. Ingrese sus credenciales para continuar."
                )
            try:
                self.login(*credenciales, config)
            except CredencialesRequeridas as error:
                raise CredencialesRequeridas(
                    "PSG no aceptó la reconexión automática o solicita cambiar la clave. Revise Edge e ingrese nuevamente si corresponde."
                ) from error
            return "Sesión reconectada automáticamente. Valide nuevamente el TP."
        self.comprobar_pagina()
        return "Sesión reutilizada sin pedir credenciales. Valide nuevamente el TP."

    def diagnosticar(self, config):
        self.abrir(config)
        self.destino_bloqueado = False
        prueba = self.context.new_page()
        try:
            respuesta = prueba.goto(
                urljoin(config.base, "index.php"), wait_until="domcontentloaded", timeout=TIMEOUT
            )
            config.validar_url(prueba.url)
            estado = respuesta.status if respuesta else None
            if estado is None or estado >= 400:
                raise ErrorAplicacion(
                    f"PSG no está disponible o denegó el acceso. Estado HTTP: {estado}."
                )
            return (
                f"PSG responde por {urlsplit(config.base).scheme.upper()} (HTTP {estado}).\n"
                "Esta prueba no acredita permisos para iniciar o finalizar trabajos.\n"
                "El navegador usa la configuración de red de Windows, sin desactivar sus controles."
            )
        finally:
            prueba.close()

    def leer_tp(self, numero, navegar=True):
        validar_numero(numero)
        if navegar:
            self.navegar(urljoin(self.config.base, f"tp/ver_planned.php?id={numero}"))
        self.comprobar_pagina()
        titulo = self.page.locator("h1").inner_text()
        match = re.search(r"(?<!\d)\d+(?!\d)", titulo)
        if not match or match.group() != numero:
            raise ErrorAplicacion("El portal no muestra el TP solicitado. Vuelva a validar.")
        fila = self.page.locator("table.sample").first.locator("tr").nth(1)
        celdas = fila.locator("td")
        if celdas.count() < 5:
            raise ErrorAplicacion("Cambió la tabla de PSG. No se puede validar el trabajo.")
        descripcion = celdas.nth(0).inner_text().strip()
        try:
            rpn = int(celdas.nth(2).inner_text().strip())
            fecha = datetime.strptime(celdas.nth(4).inner_text().strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError as error:
            raise ErrorAplicacion(
                "PSG devolvió un RPN o una fecha inválidos. No se habilitaron acciones."
            ) from error
        return {
            "numero": numero,
            "descripcion": descripcion,
            "rpn": rpn,
            "fecha_plan": fecha.strftime("%Y-%m-%d"),
            "estado": normalizar_estado(celdas.nth(3).inner_text()),
        }

    def comprobar_tp(self, numero, estados):
        datos = self.leer_tp(numero, navegar=False)
        if datos["estado"] not in estados:
            raise ErrorAplicacion(
                f"El estado actual es {datos['estado']}. Vuelva a validar antes de actuar."
            )
        return datos

    def _pausar(self, guardado=False):
        demora = self.pausa_guardado_ms if guardado else self.pausa_paso_ms
        if demora:
            # En el hilo del navegador: Tk permanece disponible.
            self.page.wait_for_timeout(demora)

    def _enlaces_accion(self, texto):
        variantes = {"a": "[aá]", "e": "[eé]", "i": "[ií]", "o": "[oó]", "u": "[uú]"}
        palabras = [
            "".join(variantes.get(c.lower(), re.escape(c)) for c in palabra)
            for palabra in texto.split()
        ]
        patron = re.compile(r"^[\W_]*" + r"\s+".join(palabras) + r"[\W_]*$", re.I)
        encontrados = []
        for marco in self._marcos_portal():
            candidatos = (
                marco.get_by_role("link", name=patron)
                .or_(marco.locator("a").filter(has_text=patron))
                .filter(visible=True)
            )
            for enlace in candidatos.all():
                href = enlace.get_attribute("href")
                if not href or href.lower().startswith("javascript:"):
                    raise ErrorAplicacion(
                        f"El enlace «{texto}» cambió de formato. No se ejecutó la acción."
                    )
                destino = urljoin(marco.url, href)
                self.config.validar_url(destino)
                encontrados.append((destino, enlace, marco))
        return encontrados

    def _abrir_accion(self, texto):
        self._pausar()
        limite = time.monotonic() + TIMEOUT / 1000
        while True:
            self.comprobar_pagina()
            encontrados = self._enlaces_accion(texto)
            destinos = {destino for destino, _, _ in encontrados}
            if len(destinos) > 1:
                raise ErrorAplicacion(
                    f"PSG muestra varios destinos distintos para «{texto}». No se hizo clic; revise el TP abierto."
                )
            if encontrados:
                _, enlace, marco = encontrados[0]
                break
            if time.monotonic() >= limite:
                raise ErrorAplicacion(
                    f"No apareció la acción «{texto}» después de esperar a PSG. Vuelva a validar el TP y compruebe su estado y permisos."
                )
            self.page.wait_for_timeout(100)
        enlace.click()
        self.page.wait_for_load_state("domcontentloaded")
        self.marco_formulario = self.page.main_frame if marco.is_detached() else marco
        self.marco_formulario.wait_for_load_state("domcontentloaded")
        self._pausar()
        self.comprobar_pagina()

    def enviar_formulario(self, texto=None, confirmar=False, antes_de_enviar=None):
        self.comprobar_pagina()
        marco = self.marco_formulario
        if marco is None or marco.is_detached():
            marco = self.page.main_frame
        campo = (
            marco.locator("textarea").filter(visible=True).first
            if texto is not None
            else marco.locator('form input[type="submit"], form button[type="submit"]')
            .filter(visible=True)
            .first
        )
        campo.wait_for(state="visible", timeout=TIMEOUT)
        formulario = self._formulario(campo)
        if texto is not None:
            campo.fill("")
            campo.press_sequentially(texto, delay=self.demora_tecla_ms)
        self._pausar()
        selector = (
            'input[name="accion"][value="Confirmar"]'
            if confirmar
            else 'input[type="submit"], button[type="submit"]'
        )
        boton = formulario.locator(selector).filter(visible=True)
        boton.first.wait_for(state="visible", timeout=TIMEOUT)
        if boton.count() != 1:
            raise ErrorAplicacion(
                "El formulario tiene más de una confirmación o cambió. Revise PSG."
            )
        self._formulario(campo)
        if antes_de_enviar:
            antes_de_enviar()
        boton.click()
        self.page.wait_for_load_state("domcontentloaded")
        self._pausar(guardado=True)
        self.comprobar_pagina()

    def documentar(self, numero, texto, marca, antes_de_enviar=None):
        self.leer_tp(numero)
        if marca in self.page.locator("body").inner_text():
            return
        self._abrir_accion("Documentar desarrollo de trabajo")
        self.enviar_formulario(texto, antes_de_enviar=antes_de_enviar)
        self.leer_tp(numero)
        try:
            self.page.get_by_text(marca, exact=False).first.wait_for(
                state="visible", timeout=TIMEOUT
            )
        except BrowserTimeout as error:
            raise ErrorAplicacion(
                "PSG no confirmó la bitácora. Verifique el portal antes de repetirla."
            ) from error
        self._pausar()

    def iniciar(self, numero, antes_de_enviar):
        datos = self.comprobar_tp(numero, ("PLANIFICADO",))
        if datetime.strptime(datos["fecha_plan"], "%Y-%m-%d").date() < datetime.now().date():
            raise ErrorAplicacion("No se puede iniciar un TP vencido.")
        self._abrir_accion("Iniciar Ejecucion")
        self.enviar_formulario(antes_de_enviar=antes_de_enviar)
        datos = self.leer_tp(numero)
        if datos["estado"] not in ("EJECUCION", "EN EJECUCION"):
            raise ErrorAplicacion(
                "PSG no confirmó el inicio. Verifique el estado antes de repetirlo."
            )
        return datos

    def finalizar(self, numero, texto, antes_de_enviar):
        self.comprobar_tp(numero, ("EJECUCION", "EN EJECUCION"))
        self._abrir_accion("Finalizar Ejecucion")
        self.enviar_formulario(texto, confirmar=True, antes_de_enviar=antes_de_enviar)
        datos = self.leer_tp(numero)
        if datos["estado"] != "EJECUTADO":
            raise ErrorAplicacion(
                "PSG no confirmó el cierre. Verifique su estado antes de repetirlo."
            )
        return datos
