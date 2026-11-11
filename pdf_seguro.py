"""Lectura de PDF en proceso separado, con límites y huellas de contenido."""

import hashlib
import io
import multiprocessing
import re
from pathlib import Path

from pypdf import PdfReader

from psg_core import ErrorAplicacion

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGINAS = 500
MAX_TEXTO = 2_000_000
TIEMPO_PDF = 25


def leer_archivo(ruta):
    archivo = Path(ruta)
    if archivo.suffix.lower() != ".pdf":
        raise ErrorAplicacion("Seleccione un archivo PDF.")
    with archivo.open("rb") as entrada:
        contenido = entrada.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise ErrorAplicacion("El PDF supera el límite de 20 MB.")
    if not contenido.startswith(b"%PDF-"):
        raise ErrorAplicacion("El archivo no tiene una cabecera PDF válida.")
    return contenido


def extraer_numeros(contenido):
    reader = PdfReader(io.BytesIO(contenido), strict=True)
    if reader.is_encrypted:
        raise ErrorAplicacion("El PDF está cifrado. Cargue una copia autorizada sin contraseña.")
    if len(reader.pages) > MAX_PAGINAS:
        raise ErrorAplicacion("El PDF supera el límite de 500 páginas.")
    numeros, longitud = set(), 0
    for pagina in reader.pages:
        texto = pagina.extract_text() or ""
        longitud += len(texto)
        if longitud > MAX_TEXTO:
            raise ErrorAplicacion("El PDF contiene demasiado texto para procesarlo con seguridad.")
        numeros.update(re.findall(r"(?<!\d)[0-9]{1,20}(?!\d)", texto))
    if not numeros:
        raise ErrorAplicacion(
            "No se encontraron números en el texto del PDF. Si es una imagen escaneada, necesita una versión con texto."
        )
    return numeros


def _proceso(contenido, conexion):
    try:
        numeros = extraer_numeros(contenido)
        conexion.send(("ok", numeros))
    except Exception as error:
        mensaje = (
            str(error)
            if isinstance(error, ErrorAplicacion)
            else "El PDF está dañado o utiliza un formato no compatible."
        )
        conexion.send(("error", mensaje))
    finally:
        conexion.close()


def cargar_documento(ruta):
    contenido = leer_archivo(ruta)
    huella = hashlib.sha256(contenido).hexdigest()
    contexto = multiprocessing.get_context("spawn")
    receptor, emisor = contexto.Pipe(duplex=False)
    proceso = contexto.Process(target=_proceso, args=(contenido, emisor), daemon=True)
    try:
        proceso.start()
        emisor.close()
        if not receptor.poll(TIEMPO_PDF):
            raise ErrorAplicacion(
                "Se detuvo la lectura del PDF por superar 25 segundos. Pruebe con un documento más pequeño."
            )
        try:
            estado, resultado = receptor.recv()
        except EOFError as error:
            raise ErrorAplicacion(
                "El lector PDF se cerró inesperadamente. El documento no se cargó."
            ) from error
        if estado != "ok":
            raise ErrorAplicacion(resultado)
        return {
            "ruta": str(Path(ruta).resolve()),
            "huella": huella,
            "numeros": frozenset(resultado),
        }
    finally:
        receptor.close()
        emisor.close()
        if proceso.pid:
            if proceso.is_alive():
                proceso.terminate()
            proceso.join(timeout=3)
            if proceso.is_alive():
                proceso.kill()
                proceso.join(timeout=3)
            proceso.close()


def comprobar_documentos(documentos, numero):
    if not documentos:
        raise ErrorAplicacion("Cargue al menos un PDF válido.")
    encontrado = False
    for documento in documentos:
        actual = hashlib.sha256(leer_archivo(documento["ruta"])).hexdigest()
        if actual != documento["huella"]:
            raise ErrorAplicacion("Un PDF cambió desde su carga. Cárguelo y valide nuevamente.")
        encontrado = encontrado or numero in documento["numeros"]
    if not encontrado:
        raise ErrorAplicacion("El TP no aparece como número completo en los PDF cargados.")
