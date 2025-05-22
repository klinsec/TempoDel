import json
import os
import shutil
import time
import datetime
import sys
import traceback # Para logging de errores más detallado en consola

# --- Constantes y Configuración ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_FILE = os.path.join(SCRIPT_DIR, "schedule.json")
CHECK_INTERVAL_SECONDS_INTERNAL = 5

def log_message(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - {message}")

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
                     # DEBUG LOGGING:
                     for i, item_debug in enumerate(schedule):
                         if item_debug.get("periodic"):
                             log_message(f"DEBUG LOAD (Checker): Item {i} ({item_debug.get('path')}) es periodico. original_duration_seconds: {item_debug.get('original_duration_seconds')}, Tipo: {type(item_debug.get('original_duration_seconds'))}")
                     # FIN DEBUG
                     if len(schedule) != len(loaded_data): log_message("WARN: Items malformados eliminados al cargar schedule.")
                else:
                    log_message("ERROR: schedule.json no contiene lista valida. Usando vacia.")
                    schedule = []
            except (json.JSONDecodeError, IOError, TypeError) as e:
                log_message(f"ERROR: Cargando schedule ({SCHEDULE_FILE}): {e}. Usando vacia.")
                save_schedule([])
                schedule = []
        else: 
            log_message("INFO: schedule.json no existe. Se creara uno vacio si es necesario.")
            schedule = []
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

def check_and_delete():
    log_message("--- Iniciando comprobacion de schedule ---")
    schedule = load_schedule()
    if not schedule:
        log_message("Schedule vacio o no cargado. Finalizando comprobacion.")
        return

    current_time = time.time()
    items_to_keep = []
    items_processed_this_run = False
    log_message(f"Items en schedule: {len(schedule)}")
    items_due_count = 0

    for item_original in schedule: # Usar item_original para claridad, item es el que se modifica
        item = item_original.copy() # Trabajar con una copia superficial para modificar delete_at sin afectar el schedule original durante la iteración si algo sale mal antes de items_to_keep

        if not all(k in item for k in ('path', 'delete_at', 'is_dir')):
            log_message(f"WARN: Omitiendo item malformado: {item}")
            continue

        path_to_process = os.path.normpath(item['path'])
        is_dir = item['is_dir']
        delete_time = item.get('delete_at', 0)
        is_periodic = item.get('periodic', False)
        original_duration = item.get('original_duration_seconds', None)
        # Asegurarse de que original_duration es un número si existe
        if original_duration is not None:
            try:
                original_duration = float(original_duration)
                if original_duration <= 0: # Duración debe ser positiva
                    original_duration = None 
            except ValueError:
                original_duration = None

        processed_item_this_cycle = False # Flag para saber si este item fue procesado (borrado o intento)

        if current_time >= delete_time:
            items_due_count += 1
            items_processed_this_run = True
            processed_item_this_cycle = True 

            log_message(f"INFO: Tiempo cumplido para: '{path_to_process}' (Programado: {datetime.datetime.fromtimestamp(delete_time)})")
            log_message(f"       Is Periodic: {is_periodic}, Original Duration: {original_duration} seconds")

            if not os.path.exists(path_to_process):
                log_message(f"INFO: Elemento '{path_to_process}' ya no existia.")
                if is_periodic:
                    # Si es periódico y no existe, no lo reprogramamos, se elimina del schedule.
                    log_message(f"INFO: Elemento periodico '{path_to_process}' no encontrado. Se eliminara del schedule.")
                # No se añade a items_to_keep, por lo que se eliminará del schedule.
                continue # Pasa al siguiente item del schedule

            action_successful = False
            try:
                if is_periodic:
                    if original_duration is None:
                        log_message(f"ERROR: Item periodico '{path_to_process}' no tiene 'original_duration_seconds' valida. No se puede reprogramar. Se tratara como no periodico.")
                        is_periodic = False # Forzar no periódico para este ciclo si no hay duración

                    if is_dir:
                        log_message(f"INFO: Procesando CARPETA PERIODICA: {path_to_process}. Eliminando contenido.")
                        content_deleted_count = 0
                        # ... (lógica de borrado de contenido, como antes) ...
                        for entry_name in os.listdir(path_to_process):
                            entry_path = os.path.join(path_to_process, entry_name)
                            try:
                                if os.path.isfile(entry_path) or os.path.islink(entry_path):
                                    os.unlink(entry_path)
                                    content_deleted_count +=1
                                elif os.path.isdir(entry_path):
                                    shutil.rmtree(entry_path)
                                    content_deleted_count +=1
                            except Exception as e_content:
                                log_message(f"ERROR: BORRANDO CONTENIDO '{entry_path}' de '{path_to_process}': {e_content}")
                        log_message(f"INFO: {content_deleted_count} elementos eliminados del contenido de '{path_to_process}'.")
                        action_successful = True # Asumimos éxito si no hay excepciones graves
                        
                        if is_periodic: # Re-chequear 'is_periodic' por si se cambió arriba
                            item['delete_at'] = time.time() + original_duration
                            items_to_keep.append(item) # Guardar el item modificado
                            log_message(f"SUCCESS: Contenido de carpeta '{path_to_process}' procesado. Reprogramado para {datetime.datetime.fromtimestamp(item['delete_at'])}.")
                        else: # Se trató como no periódico
                             log_message(f"INFO: Carpeta '{path_to_process}' (contenido) procesada. No se reprograma (tratada como no periodica).")
                    
                    else: # Es un archivo periódico
                        log_message(f"INFO: Intentando borrar ARCHIVO PERIODICO: {path_to_process}")
                        os.remove(path_to_process)
                        action_successful = True
                        log_message(f"SUCCESS: Archivo periodico borrado: {path_to_process}")

                        if is_periodic: # Re-chequear
                            item['delete_at'] = time.time() + original_duration
                            items_to_keep.append(item) # Guardar el item modificado
                            log_message(f"SUCCESS: Archivo '{path_to_process}' reprogramado para {datetime.datetime.fromtimestamp(item['delete_at'])}.")
                        else: # Se trató como no periódico
                             log_message(f"INFO: Archivo '{path_to_process}' procesado. No se reprograma (tratado como no periodico).")

                else: # No es periódico
                    if is_dir:
                        log_message(f"INFO: Intentando borrar CARPETA (no periodica): {path_to_process}")
                        shutil.rmtree(path_to_process)
                        action_successful = True
                        log_message(f"SUCCESS: Carpeta borrada: {path_to_process}")
                    else:
                        log_message(f"INFO: Intentando borrar ARCHIVO (no periodico): {path_to_process}")
                        os.remove(path_to_process)
                        action_successful = True
                        log_message(f"SUCCESS: Archivo borrado: {path_to_process}")
                
            except OSError as e:
                log_message(f"ERROR: BORRANDO '{path_to_process}': {e}")
                # Si hay error, no se añade a items_to_keep, por lo que se eliminará
            except Exception as e:
                log_message(f"ERROR: INESPERADO procesando '{path_to_process}': {e}\n{traceback.format_exc()}")
                # Si hay error, no se añade a items_to_keep

            if is_periodic and not action_successful:
                 log_message(f"WARN: Item periodico '{path_to_process}' tuvo un error durante el borrado/procesamiento. No se reprogramara ni mantendra.")
            elif is_periodic and action_successful and not any(id(x) == id(item) for x in items_to_keep):
                 # Esto es un chequeo extra por si se me escapa algo y no se añadió a items_to_keep
                 log_message(f"CRITICAL WARN: Item periodico '{path_to_process}' procesado exitosamente PERO NO AÑADIDO A items_to_keep. Original Duration: {original_duration}. Esto es un bug.")


        else: # No es tiempo de borrar (current_time < delete_time)
            # Si el path existe o es periódico (incluso si no existe aun, podría crearse luego), mantenerlo.
            if os.path.exists(path_to_process):
                items_to_keep.append(item_original) # Mantener el item original, no la copia
            elif is_periodic:
                items_to_keep.append(item_original) # Mantener el item original
                log_message(f"INFO: Elemento periodico '{path_to_process}' no encontrado, pero se mantiene en schedule por ser periodico (no es su hora).")
            else: # No es periódico y no existe
                log_message(f"WARN: Elemento no encontrado y no periodico (se quitara de lista): {path_to_process}")
                items_processed_this_run = True

    log_message(f"Items caducados encontrados en esta ejecucion: {items_due_count}")
    log_message(f"Total items a mantener/reprogramar: {len(items_to_keep)}")


    # Comparamos la lista original con la nueva lista de items a mantener
    # para decidir si es necesario guardar. Un cambio en delete_at también es un cambio.
    # Esto es complejo. Una forma más simple es guardar si `items_processed_this_run` es True,
    # o si la cantidad de items cambió.
    # Para ser más preciso: guardar si `items_processed_this_run` es True (algo se borró o intentó borrar),
    # O si la lista `items_to_keep` es diferente en contenido o tamaño a la `schedule` original.
    # La comparación directa de listas de diccionarios puede ser costosa.
    # Guardaremos si `items_processed_this_run` es true O si el número de items cambió.
    # Si un item solo se reprogramó, `items_processed_this_run` será True.
    
    needs_saving = False
    if len(schedule) != len(items_to_keep):
        needs_saving = True
    else: # Mismo número de items, verificar si alguno cambió (ej. delete_at)
        # Esto requiere comparar los items uno a uno, puede ser complejo si el orden cambia.
        # Por ahora, si items_processed_this_run es True, asumimos que algo cambió y guardamos.
        # Esto podría llevar a guardados innecesarios si un item "due" no existía y no era periódico.
        # Mejor: if items_processed_this_run: save
        pass


    if items_processed_this_run : # Si se procesó algún item "due" (borrado, reprogramado, o error)
         log_message(f"INFO: Actualizando schedule.json porque se procesaron items 'due'. Items a mantener/reprogramados: {len(items_to_keep)}")
         save_schedule(items_to_keep)
    elif len(schedule) != len(items_to_keep): # Si se eliminó un item no "due" pero no existente y no periódico
        log_message(f"INFO: Actualizando schedule.json porque items no existentes y no periodicos fueron eliminados. Items a mantener: {len(items_to_keep)}")
        save_schedule(items_to_keep)
    else:
         log_message("INFO: No hubo cambios en el schedule que requieran guardado en esta ejecucion.")
    log_message("--- Finalizada comprobacion de schedule ---")


# --- Punto de Entrada Principal del Checker ---
if __name__ == "__main__":
    log_message(f"=== tempodel_checker.py iniciado (PID: {os.getpid()}) - Modo Continuo ===")
    log_message(f"Intervalo de comprobacion: {CHECK_INTERVAL_SECONDS_INTERNAL} segundos")

    try:
        initial_schedule = load_schedule()
        cleaned_schedule = []
        made_changes_init = False
        for item_init in initial_schedule:
            if os.path.exists(item_init['path']) or item_init.get('periodic', False):
                cleaned_schedule.append(item_init)
            else:
                log_message(f"INFO (arranque): Eliminando item no existente y no periódico: {item_init['path']}")
                made_changes_init = True
        if made_changes_init:
            save_schedule(cleaned_schedule)
            log_message("INFO (arranque): Schedule limpiado de items obsoletos no periódicos.")
    except Exception as e_init_clean:
        log_message(f"ERROR (arranque): No se pudo limpiar el schedule: {e_init_clean}")

    while True:
        try:
            check_and_delete()
        except Exception as e:
            log_message(f"¡¡¡ ERROR CRITICO en el bucle principal de check_and_delete !!!")
            log_message(f"Error: {e}")
            log_message(f"Traceback:\n{traceback.format_exc()}")
            time.sleep(CHECK_INTERVAL_SECONDS_INTERNAL * 5)
        try:
            time.sleep(CHECK_INTERVAL_SECONDS_INTERNAL)
        except KeyboardInterrupt:
             log_message("KeyboardInterrupt recibido. Saliendo...")
             break
        except Exception as e:
             log_message(f"Error durante time.sleep: {e}. Saliendo...")
             break
    log_message(f"=== tempodel_checker.py finalizado (PID: {os.getpid()}) ===")