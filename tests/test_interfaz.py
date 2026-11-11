"""Regresiones de Tk y del hilo de trabajo; no se conecta a la red."""

import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from Prueba2PDF import Aplicacion
from psg_core import CredencialesRequeridas, ErrorAplicacion


class InterfazTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.app = Aplicacion(self.root, cliente=Mock(), registro=Mock())
        self.root.update()

    def tearDown(self):
        self.app.executor.shutdown(wait=True)
        for identificador in self.root.tk.call("after", "info"):
            self.root.after_cancel(identificador)
        self.root.destroy()

    def esperar(self):
        limite = time.monotonic() + 4
        while self.app.ocupada and time.monotonic() < limite:
            self.root.update()
            time.sleep(0.005)
        self.assertFalse(self.app.ocupada)

    def test_interfaz_responde_y_no_admite_doble_envio(self):
        liberar = threading.Event()
        pulsos, resultados = [], []

        def tarea():
            liberar.wait(2)
            return threading.get_ident()

        self.assertTrue(self.app.ejecutar(tarea, resultados.append))
        self.assertFalse(self.app.ejecutar(tarea, resultados.append))
        self.assertEqual(str(self.app.nombre.cget("state")), "disabled")
        self.root.after(10, lambda: (pulsos.append("activa"), liberar.set()))
        self.esperar()
        self.assertEqual(pulsos, ["activa"])
        self.assertNotEqual(resultados[0], threading.get_ident())
        self.app.ejecutar(threading.get_ident, resultados.append)
        self.esperar()
        self.assertEqual(resultados[0], resultados[1])

    def test_limpiar_conserva_tp_documentos_y_validacion(self):
        app = self.app
        app.numero.set("123456")
        app.validado = {"numero": "123456", "estado": "EN EJECUCION", "fecha_plan": "2099-01-01"}
        app.documentos = {1: {"ruta": "uno.pdf"}}
        app.ultima_bitacora = ("datos", "registro")
        app.nombre.insert(0, "Operador")
        app.telefono.insert(0, "987654321")
        app.empresa.insert(0, "Empresa")
        app.limpiar_datos()
        self.assertEqual([app.nombre.get(), app.telefono.get(), app.empresa.get()], ["", "", ""])
        self.assertEqual(app.numero.get(), "123456")
        self.assertEqual(app.validado["estado"], "EN EJECUCION")
        self.assertEqual(app.documentos, {1: {"ruta": "uno.pdf"}})
        self.assertEqual(app.ultima_bitacora, ("datos", "registro"))

    def test_cambio_de_tp_deshabilita_acciones(self):
        app = self.app
        app.numero.set("123456")
        app.mostrar_datos(
            {"numero": "123456", "estado": "PLANIFICADO", "fecha_plan": "2099-01-01", "rpn": 20}
        )
        app.actualizar_botones()
        self.assertEqual(str(app.btn_iniciar.cget("state")), "normal")
        app.numero.set("654321")
        self.assertIsNone(app.validado)
        self.assertEqual(str(app.btn_iniciar.cget("state")), "disabled")
        self.assertEqual(str(app.btn_finalizar.cget("state")), "disabled")

    def test_distribucion_compacta_sin_controles_recortados(self):
        app = self.app
        app.etiquetas_pdf[1].config(text="planificacion_documento_extenso_2026.pdf")
        app.resultado.config(text="Hay envíos sin confirmar. Revise Herramientas → Pendientes.")
        self.root.update()
        self.assertLessEqual(self.root.winfo_width(), 480)
        self.assertLessEqual(self.root.winfo_height(), 540)
        for widget in app.widgets:
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(
                widget.winfo_rooty() + widget.winfo_height(),
                self.root.winfo_rooty() + self.root.winfo_height(),
            )
            self.assertLessEqual(
                widget.winfo_rootx() + widget.winfo_width(),
                self.root.winfo_rootx() + self.root.winfo_width(),
            )

    def test_restaurar_no_abre_formulario_y_conserva_datos(self):
        app = self.app
        app.conectada = True
        app.nombre.insert(0, "Operador")
        app.telefono.insert(0, "987654321")
        app.empresa.insert(0, "Empresa")
        app.documentos = {1: {"ruta": "uno.pdf"}}
        app.numero.set("123456")
        app.validado = {"numero": "123456", "estado": "PLANIFICADO", "fecha_plan": "2099-01-01"}
        app.cliente.restaurar_sesion.return_value = "Sesión reutilizada"
        with patch.object(app, "mostrar_login") as formulario:
            app.restaurar_sesion()
            self.esperar()
            self.root.update()
            formulario.assert_not_called()
        self.assertTrue(app.conectada)
        self.assertIsNone(app.validado)
        self.assertEqual(
            [app.nombre.get(), app.telefono.get(), app.empresa.get()],
            ["Operador", "987654321", "Empresa"],
        )
        self.assertEqual(app.documentos, {1: {"ruta": "uno.pdf"}})
        app.cliente.login.assert_not_called()

    def test_restaurar_solo_abre_acceso_cuando_es_necesario(self):
        self.app.cliente.restaurar_sesion.side_effect = CredencialesRequeridas("PSG pide acceso")
        with patch.object(self.app, "mostrar_login") as formulario:
            self.app.restaurar_sesion()
            self.esperar()
            self.root.update()
            formulario.assert_called_once()
        self.assertFalse(self.app.conectada)

    def test_fallo_red_no_pide_credenciales(self):
        self.app.cliente.restaurar_sesion.side_effect = ErrorAplicacion("Conexión interrumpida")
        with (
            patch.object(self.app, "mostrar_login") as formulario,
            patch("Prueba2PDF.messagebox.showerror") as aviso,
        ):
            self.app.restaurar_sesion()
            self.esperar()
            self.root.update()
            formulario.assert_not_called()
            aviso.assert_called_once()


if __name__ == "__main__":
    unittest.main()
