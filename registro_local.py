"""Registro operativo local: no almacena credenciales, cookies ni teléfonos."""

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from psg_core import ErrorAplicacion


def guardar_txt(ruta, contenido):
    """Reemplazo atómico: un fallo de escritura no trunca la bitácora anterior."""
    destino = Path(ruta)
    if destino.suffix.lower() != ".txt":
        raise ErrorAplicacion("La bitácora debe guardarse con extensión .txt.")
    temporal = destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporal.open("x", encoding="utf-8", newline="\n") as archivo:
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, destino)
    finally:
        try:
            temporal.unlink(missing_ok=True)
        except OSError:
            # Si la carpeta perdió permisos, se conserva el error de la escritura.
            pass


def carpeta_datos():
    # Fuera del ejecutable y de OneDrive; permisos heredados del usuario de Windows.
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "ValidadorTP"


class Registro:
    def __init__(self, carpeta=None):
        self.carpeta = Path(carpeta) if carpeta is not None else carpeta_datos()

    @contextmanager
    def _conexion(self):
        self.carpeta.mkdir(parents=True, exist_ok=True)
        conexion = sqlite3.connect(self.carpeta / "operaciones.sqlite3", timeout=5)
        try:
            conexion.execute("""CREATE TABLE IF NOT EXISTS operaciones (
                id TEXT PRIMARY KEY, tp TEXT NOT NULL, accion TEXT NOT NULL,
                estado TEXT NOT NULL, actualizado TEXT NOT NULL)""")
            conexion.commit()
            with conexion:
                yield conexion
        finally:
            conexion.close()

    def crear(self, numero, accion):
        identificador = uuid.uuid4().hex
        with self._conexion() as conexion:
            conexion.execute(
                "INSERT INTO operaciones VALUES (?, ?, ?, ?, ?)",
                (identificador, numero, accion, "preparada", self.ahora()),
            )
        return identificador

    def estado(self, identificador, estado):
        if estado not in (
            "preparada",
            "enviando",
            "confirmada",
            "incierta",
            "cancelada",
            "revisada",
        ):
            raise ValueError("Estado de operación inválido")
        with self._conexion() as conexion:
            conexion.execute(
                "UPDATE operaciones SET estado=?, actualizado=? WHERE id=?",
                (estado, self.ahora(), identificador),
            )

    def pendientes(self, numero=None):
        consulta = "SELECT id, tp, accion, estado FROM operaciones WHERE estado IN ('enviando', 'incierta')"
        argumentos = ()
        if numero is not None:
            consulta += " AND tp=?"
            argumentos = (numero,)
        with self._conexion() as conexion:
            return conexion.execute(consulta, argumentos).fetchall()

    @staticmethod
    def ahora():
        return datetime.now(UTC).isoformat(timespec="seconds")


class InstanciaUnica:
    """Evita dos aplicaciones actuando simultáneamente bajo el mismo usuario."""

    def __init__(self, carpeta=None):
        self.carpeta = Path(carpeta) if carpeta is not None else carpeta_datos()
        self.archivo = None

    def adquirir(self):
        self.carpeta.mkdir(parents=True, exist_ok=True)
        archivo = (self.carpeta / "aplicacion.lock").open("a+b")
        try:
            archivo.seek(0, 2)
            if archivo.tell() == 0:
                archivo.write(b"0")
                archivo.flush()
            archivo.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            archivo.close()
            return False
        self.archivo = archivo
        return True

    def liberar(self):
        if self.archivo:
            self.archivo.close()
            self.archivo = None
