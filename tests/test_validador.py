"""Pruebas sin acceso a PSG ni cambios en trabajos reales."""

import hashlib
import io
import multiprocessing
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from pdf_seguro import cargar_documento, comprobar_documentos, extraer_numeros, leer_archivo
from Prueba2PDF import Aplicacion
from psg_core import (
    HOST,
    ClientePSG,
    Configuracion,
    ErrorAplicacion,
    explicar_error,
    normalizar_estado,
    validar_numero,
    validar_operador,
)
from registro_local import InstanciaUnica, Registro, guardar_txt


def crear_pdf(texto="TP 123456 autorizado"):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 100 Td ({texto}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    salida = io.BytesIO()
    writer.write(salida)
    return salida.getvalue()


class SeguridadTests(unittest.TestCase):
    def test_destinos_no_autorizados(self):
        invalidos = [
            f"http://{HOST}/",
            f"https://{HOST}.example.org/",
            f"https://{HOST}@example.org/",
            f"https://{HOST}:444/",
            f"https://user@{HOST}/",
            "file:///C:/secret",
            "javascript:alert(1)",
        ]
        for url in invalidos:
            with self.subTest(url=url), self.assertRaises(ErrorAplicacion):
                Configuracion().validar_url(url)

    def test_https_permitido(self):
        url = f"https://{HOST}/tp/ver_planned.php?id=123"
        self.assertEqual(Configuracion().validar_url(url), url)

    def test_http_explicito_sigue_permitiendo_mejora_https(self):
        config = Configuracion(permitir_http=True)
        config.validar_url(f"http://{HOST}/")
        config.validar_url(f"https://{HOST}/")
        with self.assertRaises(ErrorAplicacion):
            config.validar_url("http://example.org/")

    def test_numero_no_admite_inyeccion_ni_unicode(self):
        for numero in ("", "123&otro=1", "１２３", "-12", "1" * 21):
            with self.subTest(numero=numero), self.assertRaises(ErrorAplicacion):
                validar_numero(numero)
        self.assertEqual(validar_numero("123456"), "123456")

    def test_operador_sin_controles_ni_telefonos_invalidos(self):
        for valores in (
            ("Ana\nRegistro falso", "987654321", ""),
            ("Ana", "abc", ""),
            ("", "987654321", ""),
        ):
            with self.subTest(valores=valores), self.assertRaises(ErrorAplicacion):
                validar_operador(*valores)
        self.assertEqual(
            validar_operador(" Ana ", "+56 9 1234-5678", " Entel "),
            ("Ana", "+56 9 1234-5678", "Entel"),
        )

    def test_estado_con_acentos_y_espacios(self):
        self.assertEqual(normalizar_estado("  En   ejecución "), "EN EJECUCION")

    def test_errores_no_filtran_password_ni_trazas(self):
        texto = explicar_error(RuntimeError("secreto=abc123 http://interno?token=123"))
        self.assertNotIn("abc123", texto)
        self.assertNotIn("token=", texto)

    def test_diagnostico_bloqueo_y_certificado(self):
        self.assertIn("política", explicar_error(RuntimeError("net::ERR_BLOCKED_BY_CLIENT")))
        self.assertIn(
            "certificado", explicar_error(RuntimeError("net::ERR_CERT_AUTHORITY_INVALID"))
        )
        self.assertIn("VPN", explicar_error(RuntimeError("net::ERR_NAME_NOT_RESOLVED")))


class PDFTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.ruta = Path(self.temp.name) / "documento.pdf"

    def test_numeros_completos_y_lectura_real(self):
        numeros = extraer_numeros(crear_pdf("TP 123456 y 91234567"))
        self.assertIn("123456", numeros)
        self.assertNotIn("123", numeros)

    def test_proceso_aislado_real(self):
        self.ruta.write_bytes(crear_pdf())
        documento = cargar_documento(str(self.ruta))
        self.assertIn("123456", documento["numeros"])
        comprobar_documentos((documento,), "123456")

    def test_pdf_modificado_invalida(self):
        datos = crear_pdf()
        self.ruta.write_bytes(datos)
        documento = {
            "ruta": str(self.ruta),
            "huella": hashlib.sha256(datos).hexdigest(),
            "numeros": {"123456"},
        }
        self.ruta.write_bytes(crear_pdf("Otro TP 999999"))
        with self.assertRaisesRegex(ErrorAplicacion, "cambió"):
            comprobar_documentos((documento,), "123456")

    def test_pdf_falso_y_extension(self):
        self.ruta.write_bytes(b"no es un PDF")
        with self.assertRaises(ErrorAplicacion):
            leer_archivo(self.ruta)
        with self.assertRaises(ErrorAplicacion):
            leer_archivo(self.ruta.with_suffix(".exe"))

    def test_limite_de_tamano(self):
        self.ruta.write_bytes(b"%PDF-123456789")
        with patch("pdf_seguro.MAX_BYTES", 5), self.assertRaisesRegex(ErrorAplicacion, "20 MB"):
            leer_archivo(self.ruta)

    def test_pdf_cifrado(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secreto")
        salida = io.BytesIO()
        writer.write(salida)
        with self.assertRaisesRegex(ErrorAplicacion, "cifrado"):
            extraer_numeros(salida.getvalue())

    def test_sin_pdf_no_habilita(self):
        with self.assertRaises(ErrorAplicacion):
            comprobar_documentos((), "123456")


class NavegadorTests(unittest.TestCase):
    def setUp(self):
        self.cliente = ClientePSG()
        self.cliente.page = Mock()
        self.cliente.page.url = f"https://{HOST}/index.php"
        self.cliente.page.is_closed.return_value = False
        self.cliente.page.frames = [self.cliente.page]
        self.cliente.page.main_frame = self.cliente.page
        self.cliente.page.locator.return_value.all.return_value = [
            self.cliente.page.locator.return_value.first
        ]
        self.cliente.page.locator.return_value.first.is_visible.return_value = False

    def test_sesion_vencida(self):
        self.cliente.page.locator.return_value.first.is_visible.return_value = True
        with self.assertRaisesRegex(ErrorAplicacion, "expiró"):
            self.cliente.comprobar_pagina()

    def test_cierre_descarta_clave_aunque_falle_el_navegador(self):
        self.cliente._credenciales = ("usuario-prueba", "clave-prueba")
        self.cliente.browser = Mock()
        self.cliente.browser.close.side_effect = RuntimeError("Ya cerrado")
        self.cliente.playwright = Mock()
        with self.assertRaises(RuntimeError):
            self.cliente.cerrar()
        self.assertIsNone(self.cliente._credenciales)
        self.assertIsNone(self.cliente.browser)

    def test_recrear_navegador_conserva_clave_solo_si_se_solicita(self):
        self.cliente._credenciales = ("usuario-prueba", "clave-prueba")
        self.cliente.cerrar(olvidar_credenciales=False)
        self.assertEqual(self.cliente._credenciales, ("usuario-prueba", "clave-prueba"))
        self.cliente.cerrar()
        self.assertIsNone(self.cliente._credenciales)

    def test_403_no_se_reintenta(self):
        self.cliente.page.goto.return_value.status = 403
        with self.assertRaisesRegex(ErrorAplicacion, "401/403"):
            self.cliente.navegar(f"https://{HOST}/")
        self.assertEqual(self.cliente.page.goto.call_count, 1)

    def test_lectura_503_se_reintenta_una_vez(self):
        self.cliente.page.goto.side_effect = [Mock(status=503), Mock(status=200)]
        self.cliente.navegar(f"https://{HOST}/")
        self.assertEqual(self.cliente.page.goto.call_count, 2)

    def test_redireccion_externa_no_se_acepta(self):
        self.cliente.page.url = "https://example.org/login"
        self.cliente.page.goto.return_value.status = 200
        with self.assertRaises(ErrorAplicacion):
            self.cliente.navegar(f"https://{HOST}/")

    def test_post_externo_se_bloquea(self):
        ruta = Mock()
        ruta.request.url = "https://example.org/login"
        ruta.request.method = "POST"
        ruta.request.is_navigation_request.return_value = False
        self.cliente._ruta(ruta)
        ruta.abort.assert_called_once()
        ruta.continue_.assert_not_called()

    def test_formulario_externo_no_recibe_datos(self):
        campo = Mock()
        campo.evaluate.return_value = f"https://{HOST}/login.php"
        form = campo.locator.return_value
        form.count.return_value = 1
        form.get_attribute.return_value = "https://example.org/robar"
        with self.assertRaises(ErrorAplicacion):
            self.cliente._formulario(campo)
        campo.fill.assert_not_called()

    def test_inicio_vencido_no_envia(self):
        fecha = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        self.cliente.comprobar_tp = Mock(return_value={"fecha_plan": fecha})
        self.cliente._abrir_accion = Mock()
        callback = Mock()
        with self.assertRaises(ErrorAplicacion):
            self.cliente.iniciar("123456", callback)
        callback.assert_not_called()
        self.cliente._abrir_accion.assert_not_called()

    def test_bitacora_con_marca_no_se_duplica(self):
        self.cliente.leer_tp = Mock()
        self.cliente.page.locator.return_value.inner_text.return_value = (
            "Registro [ValidadorTP:123]"
        )
        self.cliente._abrir_accion = Mock()
        callback = Mock()
        self.cliente.documentar(
            "123456", "Registro [ValidadorTP:123]", "[ValidadorTP:123]", callback
        )
        self.cliente._abrir_accion.assert_not_called()
        callback.assert_not_called()

    def test_submit_ambiguo_no_se_envia_ni_se_registra_envio(self):
        form = Mock()
        form.locator.return_value.count.return_value = 2
        self.cliente._formulario = Mock(return_value=form)
        callback = Mock()
        with self.assertRaises(ErrorAplicacion):
            self.cliente.enviar_formulario("texto", antes_de_enviar=callback)
        callback.assert_not_called()
        form.locator.return_value.click.assert_not_called()


class RegistroTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.registro = Registro(self.temp.name)
        self.app = Aplicacion.__new__(Aplicacion)
        self.app.registro = self.registro

    def test_envio_confirmado(self):
        def operacion(antes, _):
            antes()
            return "ok"

        self.assertEqual(self.app.operar("123456", "inicio", operacion), "ok")
        self.assertEqual(self.registro.pendientes(), [])

    def test_fallo_antes_de_enviar_no_es_incierto(self):
        def fallo(antes, _):
            raise ErrorAplicacion("Formulario inesperado")

        with self.assertRaises(ErrorAplicacion):
            self.app.operar("123456", "inicio", fallo)
        self.assertEqual(self.registro.pendientes(), [])

    def test_fallo_tras_envio_queda_incierto_y_no_se_repite(self):
        contador = []

        def fallo(antes, _):
            antes()
            contador.append("enviado")
            raise ErrorAplicacion("Se perdió la respuesta")

        with self.assertRaises(ErrorAplicacion):
            self.app.operar("123456", "cierre", fallo)
        self.assertEqual(contador, ["enviado"])
        pendientes = Registro(self.temp.name).pendientes("123456")
        self.assertEqual(pendientes[0][3], "incierta")
        self.registro.estado(pendientes[0][0], "revisada")
        self.assertEqual(self.registro.pendientes(), [])

    def test_journal_no_guarda_telefonos_ni_texto(self):
        self.registro.crear("123456", "inicio")
        with self.registro._conexion() as conexion:
            columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(operaciones)")]
        self.assertEqual(columnas, ["id", "tp", "accion", "estado", "actualizado"])

    def test_no_se_permiten_dos_instancias(self):
        primera, segunda = InstanciaUnica(self.temp.name), InstanciaUnica(self.temp.name)
        try:
            self.assertTrue(primera.adquirir())
            self.assertFalse(segunda.adquirir())
            primera.liberar()
            self.assertTrue(segunda.adquirir())
        finally:
            primera.liberar()
            segunda.liberar()

    def test_exportacion_atomica_conserva_original_si_falla_reemplazo(self):
        ruta = Path(self.temp.name) / "bitacora.txt"
        ruta.write_text("Anterior", encoding="utf-8")
        with patch("registro_local.os.replace", side_effect=PermissionError("Sin acceso")):
            with self.assertRaises(PermissionError):
                guardar_txt(ruta, "Nuevo")
        self.assertEqual(ruta.read_text(encoding="utf-8"), "Anterior")
        self.assertEqual(list(Path(self.temp.name).glob("*.tmp")), [])

    def test_exportacion_txt_valida(self):
        ruta = Path(self.temp.name) / "bitacora.txt"
        guardar_txt(ruta, "Registro de prueba")
        self.assertEqual(ruta.read_text(encoding="utf-8"), "Registro de prueba")
        with self.assertRaises(ErrorAplicacion):
            guardar_txt(ruta.with_suffix(".exe"), "No permitido")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
