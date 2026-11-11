"""Validador TP: interfaz compacta y navegador en un hilo de trabajo único."""

import multiprocessing
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pdf_seguro import cargar_documento, comprobar_documentos
from psg_core import (
    ClientePSG,
    Configuracion,
    CredencialesRequeridas,
    ErrorAplicacion,
    explicar_error,
    validar_numero,
    validar_operador,
)
from registro_local import InstanciaUnica, Registro, guardar_txt


class Aplicacion:
    def __init__(self, ventana, cliente=None, registro=None):
        self.ventana = ventana
        self.cliente = cliente or ClientePSG()
        self.registro = registro or Registro()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PSG")
        self.futuro = None
        self.ocupada = self.cerrando = self.conectada = False
        self.config = Configuracion()
        self.documentos = {}
        self.validado = self.ultima_bitacora = self.pendiente_bitacora = None
        self.widgets = []
        self.crear_interfaz()

    def boton(self, padre, texto, funcion):
        boton = ttk.Button(padre, text=texto, command=funcion)
        self.widgets.append(boton)
        return boton

    def crear_interfaz(self):
        root = self.ventana
        root.title("Validador TP")
        root.configure(bg="white")
        root.option_add("*Font", ("Segoe UI", 9))
        card = tk.Frame(root, bg="white", padx=12, pady=10)
        card.pack(fill="both", expand=True)
        for col in (0, 1):
            card.columnconfigure(col, weight=1, uniform="campos")
        tk.Label(card, text="Validador TP", font=("Segoe UI", 12, "bold"), bg="white").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        herramientas = ttk.Menubutton(card, text="Herramientas")
        herramientas.grid(row=0, column=1, sticky="e", pady=(0, 6))
        menu = tk.Menu(herramientas, tearoff=False)
        menu.add_command(label="Diagnóstico de conexión", command=self.diagnosticar)
        menu.add_command(label="Revisar operaciones pendientes", command=self.revisar_pendientes)
        menu.add_command(
            label="Recuperar última bitácora pendiente", command=self.recuperar_bitacora
        )
        herramientas.config(menu=menu)
        self.widgets.append(herramientas)
        tk.Label(card, text="Número TP", bg="white").grid(row=1, column=0, sticky="w")
        busqueda = tk.Frame(card, bg="white")
        busqueda.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        busqueda.columnconfigure(0, weight=1)
        self.numero = tk.StringVar()
        self.entry_trabajo = ttk.Entry(busqueda, textvariable=self.numero)
        self.entry_trabajo.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.entry_trabajo.bind("<Return>", lambda event: self.validar())
        self.numero.trace_add("write", self.invalidar)
        self.widgets.append(self.entry_trabajo)
        self.boton(busqueda, "Validar TP", self.validar).grid(row=0, column=1)
        documentos = tk.Frame(card, bg="white")
        documentos.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        documentos.columnconfigure(1, weight=1)
        self.etiquetas_pdf = {}
        for indice in (1, 2):
            self.boton(
                documentos, f"Cargar PDF {indice}", lambda i=indice: self.cargar_pdf(i)
            ).grid(row=indice - 1, column=0, sticky="ew", padx=(0, 6), pady=2)
            etiqueta = tk.Label(
                documentos,
                text=f"Sin PDF {indice}",
                bg="white",
                fg="#b91c1c",
                width=34,
                height=2,
                anchor="w",
                justify="left",
                wraplength=275,
            )
            etiqueta.grid(row=indice - 1, column=1, sticky="ew", pady=2)
            self.etiquetas_pdf[indice] = etiqueta
        self.resultado = tk.Label(
            card,
            text="Inicie sesión para consultar PSG.",
            bg="#f3f4f6",
            padx=6,
            pady=4,
            anchor="w",
            justify="left",
            wraplength=380,
            height=2,
        )
        self.resultado.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.rpn = tk.Label(card, text="", bg="#eef2ff", fg="#1e3a8a", padx=6, pady=4, anchor="w")
        self.rpn.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        tk.Label(card, text="Nombre", bg="white").grid(row=6, column=0, sticky="w")
        tk.Label(card, text="Teléfono", bg="white").grid(row=6, column=1, sticky="w")
        self.nombre = ttk.Entry(card)
        self.nombre.grid(row=7, column=0, sticky="ew", padx=(0, 6), pady=(2, 4))
        self.telefono = ttk.Entry(card)
        self.telefono.grid(row=7, column=1, sticky="ew", pady=(2, 4))
        tk.Label(card, text="Empresa (opcional)", bg="white").grid(row=8, column=0, sticky="w")
        empresa = tk.Frame(card, bg="white")
        empresa.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        empresa.columnconfigure(0, weight=1)
        self.empresa = ttk.Entry(empresa)
        self.empresa.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        limpiar = tk.Button(
            empresa,
            text="Limpiar datos",
            command=self.limpiar_datos,
            bg="#fef3c7",
            fg="#78350f",
            activebackground="#fde68a",
            activeforeground="#78350f",
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#f59e0b",
            highlightcolor="#b45309",
            cursor="hand2",
            padx=8,
            pady=3,
        )
        limpiar.grid(row=0, column=1, sticky="ew")
        self.widgets.extend((self.nombre, self.telefono, self.empresa, limpiar))
        self.btn_iniciar = self.boton(card, "Iniciar TP", self.iniciar)
        self.btn_iniciar.grid(row=10, column=0, sticky="ew", padx=(0, 6))
        self.btn_finalizar = self.boton(card, "Finalizar TP", self.mostrar_finalizar)
        self.btn_finalizar.grid(row=10, column=1, sticky="ew")
        self.btn_exportar = self.boton(card, "Exportar TXT", self.exportar)
        self.btn_exportar.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        self.boton(card, "Restaurar sesión", self.restaurar_sesion).grid(
            row=12, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(card, text="Cerrar", command=self.cerrar).grid(row=12, column=1, sticky="ew")
        root.protocol("WM_DELETE_WINDOW", self.cerrar)
        root.update_idletasks()
        ancho, alto = max(430, root.winfo_reqwidth()), root.winfo_reqheight() + 12
        root.geometry(f"{ancho}x{alto}")
        root.minsize(ancho, alto)
        self.actualizar_botones()

    def limpiar_datos(self):
        if not self.ocupada:
            for campo in (self.nombre, self.telefono, self.empresa):
                campo.delete(0, tk.END)
            self.nombre.focus_set()

    def invalidar(self, *args):
        self.validado = None
        self.rpn.config(text="")
        self.resultado.config(text="Valide el TP para habilitar acciones.", fg="#374151")
        self.actualizar_botones()

    def actualizar_botones(self):
        for widget in self.widgets:
            widget.config(state="disabled" if self.ocupada else "normal")
        estado = self.validado["estado"] if self.validado else ""
        vencido = bool(
            self.validado
            and datetime.strptime(self.validado["fecha_plan"], "%Y-%m-%d").date()
            < datetime.now().date()
        )
        self.btn_iniciar.config(
            state="normal"
            if not self.ocupada and estado == "PLANIFICADO" and not vencido
            else "disabled"
        )
        self.btn_finalizar.config(
            state="normal"
            if not self.ocupada and estado in ("EJECUCION", "EN EJECUCION")
            else "disabled"
        )
        self.btn_exportar.config(
            state="normal" if not self.ocupada and self.ultima_bitacora else "disabled"
        )

    def ejecutar(self, tarea, exito, mensaje="Consultando PSG…", error=None):
        if self.ocupada or self.cerrando:
            return False
        self.ocupada = True
        self.resultado.config(text=mensaje, fg="#374151")
        self.actualizar_botones()
        self.futuro = self.executor.submit(tarea)

        def recoger():
            if not self.futuro.done():
                self.ventana.after(80, recoger)
                return
            futuro, self.futuro = self.futuro, None
            self.ocupada = False
            try:
                respuesta = futuro.result()
            except Exception as causa:
                self.validado = None
                self.resultado.config(
                    text="No se completó la operación. Revise el detalle.", fg="#b91c1c"
                )
                if error and not self.cerrando:
                    error(causa)
                elif not self.cerrando:
                    messagebox.showerror(
                        "Operación no completada", explicar_error(causa), parent=self.ventana
                    )
            else:
                if not self.cerrando:
                    exito(respuesta)
            finally:
                self.actualizar_botones()
                if self.cerrando:
                    self.terminar_cierre()

        self.ventana.after(80, recoger)
        return True

    def restaurar_sesion(self):
        if self.ocupada or self.cerrando:
            return
        self.invalidar()
        self.conectada = False
        config = self.config

        def listo(mensaje):
            self.conectada = True
            self.resultado.config(text=mensaje, fg="#166534")

        def fallo(causa):
            if isinstance(causa, CredencialesRequeridas):
                self.resultado.config(text=str(causa), fg="#b45309")
                self.ventana.after_idle(self.mostrar_login)
            else:
                messagebox.showerror("Restaurar sesión", explicar_error(causa), parent=self.ventana)

        self.ejecutar(
            lambda: self.cliente.restaurar_sesion(config),
            listo,
            "Intentando recuperar la sesión de PSG…",
            fallo,
        )

    def mostrar_login(self):
        if self.ocupada or self.cerrando:
            return
        self.invalidar()
        modal = tk.Toplevel(self.ventana)
        modal.title("Acceso a PSG")
        modal.resizable(False, False)
        modal.transient(self.ventana)
        modal.grab_set()
        panel = ttk.Frame(modal, padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Usuario del portal").pack(anchor="w")
        usuario = ttk.Entry(panel, width=36)
        usuario.pack(fill="x", pady=(3, 8))
        ttk.Label(panel, text="Contraseña").pack(anchor="w")
        clave = ttk.Entry(panel, show="*")
        clave.pack(fill="x", pady=(3, 8))
        http = tk.BooleanVar(value=self.config.permitir_http)
        ttk.Checkbutton(panel, text="Usar HTTP para PSG antiguo", variable=http).pack(anchor="w")
        ttk.Label(
            panel,
            text="HTTPS es la opción predeterminada. HTTP no cifra\nlas credenciales: úselo solo si TI autoriza ese acceso.",
            foreground="#78350f",
        ).pack(anchor="w", pady=(3, 10))

        def entrar():
            user, password = usuario.get().strip(), clave.get()
            if not user or not password:
                messagebox.showwarning(
                    "Datos incompletos", "Ingrese usuario y contraseña.", parent=modal
                )
                return
            config = Configuracion(permitir_http=http.get())
            self.config = config
            self.conectada = False
            ingresar.config(state="disabled")
            clave.delete(0, tk.END)
            usuario.config(state="disabled")
            clave.config(state="disabled")

            def conectado(mensaje):
                self.config = config
                self.conectada = True
                if modal.winfo_exists():
                    modal.destroy()
                self.resultado.config(text=mensaje, fg="#166534")

            def fallo(causa):
                if modal.winfo_exists():
                    ingresar.config(state="normal")
                    usuario.config(state="normal")
                    clave.config(state="normal")
                    clave.focus_set()
                    messagebox.showerror(
                        "Acceso no confirmado", explicar_error(causa), parent=modal
                    )

            self.ejecutar(
                lambda: self.cliente.login(user, password, config),
                conectado,
                "Comprobando acceso a PSG…",
                fallo,
            )

        ingresar = ttk.Button(panel, text="Ingresar", command=entrar)
        ingresar.pack(fill="x")
        modal.bind("<Return>", lambda event: entrar() if not self.ocupada else None)
        usuario.focus_set()

    def cargar_pdf(self, indice):
        if self.ocupada:
            return
        ruta = filedialog.askopenfilename(parent=self.ventana, filetypes=[("PDF", "*.pdf")])
        if not ruta:
            return
        self.invalidar()

        def listo(documento):
            self.documentos[indice] = documento
            self.etiquetas_pdf[indice].config(text=Path(documento["ruta"]).name, fg="#166534")
            self.resultado.config(text="PDF cargado y comprobado. Valide el TP.", fg="#166534")

        self.ejecutar(lambda: cargar_documento(ruta), listo, "Leyendo PDF de forma aislada…")

    def validar(self):
        if self.ocupada:
            return
        self.invalidar()
        try:
            numero = validar_numero(self.numero.get().strip())
            if not self.conectada:
                raise ErrorAplicacion("Inicie sesión en PSG primero.")
            documentos = tuple(self.documentos.values())
        except Exception as error:
            messagebox.showwarning("Validación", explicar_error(error), parent=self.ventana)
            return

        def tarea():
            comprobar_documentos(documentos, numero)
            return self.cliente.leer_tp(numero), self.registro.pendientes(numero)

        def listo(respuesta):
            datos, pendientes = respuesta
            if pendientes:
                self.resultado.config(
                    text="Hay envíos sin confirmar. Revise Herramientas → Pendientes.", fg="#b45309"
                )
                messagebox.showwarning(
                    "Revisión necesaria",
                    "Hay envíos cuyo resultado no se confirmó. Revise PSG y las operaciones pendientes antes de habilitar acciones.",
                    parent=self.ventana,
                )
            else:
                self.mostrar_datos(datos)

        self.ejecutar(tarea, listo)

    def mostrar_datos(self, datos):
        self.validado = (
            datos if datos["estado"] in ("PLANIFICADO", "EJECUCION", "EN EJECUCION") else None
        )
        self.resultado.config(
            text=f"TP {datos['numero']}: {datos['estado']}",
            fg="#166534" if self.validado else "#b45309",
        )
        self.rpn.config(text=f"RPN: {datos['rpn']} | Fecha: {datos['fecha_plan']}")

    def contexto_accion(self):
        if (
            not self.conectada
            or not self.validado
            or self.numero.get().strip() != self.validado["numero"]
        ):
            raise ErrorAplicacion("Valide nuevamente el TP antes de actuar.")
        return self.validado["numero"], tuple(self.documentos.values())

    def operar(self, numero, accion, funcion):
        identificador = self.registro.crear(numero, accion)
        enviado = False

        def antes_de_enviar():
            nonlocal enviado
            self.registro.estado(identificador, "enviando")
            enviado = True

        try:
            resultado = funcion(antes_de_enviar, identificador)
            self.registro.estado(identificador, "confirmada")
            return resultado
        except Exception:
            self.registro.estado(identificador, "incierta" if enviado else "cancelada")
            raise

    def verificar_antes(self, numero, documentos):
        comprobar_documentos(documentos, numero)
        if self.registro.pendientes(numero):
            raise ErrorAplicacion(
                "Hay una operación pendiente de revisión para este TP. Use Herramientas → Revisar operaciones pendientes."
            )

    @staticmethod
    def crear_texto(numero, nombre, telefono, empresa, accion):
        hora = datetime.now().strftime("%H:%M:%S %Y-%m-%d")
        partes = [f"{nombre}, Cel {telefono}"]
        if empresa:
            partes.append(f"Empresa {empresa}")
        return f"{', '.join(partes)} {accion} TP {numero} a las {hora}"

    def registrar_bitacora(self, numero, texto):
        pendiente = {}

        def envio(antes, identificador):
            # El identificador se conserva solo en el registro local.
            marca = completo = texto
            pendiente.update(numero=numero, texto=completo, marca=marca, id=identificador)
            self.cliente.documentar(numero, completo, marca, antes)
            return completo

        try:
            completo = self.operar(numero, "bitacora", envio)
            return completo, None
        except Exception as error:
            return pendiente.get("texto", texto), {
                "datos": pendiente,
                "mensaje": explicar_error(error),
            }

    def iniciar(self):
        if self.ocupada:
            return
        try:
            numero, documentos = self.contexto_accion()
            nombre, telefono, empresa = validar_operador(
                self.nombre.get(), self.telefono.get(), self.empresa.get()
            )
        except Exception as error:
            messagebox.showwarning("Inicio", explicar_error(error), parent=self.ventana)
            return
        texto = self.crear_texto(numero, nombre, telefono, empresa, "inicia")

        def tarea():
            self.verificar_antes(numero, documentos)
            datos = self.operar(
                numero, "inicio", lambda antes, _: self.cliente.iniciar(numero, antes)
            )
            completo, pendiente = self.registrar_bitacora(numero, texto)
            return datos, completo, pendiente

        self.ejecutar(tarea, self.accion_completada, "Iniciando TP; no repita la acción…")

    def accion_completada(self, respuesta):
        datos, texto, pendiente = respuesta
        self.mostrar_datos(datos)
        self.ultima_bitacora = (datos.copy(), texto)
        self.pendiente_bitacora = pendiente["datos"] if pendiente else None
        if pendiente:
            self.validado = None
            self.resultado.config(
                text="Inicio confirmado; bitácora pendiente de comprobar.", fg="#b45309"
            )
            messagebox.showwarning(
                "Bitácora pendiente",
                "El TP se inició, pero la bitácora no quedó confirmada.\nUse Herramientas → Recuperar última bitácora pendiente.\n\n"
                + pendiente["mensaje"],
                parent=self.ventana,
            )
        else:
            messagebox.showinfo(
                "PSG", "Operación y bitácora confirmadas en el portal.", parent=self.ventana
            )

    def mostrar_finalizar(self):
        if self.ocupada:
            return
        try:
            numero, documentos = self.contexto_accion()
        except Exception as error:
            messagebox.showwarning("Cierre", explicar_error(error), parent=self.ventana)
            return
        modal = tk.Toplevel(self.ventana)
        modal.title(f"Finalizar TP {numero}")
        modal.transient(self.ventana)
        modal.resizable(False, False)
        modal.grab_set()
        panel = ttk.Frame(modal, padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Nombre de quien finaliza").pack(anchor="w")
        nombre = ttk.Entry(panel, width=34)
        nombre.pack(fill="x", pady=(3, 8))
        nombre.insert(0, self.nombre.get())
        ttk.Label(panel, text="Teléfono").pack(anchor="w")
        telefono = ttk.Entry(panel)
        telefono.pack(fill="x", pady=(3, 12))
        telefono.insert(0, self.telefono.get())

        def confirmar():
            try:
                operador, celular, _ = validar_operador(nombre.get(), telefono.get())
            except Exception as error:
                messagebox.showwarning("Cierre", explicar_error(error), parent=modal)
                return
            texto = self.crear_texto(numero, operador, celular, "", "finaliza")

            def tarea():
                self.verificar_antes(numero, documentos)
                self.cliente.comprobar_tp(numero, ("EJECUCION", "EN EJECUCION"))
                completo, pendiente = self.registrar_bitacora(numero, texto)
                if pendiente:
                    return None, completo, pendiente
                datos = self.operar(
                    numero,
                    "cierre",
                    lambda antes, _: self.cliente.finalizar(numero, completo, antes),
                )
                return datos, completo, None

            def listo(respuesta):
                datos, completo, pendiente = respuesta
                if pendiente:
                    self.pendiente_bitacora = pendiente["datos"]
                    self.validado = None
                    self.resultado.config(
                        text="No se envió el cierre: bitácora pendiente.", fg="#b45309"
                    )
                    messagebox.showwarning(
                        "Cierre detenido",
                        "No se envió la finalización porque la bitácora no quedó confirmada. Use Herramientas para recuperarla y luego vuelva a validar.",
                        parent=self.ventana,
                    )
                else:
                    self.accion_completada((datos, completo, None))

            if self.ejecutar(tarea, listo, "Finalizando TP; no repita la acción…"):
                modal.destroy()

        ttk.Button(panel, text="Confirmar cierre", command=confirmar).pack(fill="x")

    def exportar(self):
        if self.ocupada or not self.ultima_bitacora:
            return
        datos, texto = self.ultima_bitacora
        ruta = filedialog.asksaveasfilename(
            parent=self.ventana,
            title="Guardar bitácora TXT",
            initialfile=f"TP_{datos['numero']}.txt",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt")],
        )
        if not ruta:
            return
        descripcion = " ".join(datos["descripcion"].split())[:500]
        contenido = f"TP {datos['numero']} {descripcion}\n{texto}\n"

        def guardar():
            guardar_txt(ruta, contenido)

        self.ejecutar(
            guardar,
            lambda _: messagebox.showinfo(
                "Exportación", "Bitácora guardada en la ubicación elegida.", parent=self.ventana
            ),
            "Guardando bitácora…",
        )

    def diagnosticar(self):
        def listo(mensaje):
            self.resultado.config(text="Diagnóstico finalizado.")
            messagebox.showinfo("Conexión con PSG", mensaje, parent=self.ventana)

        self.ejecutar(
            lambda: self.cliente.diagnosticar(self.config),
            listo,
            "Comprobando conexión sin enviar credenciales…",
        )

    def revisar_pendientes(self):
        def listo(pendientes):
            if not pendientes:
                messagebox.showinfo(
                    "Operaciones", "No hay envíos sin confirmar.", parent=self.ventana
                )
                return
            detalle = "\n".join(
                f"TP {tp}: {accion} ({estado})" for _, tp, accion, estado in pendientes[:20]
            )
            if messagebox.askyesno(
                "Revisión manual de PSG",
                detalle
                + "\n\nRevise el resultado de cada envío en PSG.\n¿Ya verificó TODOS estos envíos y desea marcarlos como revisados?\nEsto no ejecuta acciones en el portal.",
                parent=self.ventana,
            ):

                def marcar():
                    for identificador, _, _, _ in pendientes[:20]:
                        self.registro.estado(identificador, "revisada")

                self.ventana.after_idle(
                    lambda: self.ejecutar(
                        marcar, lambda _: self.invalidar(), "Actualizando revisión local…"
                    )
                )

        self.ejecutar(self.registro.pendientes, listo, "Consultando operaciones pendientes…")

    def recuperar_bitacora(self):
        pendiente = self.pendiente_bitacora
        if self.ocupada:
            return
        if not pendiente or not pendiente.get("id"):
            messagebox.showinfo(
                "Bitácora",
                "No hay una bitácora recuperable en esta ejecución. Si reinició la aplicación, revise los pendientes y el portal.",
                parent=self.ventana,
            )
            return
        if not messagebox.askyesno(
            "Recuperar bitácora",
            f"TP {pendiente['numero']}: se buscará el texto de la bitácora en PSG. Si no aparece, se intentará documentar una vez.\n¿Continuar?",
            parent=self.ventana,
        ):
            return

        def tarea():
            self.cliente.documentar(
                pendiente["numero"],
                pendiente["texto"],
                pendiente["marca"],
                lambda: self.registro.estado(pendiente["id"], "enviando"),
            )
            self.registro.estado(pendiente["id"], "confirmada")

        def listo(_):
            self.pendiente_bitacora = None
            self.invalidar()
            messagebox.showinfo(
                "Bitácora",
                "Registro confirmado en PSG. Valide el TP nuevamente.",
                parent=self.ventana,
            )

        self.ejecutar(tarea, listo, "Comprobando y recuperando bitácora…")

    def cerrar(self):
        if self.cerrando:
            return
        self.cerrando = True
        if self.ocupada:
            self.resultado.config(text="Terminando la operación antes de cerrar…")
        else:
            self.terminar_cierre()

    def terminar_cierre(self):
        futuro = self.executor.submit(self.cliente.cerrar)

        def esperar():
            if not futuro.done():
                self.ventana.after(80, esperar)
                return
            self.executor.shutdown(wait=False)
            self.ventana.destroy()

        self.ventana.after(80, esperar)


def main():
    multiprocessing.freeze_support()
    ventana = tk.Tk()
    ventana.withdraw()
    instancia = InstanciaUnica()
    try:
        if not instancia.adquirir():
            messagebox.showinfo(
                "Validador TP",
                "Ya hay una instancia abierta o no se pudo bloquear su registro local. Revise la barra de tareas y los permisos de su carpeta de usuario.",
                parent=ventana,
            )
            ventana.destroy()
            return

        def fallo_interfaz(tipo, error, traceback):
            messagebox.showerror("Validador TP", explicar_error(error), parent=ventana)

        ventana.report_callback_exception = fallo_interfaz
        app = Aplicacion(ventana)
        ventana.deiconify()
        ventana.after(200, app.mostrar_login)
        ventana.mainloop()
    except Exception as error:
        messagebox.showerror("No se pudo iniciar", explicar_error(error), parent=ventana)
        ventana.destroy()
    finally:
        instancia.liberar()


if __name__ == "__main__":
    main()
