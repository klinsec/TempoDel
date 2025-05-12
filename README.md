# Tempodel - Programador de Borrado de Archivos y Carpetas

## Descripción

Tempodel es una herramienta en Python para programar la eliminación automática de archivos y carpetas en Windows.

## Características Principales

*   Interfaz gráfica para gestionar la programación.
*   Integración con el menú contextual del Explorador de Windows.
*   Borrador en segundo plano.
*   Programación flexible (segundos a días).
*   Gestión de multi-selección.
*   Logging de actividad.

## Instalación

1.  **Requisitos:** Python 3.10 instalado.
2.  **Descarga:** Copia todos los archivos del programa a una carpeta (ej: `D:\Tempodel`).
3.  **Menú Contextual:**
    *   Abre `Tempodel_install_template.reg` con un editor de texto.
    *   Reemplaza:
        *   `"%PYTHON_PATH%"` con la ruta a `pythonw.exe` (ej: `"C:\\Python310\\pythonw.exe"`).
        *   `"%SCRIPT_PATH%"` con la ruta a la carpeta de Tempodel (ej: `"D:\\Tempodel"`).
        *   `"%ICON_PATH%"` con la ruta a `icon.ico`.
        *   Usa doble barra invertida (`\\`) en las rutas.
        *   Guarda como `tempodel_install.reg`.
    *   Ejecuta `tempodel_install.reg` como administrador.
4.  **Ejecución al Inicio:**
    *   Mueve `TempoDel_Inicio.vbs` a: `C:\Users\TuUsuario\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`
5.  **Desinstalar:** Ejecuta `tempodel_uninstall.reg` como administrador.

## Uso

*   **Interfaz:** Ejecuta `TempoDel.vbs` para gestionar la lista de borrado.
*   **Menú Contextual:** Clic derecho en archivos/carpetas -> Tempodel -> elige una opción de tiempo o "Configurar borrado...".

### Interfaz Gráfica

*   Añadir/Modificar/Quitar elementos de la lista.
*   Especificar tiempo de borrado en días/horas/minutos/segundos.

### Menú Contextual

*   Programar borrado rápido (1, 3, 7, 30 días).
*   Abrir la interfaz para configuración personalizada.

### Segundo Plano

*   `tempodel_checker.py` se ejecuta al iniciar sesión y borra archivos programados.
*   Registro de actividad en `tempodel_checker.log`.

## Archivos Principales

*   `tempodel_gui.py`: Interfaz gráfica.
*   `tempodel_checker.py`: Borrado en segundo plano.
*   `schedule.json`: Lista de borrado.
*   `Tempodel_install_template.reg`: Plantilla para instalar el menú contextual.
*   `tempodel_install.reg`: Archivo de registro *modificado* para la instalación.
*   `tempodel_uninstall.reg`: Desinstalador del menú contextual.
*   `TempoDel_Inicio.vbs`: Lanza el checker al inicio.
*   `icon.ico`: Icono.
*   `README.md`: Este archivo.

## Notas

*   La eliminación es **permanente**.
*   Los archivos en uso podrían no borrarse hasta la próxima comprobación.
*   Revisa `tempodel_checker.log` para errores.

## Desinstalación

1.  Ejecuta `tempodel_uninstall.reg` (admin).
2.  Elimina `TempoDel_Inicio.vbs` de la carpeta `Startup`.
3.  Elimina la carpeta de Tempodel.

## Créditos

klinsec

## Licencia

MIT
