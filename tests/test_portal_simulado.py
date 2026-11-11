"""Flujo completo en Edge con respuestas simuladas: ninguna petición llega a PSG."""

import html
import json
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from psg_core import HOST, ClientePSG, Configuracion, CredencialesRequeridas, ErrorAplicacion


class PortalSimuladoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cliente = ClientePSG(
            headless=True, pausa_paso_ms=0, pausa_guardado_ms=0, demora_tecla_ms=0
        )
        cls.cliente.abrir(Configuracion())
        cls.cliente.guardar_diagnostico_acceso = Mock(return_value=None)
        # Ninguna petición no simulada puede salir hacia la red.
        cls.cliente.context.route("**/*", lambda ruta: ruta.abort())

    @classmethod
    def tearDownClass(cls):
        cls.cliente.cerrar()

    def setUp(self):
        self.estado = "PLANIFICADO"
        self.notas = []
        self.envios = []
        self.auth = False
        self.cliente._credenciales = None
        self.panel_antiguo = False
        self.area_denegada = False
        self.enlace_externo = False
        self.consultas_listado = 0
        self.panel_marcos = False
        self.login_en_marco = False
        self.acciones_demoradas = False
        self.acciones_acentuadas = False
        self.duplicados_identicos = False
        self.duplicados_distintos = False
        self.sin_cierre = False
        self.tiempos = []
        self.ultima_tecla_ms = 0
        self.teclas_recibidas = 0
        self.cliente.pausa_paso_ms = self.cliente.pausa_guardado_ms = (
            self.cliente.demora_tecla_ms
        ) = 0
        self.cliente.context.route(f"https://{HOST}/**", self.responder)

    def tearDown(self):
        self.cliente.context.unroute(f"https://{HOST}/**", self.responder)

    def pagina_tp(self):
        notas = "".join(f"<p>{html.escape(nota)}</p>" for nota in self.notas)
        acciones = """<a href="/start.php">Iniciar Ejecucion</a>
        <a href="/note.php">Documentar desarrollo de trabajo</a>
        <a href="/finish.php">Finalizar Ejecucion</a>"""
        if self.acciones_acentuadas:
            acciones = acciones.replace("Finalizar Ejecucion", "🔒 Finalizar Ejecución")
        if self.duplicados_identicos:
            acciones += '<a href="/finish.php">Finalizar Ejecucion</a>'
        if self.duplicados_distintos:
            acciones += '<a href="/otro-cierre.php">Finalizar Ejecucion</a>'
        if self.sin_cierre:
            acciones = acciones.replace('<a href="/finish.php">Finalizar Ejecucion</a>', "")
        if self.acciones_demoradas:
            acciones = (
                '<div id="acciones"></div><script>setTimeout(() => {document.getElementById("acciones").innerHTML = '
                + json.dumps(acciones)
                + ";}, 250);</script>"
            )
        return f"""<html><body><a href="/logout.php">Salir</a><h1>TP 123456</h1>
        <table class="sample"><tr><th>Descripción</th><th>Otro</th><th>RPN</th><th>Estado</th><th>Fecha</th></tr>
        <tr><td>Trabajo de prueba</td><td>-</td><td>20</td><td>{self.estado}</td><td>2099-01-01 10:00:00</td></tr></table>
        {acciones}{notas}</body></html>"""

    def panel(self):
        href = "https://example.org/tp/index.php" if self.enlace_externo else "/tp/index.php"
        return f'''<h1>PSG Redes</h1><a href="{href}">Trabajos programados</a>
        <div role="dialog" style="position:fixed;inset:0;background:white;z-index:100">
        <h2>Atención!!!</h2><p>Se deberán cumplir las políticas de seguridad establecidas por ENTEL.</p>
        <button type="button">Cerrar</button></div>'''

    def responder(self, ruta):
        request = ruta.request
        path = urlsplit(request.url).path
        self.tiempos.append((path, time.monotonic(), time.time() * 1000))
        datos = parse_qs(request.post_data or "")
        if request.method == "POST":
            self.envios.append(path)
        login = """<form action="/auth.php" method="post"><input name="usuario">
                   <input name="password" type="password"><input type="submit" value="Ingresar"></form>"""
        if self.panel_antiguo:
            login = login.replace("/auth.php", "/login.php")
        if self.login_en_marco:
            login = login.replace("<form ", '<form target="_top" ')
        if path in ("/auth.php", "/login.php") and request.method == "POST":
            self.auth = datos.get("password") == ["clave-de-prueba"]
            if self.auth and self.panel_marcos:
                cuerpo = '<frameset cols="25%,75%"><frame src="/menu.php"><frame src="/home.php"></frameset>'
            elif self.auth and self.panel_antiguo:
                cuerpo = self.panel()
            else:
                cuerpo = '<a href="/logout.php">Salir</a>' if self.auth else login
        elif not self.auth:
            cuerpo = (
                '<iframe src="/login-frame.php"></iframe>'
                if self.login_en_marco and path == "/index.php"
                else login
            )
        elif path == "/menu.php":
            cuerpo = '<a href="/tp/index.php">Trabajos programados</a>'
        elif path == "/home.php":
            cuerpo = '<h1>PSG Redes</h1><div role="dialog">Atención: políticas de seguridad de ENTEL<button>Cerrar</button></div>'
        elif path == "/start.php":
            cuerpo = '<form action="/do-start.php" method="post"><input type="submit" value="Confirmar"></form>'
        elif path == "/do-start.php":
            self.estado = "EN EJECUCION"
            cuerpo = self.pagina_tp()
        elif path == "/note.php":
            cuerpo = """<form action="/save-note.php" method="post">
            <input type="hidden" name="teclas" value="0"><input type="hidden" name="ultima" value="0">
            <textarea name="texto" oninput="this.form.teclas.value = Number(this.form.teclas.value)+1;this.form.ultima.value=Date.now();"></textarea>
            <input type="submit" value="Guardar"></form>"""
        elif path == "/save-note.php":
            self.ultima_tecla_ms = float(datos["ultima"][0])
            self.teclas_recibidas = int(datos["teclas"][0])
            self.notas.append(datos["texto"][0])
            cuerpo = self.pagina_tp()
        elif path == "/finish.php":
            cuerpo = '<form action="/do-finish.php" method="post"><textarea name="texto"></textarea><input type="submit" name="accion" value="Confirmar"></form>'
        elif path == "/do-finish.php":
            self.estado = "EJECUTADO"
            cuerpo = self.pagina_tp()
        elif path == "/tp/index.php":
            self.consultas_listado += 1
            if self.area_denegada:
                ruta.fulfill(status=403, body="Sin permisos")
                return
            cuerpo = '<h1>Trabajos programados</h1><table class="sample"><tr><td>Listado de prueba</td></tr></table>'
        elif path in ("/index.php", "/login.php") and self.panel_antiguo:
            cuerpo = self.panel()
        elif path == "/index.php":
            cuerpo = '<a href="/logout.php">Salir</a>'
        else:
            if self.area_denegada:
                ruta.fulfill(status=403, body="Sin permisos")
                return
            cuerpo = self.pagina_tp()
        ruta.fulfill(status=200, content_type="text/html; charset=utf-8", body=cuerpo)

    def test_acceso_inicio_bitacora_y_cierre_reales_en_edge(self):
        cliente = self.cliente
        cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        datos = cliente.leer_tp("123456")
        self.assertEqual(datos["estado"], "PLANIFICADO")
        envios_antes = []
        datos = cliente.iniciar("123456", lambda: envios_antes.append("inicio"))
        self.assertEqual(datos["estado"], "EN EJECUCION")
        texto = "Operador de prueba [ValidadorTP:prueba-123]"
        cliente.documentar(
            "123456", texto, "[ValidadorTP:prueba-123]", lambda: envios_antes.append("bitacora")
        )
        cliente.documentar(
            "123456",
            texto,
            "[ValidadorTP:prueba-123]",
            lambda: self.fail("No debe reenviar una marca existente"),
        )
        self.assertEqual(len(self.notas), 1)
        datos = cliente.finalizar(
            "123456", "Cierre de prueba", lambda: envios_antes.append("cierre")
        )
        self.assertEqual(datos["estado"], "EJECUTADO")
        self.assertEqual(envios_antes, ["inicio", "bitacora", "cierre"])
        self.assertEqual(self.envios.count("/do-start.php"), 1)
        self.assertEqual(self.envios.count("/do-finish.php"), 1)

    def test_login_incorrecto_no_confirma_acceso(self):
        with self.assertRaises(ErrorAplicacion):
            # Se reduce solo la espera del control de login en este escenario.
            from unittest.mock import patch

            with patch("psg_core.TIMEOUT", 500):
                self.cliente.login("operador-prueba", "clave-incorrecta", Configuracion())
        self.assertFalse(self.auth)

    def test_restaurar_sesion_activa_no_reenvia_credenciales(self):
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        contexto, navegador = self.cliente.context, self.cliente.browser
        mensaje = self.cliente.restaurar_sesion(Configuracion())
        self.assertIn("reutilizada", mensaje)
        self.assertIs(self.cliente.context, contexto)
        self.assertIs(self.cliente.browser, navegador)
        self.assertEqual(self.envios, ["/auth.php"])

    def test_restaurar_sesion_expirada_reautentica_una_sola_vez(self):
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        self.auth = False
        mensaje = self.cliente.restaurar_sesion(Configuracion())
        self.assertIn("automáticamente", mensaje)
        self.assertTrue(self.auth)
        self.assertEqual(self.envios, ["/auth.php", "/auth.php"])

    def test_restaurar_pestana_cerrada_conserva_contexto(self):
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        contexto = self.cliente.context
        contexto.add_cookies(
            [{"name": "sesion_prueba", "value": "solo-prueba", "url": f"https://{HOST}/"}]
        )
        self.cliente.page.close()
        with patch("psg_core.sync_playwright", side_effect=AssertionError("No debe relanzar Edge")):
            self.cliente.restaurar_sesion(Configuracion())
        self.assertIs(self.cliente.context, contexto)
        self.assertFalse(self.cliente.page.is_closed())
        self.assertTrue(any(cookie["name"] == "sesion_prueba" for cookie in contexto.cookies()))
        self.assertEqual(self.envios, ["/auth.php"])

    def test_restaurar_sin_credenciales_solo_pide_formulario(self):
        with self.assertRaises(CredencialesRequeridas):
            self.cliente.restaurar_sesion(Configuracion())
        self.assertEqual(self.envios, [])

    def test_clave_antigua_no_se_reintenta_repetidamente(self):
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        self.auth = False
        self.cliente._credenciales = ("operador-prueba", "clave-antigua")
        with patch("psg_core.TIMEOUT", 500):
            with self.assertRaises(CredencialesRequeridas):
                self.cliente.restaurar_sesion(Configuracion())
        self.assertIsNone(self.cliente._credenciales)
        self.assertEqual(self.envios, ["/auth.php", "/auth.php"])
        with self.assertRaises(CredencialesRequeridas):
            self.cliente.restaurar_sesion(Configuracion())
        self.assertEqual(self.envios, ["/auth.php", "/auth.php"])

    def test_sesion_expirada_no_envia_inicio(self):
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        self.auth = False
        with self.assertRaises(ErrorAplicacion):
            self.cliente.leer_tp("123456")
        self.assertNotIn("/do-start.php", self.envios)

    def test_panel_antiguo_login_php_con_aviso_y_sin_salir(self):
        self.panel_antiguo = True
        mensaje = self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        self.assertIn("Conexión preparada", mensaje)
        self.assertEqual(urlsplit(self.cliente.page.url).path, "/login.php")
        self.assertEqual(self.consultas_listado, 0)
        # No cierra ni acepta el aviso de seguridad y no inicia trabajos.
        self.assertTrue(self.cliente.page.get_by_role("dialog").is_visible())
        self.assertEqual(self.envios, ["/login.php"])

    def test_menu_visible_no_basta_si_el_listado_denega_acceso(self):
        self.panel_antiguo = self.area_denegada = True
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        with self.assertRaisesRegex(ErrorAplicacion, "permisos"):
            self.cliente.leer_tp("123456")
        self.assertEqual(self.envios, ["/login.php"])

    def test_menu_con_destino_externo_no_se_abre(self):
        self.panel_antiguo = self.enlace_externo = True
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        self.assertEqual(self.consultas_listado, 0)

    def test_panel_en_frames_no_bloquea_acceso_ni_validacion(self):
        self.panel_marcos = True
        mensaje = self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        self.assertIn("Conexión preparada", mensaje)
        self.assertEqual(len(self.cliente.page.frames), 3)
        estructura = self.cliente.diagnostico_estructura()
        self.assertEqual(len(estructura["marcos"]), 3)
        self.assertNotIn("operador-prueba", json.dumps(estructura))
        self.assertNotIn("clave-de-prueba", json.dumps(estructura))
        datos = self.cliente.leer_tp("123456")
        self.assertEqual(datos["estado"], "PLANIFICADO")
        self.assertEqual(self.envios, ["/auth.php"])

    def test_formulario_acceso_dentro_de_frame(self):
        self.login_en_marco = self.panel_marcos = True
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        self.assertTrue(self.auth)
        self.assertEqual(self.cliente.leer_tp("123456")["numero"], "123456")

    def test_pagina_sin_marcadores_no_habilita_operaciones_sin_tp(self):
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        self.cliente.page.set_content("<h1>PSG Redes</h1><p>Panel sin enlaces conocidos</p>")
        self.assertEqual(self.cliente._campos_clave_visibles(), [])
        with self.assertRaises(ErrorAplicacion):
            self.cliente.leer_tp("999999")
        self.assertEqual(self.envios, ["/auth.php"])

    def preparar_cierre(self):
        self.cliente.login("operador-prueba", "clave-de-prueba", Configuracion())
        self.estado = "EN EJECUCION"
        self.cliente.leer_tp("123456")

    def test_cierre_espera_enlace_que_aparece_tarde(self):
        self.acciones_demoradas = True
        self.preparar_cierre()
        inicio = time.monotonic()
        datos = self.cliente.finalizar("123456", "Cierre", lambda: None)
        self.assertEqual(datos["estado"], "EJECUTADO")
        self.assertGreaterEqual(time.monotonic() - inicio, 0.15)
        self.assertEqual(self.envios.count("/do-finish.php"), 1)

    def test_cierre_reconoce_acento_e_icono(self):
        self.acciones_acentuadas = True
        self.preparar_cierre()
        self.assertEqual(
            self.cliente.finalizar("123456", "Cierre", lambda: None)["estado"], "EJECUTADO"
        )

    def test_enlaces_repetidos_al_mismo_destino_envian_una_sola_vez(self):
        self.duplicados_identicos = True
        self.preparar_cierre()
        self.cliente.finalizar("123456", "Cierre", lambda: None)
        self.assertEqual(self.envios.count("/do-finish.php"), 1)

    def test_enlaces_a_distintos_destinos_no_envian_cierre(self):
        self.duplicados_distintos = True
        self.preparar_cierre()
        antes = Mock()
        with self.assertRaisesRegex(ErrorAplicacion, "destinos distintos"):
            self.cliente.finalizar("123456", "Cierre", antes)
        antes.assert_not_called()
        self.assertEqual(self.envios, ["/auth.php"])

    def test_bitacora_y_cierre_respetan_pausas_y_escritura(self):
        self.cliente.pausa_paso_ms = 80
        self.cliente.pausa_guardado_ms = 120
        self.cliente.demora_tecla_ms = 2
        self.preparar_cierre()
        texto = "Registro [ValidadorTP:delay]"
        self.cliente.documentar("123456", texto, "[ValidadorTP:delay]")
        self.cliente.finalizar("123456", texto, lambda: None)
        self.assertEqual(self.notas, [texto])
        self.assertGreaterEqual(self.teclas_recibidas, len(texto))
        guardar = next(t for t in self.tiempos if t[0] == "/save-note.php")
        self.assertGreaterEqual(guardar[2] - self.ultima_tecla_ms, 60)
        siguiente = self.tiempos[self.tiempos.index(guardar) + 1]
        self.assertGreaterEqual(siguiente[1] - guardar[1], 0.09)
        cierre = next(t for t in self.tiempos if t[0] == "/finish.php")
        self.assertGreaterEqual(cierre[1] - guardar[1], 0.2)
        self.assertEqual(self.envios.count("/save-note.php"), 1)
        self.assertEqual(self.envios.count("/do-finish.php"), 1)


if __name__ == "__main__":
    unittest.main()
