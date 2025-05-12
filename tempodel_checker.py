import json
import os
import shutil
import time
import datetime
import sys
import ctypes
import traceback # Para logging de errores más detallado

# --- Constantes y Configuración ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_FILE = os.path.join(SCRIPT_DIR, "schedule.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "tempodel_checker.log")
# Intervalo de comprobación DENTRO del script
CHECK_INTERVAL_SECONDS_INTERNAL = 1 # Comprobar cada 5 minutos (ajusta según necesidad)

# --- Funciones de Log ---
def log_message(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding='utf-8') as f:
            f.write(f"{timestamp} - {message}\n")
    except Exception as e:
        print(f"Error escribiendo al log: {e}")

# --- Funciones de Gestión del Schedule (COPIADAS de la versión anterior, SIN CAMBIOS) ---
# ... (load_schedule, save_schedule) ...
def load_schedule():
    lock_file = SCHEDULE_FILE + ".lock"
    schedule = []
    try:
        for _ in range(10):
            if not os.path.exists(lock_file): break
            time.sleep(0.2)
        lock_created = False
        if not os.path.exists(lock_file):
            try:
                with open(lock_file, 'w') as lf: lf.write(f"checker_load_{os.getpid()}")
                lock_created = True
            except IOError: log_message("WARN: No se pudo crear lock al cargar.")
        if os.path.exists(SCHEDULE_FILE):
            try:
                with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f: loaded_data = json.load(f)
                if isinstance(loaded_data, list):
                     schedule = [item for item in loaded_data if isinstance(item, dict) and all(k in item for k in ('path', 'delete_at', 'is_dir'))]
                     if len(schedule) != len(loaded_data): log_message("WARN: Items malformados eliminados al cargar schedule.")
                else:
                    log_message("ERROR: schedule.json no contiene lista valida. Usando vacia.")
                    schedule = []
            except (json.JSONDecodeError, IOError, TypeError) as e:
                log_message(f"ERROR: Cargando schedule ({SCHEDULE_FILE}): {e}. Usando vacia.")
                save_schedule([])
                schedule = []
        else: schedule = []
    except Exception as e:
        log_message(f"ERROR: Excepcion inesperada en load_schedule: {e}\n{traceback.format_exc()}")
        schedule = []
    finally:
        if lock_created and os.path.exists(lock_file):
            try: os.remove(lock_file)
            except OSError: log_message("WARN: No se pudo eliminar lock al cargar.")
    return schedule

def save_schedule(schedule):
    lock_file = SCHEDULE_FILE + ".lock"
    try:
        for _ in range(10):
            if not os.path.exists(lock_file): break
            time.sleep(0.2)
        lock_created = False
        if not os.path.exists(lock_file):
             try:
                 with open(lock_file, 'w') as lf: lf.write(f"checker_save_{os.getpid()}")
                 lock_created = True
             except IOError: log_message("WARN: No se pudo crear lock al guardar.")
        try:
            valid_schedule = [item for item in schedule if isinstance(item, dict) and all(k in item for k in ('path', 'delete_at', 'is_dir')) and isinstance(item.get('path'), str)]
            temp_schedule_path = SCHEDULE_FILE + ".tmp"
            with open(temp_schedule_path, 'w', encoding='utf-8') as f: json.dump(valid_schedule, f, indent=4, ensure_ascii=False)
            shutil.move(temp_schedule_path, SCHEDULE_FILE)
        except (IOError, TypeError, OSError) as e:
            log_message(f"ERROR: Guardando schedule ({SCHEDULE_FILE}): {e}")
            if os.path.exists(temp_schedule_path):
                 try: os.remove(temp_schedule_path)
                 except OSError: pass
    except Exception as e:
        log_message(f"ERROR: Excepcion inesperada en save_schedule: {e}\n{traceback.format_exc()}")
    finally:
        if lock_created and os.path.exists(lock_file):
             try: os.remove(lock_file)
             except OSError: log_message("WARN: No se pudo eliminar lock al guardar.")

# --- Lógica del Checker (COPIADA de la versión anterior, SIN CAMBIOS) ---
# ... (check_and_delete) ...
def check_and_delete():
    log_message("--- Iniciando comprobacion de schedule ---")
    schedule = load_schedule()
    if not schedule:
        log_message("Schedule vacio o no cargado. Finalizando comprobacion.")
        return
    current_time = time.time()
    items_to_keep = []
    items_processed_paths = set()
    log_message(f"Items en schedule: {len(schedule)}")
    items_due = 0

    for item in schedule:
        if not all(k in item for k in ('path', 'delete_at', 'is_dir')):
            log_message(f"WARN: Omitiendo item malformado: {item}")
            continue
        path_to_process = os.path.normpath(item['path'])
        is_dir = item['is_dir']
        delete_time = item.get('delete_at', 0)
        if path_to_process in items_processed_paths: continue

        if current_time >= delete_time:
            items_due += 1
            log_message(f"INFO: Tiempo cumplido para: '{path_to_process}' (Programado: {datetime.datetime.fromtimestamp(delete_time)})")
            items_processed_paths.add(path_to_process)
            try:
                if os.path.exists(path_to_process):
                    if is_dir:
                        log_message(f"INFO: Intentando borrar CARPETA: {path_to_process}")
                        shutil.rmtree(path_to_process)
                        log_message(f"SUCCESS: Carpeta borrada: {path_to_process}")
                    else:
                        log_message(f"INFO: Intentando borrar ARCHIVO: {path_to_process}")
                        os.remove(path_to_process)
                        log_message(f"SUCCESS: Archivo borrado: {path_to_process}")
                else: log_message(f"INFO: Elemento ya no existia: {path_to_process}")
            except OSError as e: log_message(f"ERROR: BORRANDO {path_to_process}: {e}")
            except Exception as e: log_message(f"ERROR: INESPERADO procesando {path_to_process}: {e}\n{traceback.format_exc()}")
        else:
            if os.path.exists(path_to_process): items_to_keep.append(item)
            else:
                log_message(f"WARN: Elemento no encontrado pero no caducado (se quitara de lista): {path_to_process}")
                items_processed_paths.add(path_to_process)

    log_message(f"Items procesados (borrados o no encontrados): {len(items_processed_paths)}. Items caducados encontrados: {items_due}")

    if items_processed_paths:
         log_message(f"INFO: Actualizando schedule.json. Items a mantener: {len(items_to_keep)}")
         save_schedule(items_to_keep)
    else: log_message("INFO: No hubo cambios en el schedule en esta ejecucion.")
    log_message("--- Finalizada comprobacion de schedule ---")


# --- Punto de Entrada Principal del Checker (MODIFICADO) ---
if __name__ == "__main__":
    log_message(f"=== tempodel_checker.py iniciado (PID: {os.getpid()}) - Modo Continuo ===")
    log_message(f"Intervalo de comprobacion: {CHECK_INTERVAL_SECONDS_INTERNAL} segundos")

    while True: # Bucle infinito
        log_message("...") # Mensaje periódico para saber que sigue vivo
        try:
            # Ejecutar la lógica de comprobación y borrado
            check_and_delete()

        except Exception as e:
            # Capturar cualquier error inesperado DURANTE la ejecución de check_and_delete
            # para evitar que el bucle principal se rompa.
            log_message(f"¡¡¡ ERROR CRITICO en el bucle principal de check_and_delete !!!")
            log_message(f"Error: {e}")
            log_message(f"Traceback:\n{traceback.format_exc()}")
            # Considerar una pausa más larga después de un error crítico
            time.sleep(CHECK_INTERVAL_SECONDS_INTERNAL * 2) # Esperar el doble antes de reintentar

        # Esperar el intervalo definido antes de la próxima comprobación
        try:
            time.sleep(CHECK_INTERVAL_SECONDS_INTERNAL)
        except KeyboardInterrupt:
             # Permitir salir con Ctrl+C si se ejecuta manualmente en consola
             log_message("KeyboardInterrupt recibido. Saliendo...")
             break
        except Exception as e:
             log_message(f"Error durante time.sleep: {e}. Saliendo...")
             break

    log_message(f"=== tempodel_checker.py finalizado (PID: {os.getpid()}) ===")
    # Ya no usamos sys.exit(0) aquí porque el bucle es la vida del script