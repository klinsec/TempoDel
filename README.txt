# Tempodel - Programador de Borrado de Archivos y Carpetas

## Descripción

Tempodel es una herramienta escrita en Python diseñada para programar la eliminación automática de archivos y carpetas en Windows. Te permite añadir elementos a una lista de borrado, especificando un tiempo (días, horas, minutos, segundos) después del cual se eliminarán los archivos o carpetas. 

## Características Principales

*   **Interfaz Gráfica:** Una ventana principal (`tempodel_gui.py`) para gestionar la lista de borrado programado, añadir/quitar elementos y modificar sus fechas de eliminación.
*   **Integración con el Menú Contextual:** Añade una opción al menú del clic derecho en el Explorador de Windows, permitiendo programar rápidamente el borrado de archivos y carpetas con duraciones predefinidas (1 día, 3 días, 7 días, 30 días) o personalizar la fecha.
*   **Borrador en Segundo Plano:** Un proceso en segundo plano (`tempodel_checker.py`) comprueba periódicamente la lista de borrado y elimina los archivos y carpetas que hayan alcanzado su fecha de expiración.
*   **Programación Flexible:** Permite especificar la duración del borrado en segundos, minutos, horas o días.
*   **Gestión de Multi-Selección:** Maneja correctamente la selección de múltiples archivos desde el menú contextual, permitiendo aplicar un único temporizador de borrado a todos los elementos seleccionados.
*   **Seguridad Básica:** Incluye bloqueos básicos para evitar la corrupción del archivo de programación (`schedule.json`) en caso de acceso simultáneo.
*   **Logging:** El proceso en segundo plano (`tempodel_checker.py`) registra su actividad en un archivo de log (`tempodel_checker.log`), facilitando la depuración y seguimiento.

## Instalación

1.  **Requisitos:**
    *   Python 3.10 instalado en tu sistema (asegúrate de que `pythonw.exe` esté en tu `PATH` o conoce su ruta completa).
2.  **Descarga:** Copia todos los archivos del programa (incluyendo `tempodel_gui.py`, `tempodel_checker.py`, `tempodel_install.reg`, `tempodel_uninstall_FINAL.reg`, `TempoDel.vbs`, `icon.ico` y este archivo `README.md`) a una carpeta en tu disco duro (p.ej., `D:\IA_programs\Organizador de carpetas\Tempodel`).
3.  **Integra Tempodel con el Menú Contextual:**
    *   Ejecuta el archivo `tempodel_install_Cascading.reg` con privilegios de administrador (haz doble clic y acepta la advertencia del Editor del Registro). Esto añade las opciones "Tempodel" al menú del clic derecho en archivos y carpetas.
    *   *Opcional*: Si quieres cambiar el icono de Tempodel, reemplaza el archivo `icon.ico` en la carpeta del programa por tu propio icono.
4.  **Ejecuta Tempodel al Inicio (En Segundo Plano):**
    *   Mueve el acceso directo `TempoDel_Inicio.vbs` al directorio de inicio de Windows:
        `C:\Users\TuNombreDeUsuario\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`
        (*Reemplaza "TuNombreDeUsuario" con tu nombre de usuario de Windows.*)
        *Para acceder a la carpeta `AppData`, es posible que debas habilitar la visualización de archivos y carpetas ocultas en el Explorador de Windows.*
5. **Desinstalar Tempodel del menú contextual:**
    * Ejecuta el archivo `tempodel_uninstall_FINAL.reg` con privilegios de administrador.

## Uso

### Interfaz Gráfica (`tempodel_gui.py`)

1.  Ejecuta `tempodel_gui.py` (haz doble clic o ejecútalo desde la línea de comandos con `python tempodel_gui.py`).
2.  La ventana principal mostrará una lista de los archivos y carpetas programados para borrarse, su tipo (Archivo o Carpeta), la fecha y hora de eliminación programada y la ubicación completa.
3.  **Añadir Archivos/Carpetas:**
    *   Haz clic en "Añadir Archivo" o "Añadir Carpeta" para seleccionar los elementos que deseas programar para borrar.
    *   Se abrirá un diálogo donde podrás especificar el tiempo de borrado (en días, horas, minutos o segundos).
4.  **Modificar Fecha:**
    *   Selecciona un elemento de la lista.
    *   Haz clic en "Modificar Fecha".
    *   Se abrirá el diálogo para ajustar el tiempo de borrado.
5.  **Quitar Seleccionado:**
    *   Selecciona uno o varios elementos de la lista.
    *   Haz clic en "Quitar Seleccionado" para cancelar la programación del borrado (esto no elimina los archivos o carpetas inmediatamente, solo los quita de la lista).
6.  **Refrescar:** Haz clic en "Refrescar" para actualizar la lista desde el archivo de programación (`schedule.json`).

### Menú Contextual

1.  Haz clic derecho sobre uno o varios archivos o carpetas en el Explorador de Windows.
2.  Selecciona "Tempodel" en el menú contextual.
3.  Se desplegará un submenú con las siguientes opciones:
    *   Eliminar en 1 día
    *   Eliminar en 3 días
    *   Eliminar en 7 días
    *   Eliminar en 30 días
    *   Configurar borrado...
4.  Selecciona una opción predefinida para añadir rápidamente los archivos/carpetas seleccionados a la lista de borrado con la duración correspondiente.
5.  Selecciona "Configurar borrado..." para abrir la ventana principal de Tempodel y configurar un tiempo personalizado para todos los archivos seleccionados.

### Funcionamiento en Segundo Plano

*   Una vez que Tempodel está configurado y el acceso directo `TempoDel_Inicio.vbs` está en la carpeta `Startup`, el programa `tempodel_checker.py` se ejecutará automáticamente cada vez que inicies sesión en Windows.
*   Este proceso en segundo plano comprobará periódicamente el archivo `schedule.json` y eliminará los archivos y carpetas que hayan superado su fecha de eliminación programada.
*   La actividad del proceso en segundo plano se registrará en el archivo `tempodel_checker.log`, que puedes consultar para verificar su funcionamiento o para diagnosticar posibles problemas.

## Archivos Principales

*   `tempodel_gui.py`: El script principal que contiene la interfaz gráfica.
*   `tempodel_checker.py`: El script que se ejecuta en segundo plano para comprobar y borrar archivos.
*   `schedule.json`: Un archivo JSON que almacena la lista de archivos y carpetas programados para borrar, junto con sus fechas de eliminación.
*   `tempodel_install_Cascading.reg`: Un archivo de registro que añade las opciones de Tempodel al menú contextual del Explorador de Windows.
*   `tempodel_uninstall_FINAL.reg`: Un archivo de registro que elimina las opciones de Tempodel del menú contextual.
*   `TempoDel_Inicio.vbs`: Acceso directo a TempoDelbackground.vbs, el cual crea un proceso en segundo plano para ejecutar el checker de borrado en Python al iniciar sesión.
*   `icon.ico`: El archivo del icono que se utiliza para la interfaz y el menú contextual (opcional).
*   `README.md`: Este archivo, que proporciona información sobre el programa.

## Notas Importantes

*   **Eliminación Permanente:** Tempodel elimina los archivos y carpetas de forma permanente, sin enviarlos a la Papelera de Reciclaje. Ten cuidado al programar la eliminación de elementos importantes.
*   **Bloqueos:** Si un archivo está en uso por otra aplicación, es posible que Tempodel no pueda eliminarlo. En este caso, el programa intentará eliminar el archivo en la siguiente comprobación.
*   **Logging:** Consulta el archivo `tempodel_checker.log` para verificar que el programa se está ejecutando correctamente y para identificar posibles errores.

## Desinstalación

1.  Ejecuta `tempodel_uninstall_FINAL.reg` (con privilegios de administrador) para quitar las opciones del menú contextual.
2.  Elimina el acceso directo `TempoDel_Inicio.vbs` del directorio de inicio:
    `C:\Users\TuNombreDeUsuario\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`
3.  Elimina la carpeta donde guardaste los archivos de Tempodel.

## Créditos

Tempodel fue creado por klinsec utilizando Python 3.10 y la biblioteca Tkinter.