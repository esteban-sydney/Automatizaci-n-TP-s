# Validador TP

Aplicación de escritorio para consultar trabajos programados en PSG, verificar
su presencia en dos PDF y registrar el inicio, el cierre y sus bitácoras.
Requiere Windows, Microsoft Edge, Python 3.11 o posterior y acceso autorizado
a la red corporativa. La versión actual se verificó con Python 3.13.

## Abrir la aplicación

Haz doble clic en **Iniciar Validador.cmd**, o ejecuta desde esta carpeta:

```powershell
.\.venv\Scripts\python.exe .\Prueba2PDF.py
```

No requiere permisos de administrador. El ejecutable antiguo del escritorio
contiene otra versión y todavía no incorpora estas mejoras.

Para una instalación nueva en otra carpeta:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

El entorno del proyecto está aislado de los paquetes globales. No se descarga
otro navegador: Playwright utiliza Edge instalado en Windows.

## Acceso y conexión

El acceso usa HTTPS de forma predeterminada, valida el dominio y protocolo
antes de rellenar credenciales y bloquea navegaciones y envíos a otros destinos.
El formulario prepara la conexión sin depender del texto del menú ni de un
botón Salir. Se contemplan páginas con marcos internos y formularios de acceso
dentro de ellos. Los avisos de seguridad se conservan para que el operador los
lea y cierre en Edge. Si PSG pide cambio de clave, ese paso debe completarse.

Después de ingresar, carga un PDF y valida un TP: la app consulta la página
protegida del trabajo y comprueba su número, fecha, RPN y estado. Hasta que esa
consulta tenga éxito, iniciar y finalizar permanecen deshabilitados. Una pantalla
sin formulario de acceso no se considera prueba de autorización para operar.

Si falla la preparación del acceso, se intenta guardar
`%LOCALAPPDATA%\ValidadorTP\diagnostico_acceso.json`. Solo contiene el estado HTTP
y conteos de marcos, enlaces, campos de contraseña visibles y tablas; no contiene
valores, HTML, URLs, cookies ni credenciales.

Si TI confirma que este PSG antiguo solamente admite HTTP, marca **Usar HTTP
para PSG antiguo** en el formulario de acceso. Esta elección vale para la
ejecución actual y permite una redirección posterior a HTTPS. No hay cambio
automático a HTTP. HTTP no cifra las credenciales ni el tráfico.

La app reutiliza la ventana de Edge durante su ejecución y no conecta con el
perfil personal. **Restaurar sesión** primero reutiliza las cookies existentes:
no vuelve a pedir la clave si PSG mantiene el acceso. Si solo cerraste la pestaña,
abre otra en el mismo contexto para conservar la sesión.

Si PSG vuelve a mostrar el formulario de acceso, la app intenta reconectar una
vez con las credenciales del ingreso inicial. Esas credenciales se mantienen
únicamente en memoria durante esta ejecución, no se escriben en archivos y se
descartan al cerrar la app. Si el intento falla, se descartan también para no
repetir una clave incorrecta y se solicita un nuevo ingreso. Tras reiniciar la
aplicación, cambiar la contraseña o recibir una verificación obligatoria de PSG,
puede ser necesario volver a ingresarlas. No se conservan cookies al cerrar.

Restaurar no inicia, documenta ni finaliza trabajos. Conserva los PDF y los datos
del operador, pero exige validar nuevamente el TP antes de habilitar acciones.

La ventana permanece operativa durante las consultas. Los botones y los campos
se bloquean mientras hay una tarea, y solo se permite una instancia por usuario.
Al cerrar, la app espera que termine la operación y luego cierra su navegador.

## PDF y validación

- Se admiten dos PDF, con texto extraíble, de hasta 20 MB y 500 páginas cada uno.
- La lectura ocurre en un proceso separado y se detiene después de 25 segundos.
- Se rechazan documentos cifrados, archivos falsos y texto excesivo.
- El TP debe coincidir con un número completo; no se aceptan coincidencias parciales.
- La huella SHA-256 se comprueba de nuevo antes de validar u operar. Si el PDF
  cambió o desapareció, hay que cargarlo nuevamente.
- El PDF es una referencia local. No se verifica una firma del emisor y no
  reemplaza los permisos y las validaciones del servidor PSG.

El proceso separado limita el efecto de un bloqueo del lector, pero no es un
sandbox de seguridad del sistema operativo ni impone una cuota de memoria.
Carga documentos de origen corporativo conocido.

## Operaciones y recuperación

La app vuelve a comprobar el TP y su estado antes de enviar una acción. El
inicio de un trabajo vencido queda bloqueado. No se asume que un envío tuvo
éxito: debe comprobarse el estado del trabajo o el texto de su bitácora.
Después de **Iniciar ejecución**, la app reconoce la pantalla intermedia y
pulsa **Confirmar** o **Continuar** dentro del formulario. No selecciona
**Volver**, aunque aparezca primero. Si la dirección indica otro número de TP,
se detiene antes de enviar. Luego comprueba el estado en ejecución y registra
la bitácora.
Los identificadores técnicos se conservan solo en el registro local; no se
añaden al texto de inicio, cierre ni a los TXT exportados.

El recorrido de los formularios incorpora pausas de 1,5 segundos entre pasos
y 2,5 segundos después de guardar. La bitácora se escribe progresivamente,
con 25 ms entre teclas, y se espera su confirmación antes de continuar al cierre.
La interfaz sigue respondiendo mientras el navegador realiza estos pasos.

Los enlaces de acción pueden tardar hasta 20 segundos en aparecer. Se reconocen
acentos, iconos y enlaces dentro de marcos del portal. Dos enlaces al mismo
destino se tratan como una sola acción; si apuntan a destinos distintos, se
detiene el proceso e indica cuál era la acción buscada. Estas esperas no vuelven
a enviar formularios automáticamente.

Las consultas de lectura pueden reintentarse una vez ante fallos temporales.
El acceso, inicio, cierre y envío de bitácoras **no se repiten automáticamente**.
Un error tras enviar puede significar que PSG procesó la solicitud aunque se
haya perdido la respuesta.

El registro local se guarda en:

```text
%LOCALAPPDATA%\ValidadorTP\operaciones.sqlite3
```

Está fuera de la carpeta del ejecutable y de OneDrive. Solo guarda identificador
de operación, número TP, tipo de acción, estado y fecha UTC. No guarda nombres,
teléfonos, contraseñas ni cookies. Hereda los permisos de la carpeta del usuario;
no es un registro inalterable ni está cifrado por la aplicación.

En **Herramientas** encontrarás:

- **Diagnóstico de conexión:** abre una página de prueba de PSG sin introducir
  credenciales ni ejecutar acciones. Comprueba disponibilidad, no permisos sobre TP.
- **Revisar operaciones pendientes:** muestra envíos sin confirmación. Revisa
  primero cada resultado en PSG y solo después márcalo como revisado. Esa opción
  no vuelve a ejecutar operaciones en el portal.
- **Recuperar última bitácora pendiente:** disponible durante la misma ejecución.
  Busca el texto completo en la página del TP y, si no aparece, permite enviarla
  una vez con confirmación del operador. No garantiza ausencia de duplicados si
  PSG oculta o pagina su historial. Si reiniciaste la app, verifica el portal y
  los pendientes manualmente; el texto de la bitácora no se guarda en el disco.

**Exportar TXT** permite elegir la carpeta y el nombre. La escritura es atómica:
si falla, conserva el archivo anterior. El TXT contiene datos de personas y TP;
su protección depende de la ubicación y permisos que elijas. La bitácora vieja
del proyecto se conserva y no se migra ni elimina automáticamente.

**Limpiar datos** borra únicamente nombre, teléfono y empresa.

## Si no conecta o faltan permisos

1. Comprueba que PSG abra manualmente en Edge desde la misma red o VPN.
2. Usa **Herramientas → Diagnóstico de conexión**.
3. Si aparece 401/403, revisa sesión y permisos con el administrador de PSG.
4. Si aparece un error de certificado, proxy, bloqueo corporativo o DNS, consulta
   a TI. La app no desactiva certificados, firewall, proxy, políticas ni antivirus.
5. Si no se puede escribir un archivo, elige una carpeta donde tengas permiso.
   Si falla el registro local, revisa la carpeta de usuario y el espacio en disco.
6. Si PSG cambió sus enlaces, tablas, formularios o indicador de acceso, deben
   ajustarse los selectores de `psg_core.py` a una página autorizada real. La app
   se detiene ante estructuras ambiguas en lugar de elegir un botón arbitrario.

No se puede garantizar desde el cliente la disponibilidad de PSG, su soporte de
HTTPS, los permisos del operador ni las políticas corporativas. No se modificó
el servidor PSG ni se hicieron pruebas de ataque contra él.

## Verificación y desarrollo

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\ruff.exe check Prueba2PDF.py psg_core.py pdf_seguro.py registro_local.py tests
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt --no-deps --disable-pip --progress-spinner off
```

Las pruebas incluyen interfaz, PDF reales, SQLite y un flujo completo en Edge
con respuestas simuladas. Las pruebas de navegador interceptan sus peticiones;
no acceden al PSG real ni usan credenciales de operadores.

La auditoría consulta nombres y versiones de dependencias públicas, no datos de PSG.
Un resultado sin vulnerabilidades conocidas no equivale a una garantía de seguridad.

- `Prueba2PDF.py`: interfaz y coordinación de tareas.
- `psg_core.py`: navegador, conexión y controles del portal.
- `pdf_seguro.py`: validación y lectura limitada de PDF.
- `registro_local.py`: registro operativo, bloqueo de instancia y exportación.
- `requirements.txt`: dependencias de ejecución fijadas.
- `tests/`: pruebas de regresión de interfaz, PDF, registro y PSG simulado.
- `Iniciar Validador.cmd`: lanzador de la versión actual.
- `Prueba2PDF.spec`: configuración para empaquetar un ejecutable cuando se necesite.

Antes de distribuir un ejecutable nuevo falta validar la integración en PSG real
y empaquetar y probar esa versión. No se ha generado un nuevo `.exe`.
