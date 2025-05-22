import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import json
import os
import shutil
import time
import datetime
import threading
import sys
from pathlib import Path
import tempfile
import traceback

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_FILE = os.path.join(SCRIPT_DIR, "schedule.json")
ICON_FILE = os.path.join(SCRIPT_DIR, "icon.ico")
CHECK_INTERVAL_SECONDS = 60
app = None
checker_thread = None

TEMP_DIR = tempfile.gettempdir()
CONFIGURE_LOCK_FILE = os.path.join(TEMP_DIR, "tempodel_configure_multiselect.lock")
PENDING_PATHS_FILE = os.path.join(TEMP_DIR, "tempodel_pending_paths_multiselect.txt")
MULTI_SELECT_WAIT_MS = 600

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
                with open(lock_file, 'w') as lf: lf.write(f"gui_load_{os.getpid()}")
                lock_created = True
            except IOError: pass
        if os.path.exists(SCHEDULE_FILE):
            try:
                with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f: loaded_data = json.load(f)
                if isinstance(loaded_data, list):
                     schedule = [item for item in loaded_data if isinstance(item, dict) and all(k in item for k in ('path', 'delete_at', 'is_dir'))]
                     # DEBUG LOGGING:
                     for i, item_debug in enumerate(schedule):
                         if item_debug.get("periodic"):
                             print(f"DEBUG LOAD (GUI): Item {i} ({item_debug.get('path')}) es periodico. original_duration_seconds: {item_debug.get('original_duration_seconds')}, Tipo: {type(item_debug.get('original_duration_seconds'))}")
                     # FIN DEBUG
                     if len(schedule) != len(loaded_data): print("WARN: Items malformados eliminados al cargar schedule.")
                else:
                    print("ERROR: schedule.json no contiene lista valida. Usando lista vacia.")
                    schedule = []
            except (json.JSONDecodeError, IOError, TypeError) as e:
                print(f"ERROR: Cargando schedule ({SCHEDULE_FILE}): {e}. Creando/usando lista vacia.")
                save_schedule([])
                schedule = []
        else: schedule = []
    except Exception as e:
        print(f"ERROR: Excepcion inesperada en load_schedule: {e}")
        traceback.print_exc()
        schedule = []
    finally:
        if lock_created and os.path.exists(lock_file):
            try: os.remove(lock_file)
            except OSError: pass
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
                 with open(lock_file, 'w') as lf: lf.write(f"gui_save_{os.getpid()}")
                 lock_created = True
             except IOError: pass
        try:
            valid_schedule = [item for item in schedule if isinstance(item, dict) and all(k in item for k in ('path', 'delete_at', 'is_dir')) and isinstance(item.get('path'), str)]
            temp_schedule_path = SCHEDULE_FILE + ".tmp"
            with open(temp_schedule_path, 'w', encoding='utf-8') as f: json.dump(valid_schedule, f, indent=4, ensure_ascii=False)
            shutil.move(temp_schedule_path, SCHEDULE_FILE)
        except (IOError, TypeError, OSError) as e:
            print(f"ERROR: Guardando schedule ({SCHEDULE_FILE}): {e}")
            if app and app.root.winfo_exists(): app.root.after(0, lambda: messagebox.showerror("Error", f"No se pudo guardar la lista: {e}"))
            if os.path.exists(temp_schedule_path):
                 try: os.remove(temp_schedule_path)
                 except OSError: pass
    except Exception as e:
        print(f"ERROR: Excepcion inesperada en save_schedule: {e}")
        traceback.print_exc()
    finally:
        if lock_created and os.path.exists(lock_file):
             try: os.remove(lock_file)
             except OSError: pass

def add_item_to_schedule(item_path, delete_timestamp, is_periodic_item=False, duration_for_periodic=None):
    # Determinar is_dir. Para paths no existentes, esto será False.
    # La 'is_dir_hint' del diálogo de configuración es crucial si el path no existe y DEBE ser carpeta.
    # Esta función actualmente no recibe ese hint explícito, confía en os.path.isdir().
    # Esto es una limitación si se añade una carpeta periódica que aún no existe.
    current_is_dir = os.path.isdir(item_path)

    if not os.path.exists(item_path):
        if not is_periodic_item: # Solo mostrar advertencia si no es periódico y no existe
            print(f"WARN: Path no existe al añadir/actualizar item no periódico: {item_path}")
            # No mostrar messagebox aquí, el diálogo ya terminó. El caller (_configure_items_dialog) podría.
            # return False # No retornamos False aquí para permitir que items periódicos se añadan.
        else:
             print(f"INFO: Path para item periódico '{item_path}' no existe actualmente, pero se añadirá/actualizará.")
    
    schedule = load_schedule()
    normalized_path = os.path.normpath(item_path)
    
    new_item_data = {
        "path": normalized_path,
        "delete_at": float(delete_timestamp),
        "is_dir": current_is_dir, # Usar el estado actual. Si no existe, será False.
        "periodic": is_periodic_item
    }

    if is_periodic_item:
        if duration_for_periodic is not None and float(duration_for_periodic) > 0:
            new_item_data["original_duration_seconds"] = float(duration_for_periodic)
        else:
            # Si es periódico pero no se da una duración válida, no tiene sentido. Lo hacemos no periódico.
            print(f"WARN: Item '{item_path}' marcado como periodico pero sin original_duration_seconds valido ({duration_for_periodic}). Se tratara como no periodico.")
            new_item_data["periodic"] = False
            # No necesitamos explícitamente del new_item_data["original_duration_seconds"] aquí
            # porque no se añadió si duration_for_periodic no era válido.
    # Si no es periódico, nos aseguramos que "original_duration_seconds" no esté presente.
    # Esto se maneja al construir new_item_data y al actualizar/reemplazar.

    existing_item_index = -1
    for i, item_s in enumerate(schedule):
        if 'path' in item_s and os.path.normpath(item_s['path']) == normalized_path:
            existing_item_index = i
            break
    
    if existing_item_index != -1:
        # Para actualizar, es más seguro reemplazar el diccionario completo o manejar las claves explícitamente.
        # Si el item deja de ser periódico, 'original_duration_seconds' debe ser removido.
        # Si se vuelve periódico, 'original_duration_seconds' debe ser añadido/actualizado.
        
        # schedule[existing_item_index] = new_item_data # Reemplazo directo
        # O, si queremos ser más cuidadosos con .update():
        if not new_item_data.get("periodic") and "original_duration_seconds" in schedule[existing_item_index]:
            del schedule[existing_item_index]["original_duration_seconds"]
        schedule[existing_item_index].update(new_item_data)

        print(f"'{os.path.basename(normalized_path)}' actualizado. Periódico: {new_item_data['periodic']}. Nuevo borrado: {datetime.datetime.fromtimestamp(new_item_data['delete_at'])}")
    else:
        schedule.append(new_item_data)
        print(f"'{os.path.basename(normalized_path)}' añadido. Periódico: {new_item_data['periodic']}. Borrado: {datetime.datetime.fromtimestamp(new_item_data['delete_at'])}")
    
    save_schedule(schedule)
    return True


def remove_item_from_schedule(item_path):
    schedule = load_schedule()
    normalized_path_to_remove = os.path.normpath(item_path)
    new_schedule = [item for item in schedule if 'path' not in item or os.path.normpath(item['path']) != normalized_path_to_remove]
    if len(schedule) != len(new_schedule):
        save_schedule(new_schedule)
        print(f"Eliminado de la lista: {normalized_path_to_remove}")
        return True
    else:
        print(f"Intento de eliminar, pero no se encontro: {normalized_path_to_remove}")
        return False

# --- Lógica del Background Checker (GUI) ---
# Esta es una copia de la lógica del checker autónomo, adaptada para la GUI
def check_and_delete(): # Checker de la GUI
    global SCHEDULE_FILE, CHECK_INTERVAL_SECONDS, app, checker_thread
    if not (app and app.root.winfo_exists()): # Si la GUI ya no existe, el checker no debe correr
        print("(GUI Checker) Abortando, la ventana principal no existe.")
        return

    print(f"{datetime.datetime.now()}: (GUI Checker) Comprobando schedule en {SCHEDULE_FILE}...")
    
    schedule = load_schedule() # Usa la función load_schedule global
    current_time = time.time()
    items_to_keep = []
    items_processed_this_run = False
    items_due_count = 0


    for item_original in schedule:
        item = item_original.copy()

        if not all(k in item for k in ('path', 'delete_at', 'is_dir')): continue
        
        path_to_process = os.path.normpath(item['path'])
        is_dir = item['is_dir'] # is_dir del schedule, podría ser stale si el tipo cambió
        delete_time = item.get('delete_at', 0)
        is_periodic = item.get('periodic', False)
        original_duration = item.get('original_duration_seconds', None)
        if original_duration is not None:
            try:
                original_duration = float(original_duration)
                if original_duration <= 0: original_duration = None
            except ValueError: original_duration = None
        
        processed_item_this_cycle = False

        if current_time >= delete_time:
            items_due_count += 1
            items_processed_this_run = True
            processed_item_this_cycle = True

            print(f"(GUI Checker) Tiempo cumplido para: {path_to_process}")
            print(f"              Is Periodic: {is_periodic}, Original Duration: {original_duration}s")

            if not os.path.exists(path_to_process):
                print(f"(GUI Checker) Elemento '{path_to_process}' ya no existia.")
                if is_periodic:
                    print(f"(GUI Checker) Elemento periodico '{path_to_process}' no encontrado. Se eliminara del schedule.")
                continue

            action_successful = False
            try:
                # Re-evaluar is_dir en el momento del borrado
                current_is_dir_on_disk = os.path.isdir(path_to_process)

                if is_periodic:
                    if original_duration is None:
                        print(f"(GUI Checker) ERROR: Item periodico '{path_to_process}' sin 'original_duration_seconds' valida. Tratado como no periodico.")
                        is_periodic = False 
                    
                    if current_is_dir_on_disk: # Usar el estado actual del disco para 'is_dir'
                        print(f"(GUI Checker) Procesando CARPETA PERIODICA: {path_to_process}. Eliminando contenido.")
                        # ... (borrado de contenido, igual que en checker autónomo) ...
                        for entry_name in os.listdir(path_to_process):
                            entry_path = os.path.join(path_to_process, entry_name)
                            try:
                                if os.path.isfile(entry_path) or os.path.islink(entry_path): os.unlink(entry_path)
                                elif os.path.isdir(entry_path): shutil.rmtree(entry_path)
                            except Exception as e_content:
                                print(f"(GUI Checker) ERROR borrando contenido '{entry_path}': {e_content}")
                                if app and app.root.winfo_exists(): app.root.after(0, lambda p=entry_path, err=e_content: messagebox.showerror("Error Borrado Contenido", f"No se pudo borrar:\n{p}\n\nError: {err}", parent=app.root))
                        action_successful = True
                        
                        if is_periodic:
                            item['delete_at'] = time.time() + original_duration
                            items_to_keep.append(item)
                            print(f"(GUI Checker) Carpeta '{path_to_process}' (contenido) reprogramada para {datetime.datetime.fromtimestamp(item['delete_at'])}.")
                    
                    else: # Archivo periódico (o path que no es directorio)
                        print(f"(GUI Checker) Intentando borrar ARCHIVO PERIODICO: {path_to_process}")
                        os.remove(path_to_process)
                        action_successful = True
                        print(f"(GUI Checker) Archivo periodico borrado: {path_to_process}")
                        if is_periodic:
                            item['delete_at'] = time.time() + original_duration
                            items_to_keep.append(item)
                            print(f"(GUI Checker) Archivo '{path_to_process}' reprogramado para {datetime.datetime.fromtimestamp(item['delete_at'])}.")
                
                else: # No periódico
                    if current_is_dir_on_disk:
                        print(f"(GUI Checker) Intentando borrar CARPETA (no periodica): {path_to_process}")
                        shutil.rmtree(path_to_process)
                        action_successful = True
                        print(f"(GUI Checker) Carpeta borrada: {path_to_process}")
                    else:
                        print(f"(GUI Checker) Intentando borrar ARCHIVO (no periodico): {path_to_process}")
                        os.remove(path_to_process)
                        action_successful = True
                        print(f"(GUI Checker) Archivo borrado: {path_to_process}")

            except OSError as e:
                print(f"(GUI Checker) Error borrando {path_to_process}: {e}")
                if app and app.root.winfo_exists(): app.root.after(0, lambda p=path_to_process, err=e: messagebox.showerror("Error de Borrado", f"No se pudo borrar:\n{p}\n\nError: {err}", parent=app.root))
            except Exception as e:
                print(f"(GUI Checker) Error inesperado procesando {path_to_process}: {e}")
                traceback.print_exc()
                if app and app.root.winfo_exists(): app.root.after(0, lambda p=path_to_process, err=e: messagebox.showerror("Error Inesperado", f"Error procesando:\n{p}\n\nError: {err}", parent=app.root))
            
            if is_periodic and not action_successful:
                 print(f"(GUI Checker) WARN: Item periodico '{path_to_process}' tuvo un error durante el borrado/procesamiento. No se reprogramara ni mantendra.")
            elif is_periodic and action_successful and not any(id(x) == id(item) for x in items_to_keep):
                 print(f"(GUI Checker) CRITICAL WARN: Item periodico '{path_to_process}' procesado exitosamente PERO NO AÑADIDO A items_to_keep. Original Duration: {original_duration}. Esto es un bug.")
        
        else: # No es tiempo de borrar
            if os.path.exists(path_to_process) or is_periodic:
                items_to_keep.append(item_original)
            else:
                print(f"(GUI Checker) Elemento no encontrado y no periodico (se quitara): {path_to_process}")
                items_processed_this_run = True

    if items_processed_this_run :
         print(f"(GUI Checker) INFO: Actualizando schedule.json porque se procesaron items 'due'. Items a mantener/reprogramados: {len(items_to_keep)}")
         save_schedule(items_to_keep) # Usa la función save_schedule global
         if app is not None and app.root.winfo_exists(): app.root.after(0, app.refresh_list)
    elif len(schedule) != len(items_to_keep):
        print(f"(GUI Checker) INFO: Actualizando schedule.json porque items no existentes y no periodicos fueron eliminados. Items a mantener: {len(items_to_keep)}")
        save_schedule(items_to_keep)
        if app is not None and app.root.winfo_exists(): app.root.after(0, app.refresh_list)


    if checker_thread is not None and checker_thread.is_alive() and app is not None and app.root.winfo_exists():
         # Asegurarse de que el timer es el del checker de la GUI (check_and_delete de este archivo)
         timer = threading.Timer(CHECK_INTERVAL_SECONDS, check_and_delete)
         timer.daemon = True
         timer.start()
# --- Fin Background Checker (GUI) ---

class TempodelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tempodel - Gestor de Borrado Programado")
        
        if os.path.exists(ICON_FILE):
            try: self.root.iconbitmap(ICON_FILE)
            except Exception as e: print(f"No se pudo cargar el icono '{ICON_FILE}': {e}")
        else:
            print(f"Advertencia: Archivo de icono no encontrado en '{ICON_FILE}'")

        window_width = 800; window_height = 450
        screen_width = root.winfo_screenwidth(); screen_height = root.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2); center_y = int(screen_height/2 - window_height / 2)
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        main_frame = ttk.Frame(root, padding="10"); main_frame.pack(fill=tk.BOTH, expand=True)
        list_frame = ttk.LabelFrame(main_frame, text="Archivos/Carpetas Programados", padding="10"); list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.tree = ttk.Treeview(list_frame, columns=('Tipo', 'Nombre', 'Ubicacion', 'Fecha Borrado', 'Periodico'), show='headings', height=15)
        self.tree.heading('Tipo', text='Tipo'); self.tree.column('Tipo', width=60, anchor=tk.W)
        self.tree.heading('Nombre', text='Nombre'); self.tree.column('Nombre', width=150, anchor=tk.W)
        self.tree.heading('Ubicacion', text='Ubicacion'); self.tree.column('Ubicacion', width=300, anchor=tk.W)
        self.tree.heading('Fecha Borrado', text='Fecha Borrado'); self.tree.column('Fecha Borrado', width=140, anchor=tk.CENTER)
        self.tree.heading('Periodico', text='Periódico'); self.tree.column('Periodico', width=70, anchor=tk.CENTER)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree_item_paths = {}; self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        
        button_frame = ttk.Frame(main_frame, padding="5"); button_frame.pack(fill=tk.X, pady=(5,0))
        style = ttk.Style(); style.configure('TButton', padding=5, font=('Segoe UI', 9))
        add_file_button = ttk.Button(button_frame, text="Añadir Archivo", command=self.add_file, style='TButton'); add_file_button.pack(side=tk.LEFT, padx=5)
        add_folder_button = ttk.Button(button_frame, text="Añadir Carpeta", command=self.add_folder, style='TButton'); add_folder_button.pack(side=tk.LEFT, padx=5)
        self.modify_button = ttk.Button(button_frame, text="Modificar", command=self.modify_selected, style='TButton', state=tk.DISABLED); self.modify_button.pack(side=tk.LEFT, padx=5)
        self.remove_button = ttk.Button(button_frame, text="Quitar", command=self.remove_selected, style='TButton', state=tk.DISABLED); self.remove_button.pack(side=tk.LEFT, padx=5)
        refresh_button = ttk.Button(button_frame, text="Refrescar", command=self.refresh_list, style='TButton'); refresh_button.pack(side=tk.RIGHT, padx=5)
        
        self.refresh_list(); self.update_button_states(); self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def update_button_states(self):
        state = tk.NORMAL if self.tree.selection() else tk.DISABLED
        self.modify_button.config(state=state)
        self.remove_button.config(state=state)

    def on_tree_select(self, event): self.update_button_states()

    def format_item_for_treeview(self, item):
        path = os.path.normpath(item['path'])
        try:
            delete_timestamp = float(item.get('delete_at', 0))
            delete_str = datetime.datetime.fromtimestamp(delete_timestamp).strftime('%Y-%m-%d %H:%M:%S') if delete_timestamp > 0 else "N/A"
        except (ValueError, TypeError, OSError): delete_str = "Fecha Invalida"
        
        kind = "Carpeta" if item.get('is_dir', False) else "Archivo"
        name = os.path.basename(path); parent_dir = os.path.dirname(path)
        periodic_str = "Sí" if item.get('periodic', False) else "No"
        
        return kind, name, parent_dir, delete_str, periodic_str, path

    def refresh_list(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        self.tree_item_paths.clear()
        schedule = load_schedule()
        schedule.sort(key=lambda x: (x.get('delete_at', 0) if x.get('delete_at') is not None else float('inf'))) # Manejar None en delete_at
        
        for item in schedule:
            if not all(k in item for k in ('path', 'delete_at', 'is_dir')): continue
            try:
                 kind, name, parent_dir, delete_str, periodic_str, full_path = self.format_item_for_treeview(item)
                 item_id = self.tree.insert('', tk.END, values=(kind, name, parent_dir, delete_str, periodic_str))
                 self.tree_item_paths[item_id] = full_path
            except Exception as e: print(f"Error formateando item: {item} - Error: {e}\n{traceback.format_exc()}")
        self.update_button_states()

    def _configure_items_dialog(self, item_paths_with_type_hint, is_modification=False):
        if not item_paths_with_type_hint: return

        first_item_path = item_paths_with_type_hint[0][0]
        first_item_name = os.path.basename(first_item_path)
        num_items = len(item_paths_with_type_hint)
        
        dialog_title = f"Configurar Borrado ({num_items} Item{'s' if num_items > 1 else ''}) - Tempodel"
        label_text = f"Borrar {num_items} item{'s' if num_items > 1 else ''} seleccionados en:" if num_items > 1 else f"Borrar '{first_item_name}' en:"
        
        dialog = tk.Toplevel(self.root); dialog.title(dialog_title); dialog.geometry("400x300"); dialog.resizable(False, False); dialog.transient(self.root); dialog.grab_set()
        x = self.root.winfo_x(); y = self.root.winfo_y(); dialog.geometry(f"+{x + 150}+{y + 100}")
        
        ttk.Label(dialog, text=label_text, font=('Segoe UI', 10, 'bold')).pack(pady=(10, 5))
        if num_items == 1: ttk.Label(dialog, text=f"({first_item_path})", wraplength=380).pack(pady=(0,5))
        
        time_frame = ttk.Frame(dialog, padding=(20, 10)); time_frame.pack(fill=tk.X)
        ttk.Label(time_frame, text="Tiempo:").grid(row=0, column=0, padx=(0, 5), pady=5, sticky=tk.W)
        value_var = tk.StringVar(value="7"); value_entry = ttk.Entry(time_frame, textvariable=value_var, width=10); value_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        units = ["Días", "Horas", "Minutos", "Segundos"]; unit_var = tk.StringVar(value=units[0]); unit_combobox = ttk.Combobox(time_frame, textvariable=unit_var, values=units, state="readonly", width=10); unit_combobox.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)

        periodic_var = tk.BooleanVar(value=False)
        periodic_check = ttk.Checkbutton(dialog, text="Borrado Periódico (reiniciar temporizador)", variable=periodic_var)
        periodic_check.pack(pady=10)
        
        if is_modification and num_items == 1:
            schedule_list = load_schedule() # Renombrar para evitar conflicto con global
            norm_path = os.path.normpath(first_item_path)
            for item_s_cfg in schedule_list:
                if os.path.normpath(item_s_cfg['path']) == norm_path:
                    if item_s_cfg.get('periodic', False):
                        periodic_var.set(True)
                        if 'original_duration_seconds' in item_s_cfg:
                            ods = float(item_s_cfg['original_duration_seconds'])
                            if ods % (24*3600) == 0 and ods >= (24*3600) :
                                value_var.set(str(int(ods / (24*3600))))
                                unit_var.set("Días")
                            elif ods % 3600 == 0 and ods >= 3600:
                                value_var.set(str(int(ods / 3600)))
                                unit_var.set("Horas")
                            elif ods % 60 == 0 and ods >= 60:
                                value_var.set(str(int(ods / 60)))
                                unit_var.set("Minutos")
                            else:
                                value_var.set(str(int(ods)))
                                unit_var.set("Segundos")
                    break

        def on_ok():
            try:
                value_str = value_var.get().strip(); value = float(value_str)
                if not value_str or value <= 0: raise ValueError("Tiempo debe ser > 0")
            except ValueError as e_val: messagebox.showerror("Entrada Invalida", f"Numero positivo invalido.\n({e_val})", parent=dialog); return
            
            unit = unit_var.get(); user_duration_seconds = 0.0
            if unit == "Días": user_duration_seconds = value * 24 * 3600
            elif unit == "Horas": user_duration_seconds = value * 3600
            elif unit == "Minutos": user_duration_seconds = value * 60
            elif unit == "Segundos": user_duration_seconds = value
            
            delete_timestamp = time.time() + user_duration_seconds
            is_periodic_val = periodic_var.get()
            
            success_count = 0; fail_count = 0
            
            for path, _is_dir_hint_val in item_paths_with_type_hint:
                # add_item_to_schedule determinará is_dir basado en el estado actual del disco.
                # El _is_dir_hint_val es más para casos donde el path no existe y se quiere forzar el tipo.
                # (Funcionalidad no completamente implementada en add_item_to_schedule)
                if add_item_to_schedule(path, delete_timestamp, is_periodic_val, user_duration_seconds if is_periodic_val else None):
                    success_count += 1
                else:
                    fail_count += 1 # add_item_to_schedule ahora siempre retorna True, esta lógica podría cambiar si retorna False en errores
            
            print(f"Configuración completada. Exitos: {success_count}, Fallos: {fail_count}")
            if fail_count > 0 and success_count == 0:
                messagebox.showerror("Error", "No se pudieron añadir/modificar los items.", parent=dialog)
            elif fail_count > 0 :
                 messagebox.showwarning("Atención", f"{fail_count} item(s) no pudieron ser añadidos/modificados (ver consola para detalles).", parent=dialog)

            self.refresh_list(); dialog.destroy()

        def on_cancel(): dialog.destroy()
        
        button_frame_dialog = ttk.Frame(dialog, padding="10"); button_frame_dialog.pack(side=tk.BOTTOM, fill=tk.X, pady=5, anchor=tk.S)
        cancel_button = ttk.Button(button_frame_dialog, text="Cancelar", command=on_cancel, style='TButton'); cancel_button.pack(side=tk.RIGHT, padx=5)
        ok_button = ttk.Button(button_frame_dialog, text="Aceptar", command=on_ok, style='TButton'); ok_button.pack(side=tk.RIGHT, padx=5)
        
        ok_button.focus(); dialog.protocol("WM_DELETE_WINDOW", on_cancel); dialog.bind('<Return>', lambda e=None: ok_button.invoke()); dialog.bind('<Escape>', lambda e=None: cancel_button.invoke())
        value_entry.focus(); value_entry.selection_range(0, tk.END); self.root.wait_window(dialog)

    def add_file(self):
        filepaths = filedialog.askopenfilenames(title="Seleccionar Archivo(s)")
        if filepaths: self._configure_items_dialog([(fp, False) for fp in filepaths]) # False es is_dir_hint

    def add_folder(self):
        folderpath = filedialog.askdirectory(title="Seleccionar Carpeta")
        if folderpath: self._configure_items_dialog([(folderpath, True)]) # True es is_dir_hint

    def modify_selected(self):
        selected_items_ids = self.tree.selection()
        if not selected_items_ids: return
        
        paths_to_modify = []
        for sid in selected_items_ids:
            path = self.tree_item_paths.get(sid)
            if path:
                item_values = self.tree.item(sid, 'values')
                is_dir_hint_val = (item_values[0].lower() == "carpeta") if item_values and len(item_values) > 0 else False
                paths_to_modify.append((path, is_dir_hint_val))
        
        if paths_to_modify:
            self._configure_items_dialog(paths_to_modify, is_modification=True)
        else:
            messagebox.showerror("Error", "No se pudo obtener la ruta de los items seleccionados.")

    def remove_selected(self):
        selected_items = self.tree.selection()
        if not selected_items: return
        paths_to_remove = []; names_to_remove = []
        for sid in selected_items:
             path = self.tree_item_paths.get(sid)
             if path: paths_to_remove.append(path); names_to_remove.append(os.path.basename(path))
        
        if not paths_to_remove: messagebox.showerror("Error", "No se pudo obtener la ruta."); return
        
        names_str = "\n - ".join(names_to_remove[:5])
        if len(names_to_remove) > 5: names_str += f"\n... y {len(names_to_remove)-5} más."
        num = len(paths_to_remove)
        
        if messagebox.askyesno("Confirmar", f"Cancelar borrado de {num} elemento(s)?\n - {names_str}", parent=self.root):
            removed_count = sum(1 for path_rem in paths_to_remove if remove_item_from_schedule(path_rem))
            print(f"Quitados {removed_count} de {num}."); self.refresh_list()

    def on_closing(self):
        print("Cerrando Tempodel GUI...")
        global app, checker_thread
        # El checker_thread usa threading.Timer que es difícil de cancelar limpiamente una vez iniciado.
        # Establecer app = None evitará que se reprograme si la GUI se cierra.
        _app_ref = app # Guardar referencia localmente
        app = None 
        
        # Si el checker_thread es una instancia de threading.Timer, no tiene un método join() simple
        # o una forma de cancelarlo directamente si ya está en su fase de espera.
        # Al ser daemon, debería terminar cuando el hilo principal (GUI) termine.
        # No intentamos 'join' aquí para evitar colgar la GUI al cerrar.
        
        _cleanup_temp_files() 
        if _app_ref and _app_ref.root: # Usar la referencia local
            _app_ref.root.destroy()
        print("Tempodel GUI cerrada.")

# --- Funciones Auxiliares para Multi-Selección (Sin cambios) ---
def _acquire_lock():
    try:
        fd = os.open(CONFIGURE_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd); print(f"Lock adquirido: {CONFIGURE_LOCK_FILE}"); return True
    except FileExistsError: print(f"Lock ya existe: {CONFIGURE_LOCK_FILE}"); return False
    except Exception as e: print(f"Error adquiriendo lock: {e}"); return False
def _release_lock():
    try:
        if os.path.exists(CONFIGURE_LOCK_FILE): os.remove(CONFIGURE_LOCK_FILE); print(f"Lock liberado: {CONFIGURE_LOCK_FILE}")
    except Exception as e: print(f"Error liberando lock: {e}")
def _touch_lock():
    try:
        if os.path.exists(CONFIGURE_LOCK_FILE): os.utime(CONFIGURE_LOCK_FILE, None); print(f"Lock 'touched': {CONFIGURE_LOCK_FILE}"); return True
    except Exception as e: print(f"Error 'touching' lock: {e}"); return False
def _get_lock_mtime():
    try:
        if os.path.exists(CONFIGURE_LOCK_FILE): return os.path.getmtime(CONFIGURE_LOCK_FILE)
    except Exception as e: print(f"Error obteniendo mtime del lock: {e}"); return 0
def _append_pending_path(path):
    try:
        os.makedirs(os.path.dirname(PENDING_PATHS_FILE), exist_ok=True)
        with open(PENDING_PATHS_FILE, "a", encoding='utf-8') as f: f.write(path + "\n"); print(f"Path añadido a pendientes: {path}")
    except Exception as e: print(f"Error añadiendo path a pendientes: {e}")
def _read_pending_paths():
    paths = []
    try:
        if os.path.exists(PENDING_PATHS_FILE):
            with open(PENDING_PATHS_FILE, "r", encoding='utf-8') as f: paths = [line.strip() for line in f if line.strip()]
            print(f"Leidos {len(paths)} paths de pendientes.")
    except Exception as e: print(f"Error leyendo paths pendientes: {e}")
    return paths
def _cleanup_pending_file():
     try:
         if os.path.exists(PENDING_PATHS_FILE): os.remove(PENDING_PATHS_FILE); print("Archivo de paths pendientes eliminado.")
     except Exception as e: print(f"Error eliminando archivo de pendientes: {e}")
def _cleanup_temp_files():
    print("Limpiando archivos temporales de configuracion multi-select...")
    _release_lock(); _cleanup_pending_file()

def _process_collected_paths(app_instance_proc):
    print(">>> Procesando paths recolectados...")
    pending_paths_raw = _read_pending_paths()
    _release_lock() 

    if pending_paths_raw:
        item_paths_with_type_proc = []
        for p_proc in pending_paths_raw:
             is_dir_hint_proc = os.path.isdir(p_proc) 
             item_paths_with_type_proc.append((p_proc, is_dir_hint_proc))

        # Filtrar paths que existen, pero pasar todos los recolectados al diálogo si queremos permitir configurar paths no existentes
        # Para este caso, el diálogo _configure_items_dialog ya maneja paths no existentes si son periódicos.
        # No filtraremos aquí, dejaremos que _configure_items_dialog y add_item_to_schedule decidan.
        
        if item_paths_with_type_proc:
            if app_instance_proc and app_instance_proc.root.winfo_exists():
                 app_instance_proc.root.after(0, lambda paths_arg=item_paths_with_type_proc: app_instance_proc._configure_items_dialog(paths_arg))
            else: print("ERROR: Instancia de la App no disponible para mostrar dialogo de multi-select.")
        else:
             print("No se encontraron paths pendientes para procesar (quizás solo se lanzó una instancia).")

def _check_if_ready_to_process(app_instance_check, expected_mtime):
    print(f"Check MultiSelect: Verificando mtime (esperado <= {expected_mtime})...")
    current_mtime = _get_lock_mtime(); print(f"Check MultiSelect: Mtime actual: {current_mtime}")
    if not os.path.exists(CONFIGURE_LOCK_FILE):
        print("WARN MultiSelect: Lock file desaparecio. Cancelando."); _cleanup_temp_files(); return
    if current_mtime > expected_mtime + 0.1: # Tolerancia pequeña
        print(f"Check MultiSelect: Mtime ha cambiado. Reprogramando check...")
        if app_instance_check and app_instance_check.root.winfo_exists():
             app_instance_check.root.after(MULTI_SELECT_WAIT_MS, lambda inst_arg=app_instance_check, mtime_arg=current_mtime: _check_if_ready_to_process(inst_arg, mtime_arg))
        else: print("ERROR MultiSelect: No se puede reprogramar check, app no disponible."); _cleanup_temp_files()
    else:
        print("Check MultiSelect: Mtime no ha cambiado. Listo para procesar.")
        if app_instance_check and app_instance_check.root.winfo_exists(): _process_collected_paths(app_instance_check)
        else: print("ERROR MultiSelect: No se puede procesar, app no disponible."); _cleanup_temp_files()

# --- Punto de Entrada Principal ---
if __name__ == "__main__":
    path_from_context_menu = None
    is_configure_action = False

    if len(sys.argv) > 1:
        potential_path = sys.argv[1]
        path_from_context_menu = os.path.normpath(potential_path)
        is_configure_action = True
        print(f"Instancia GUI iniciada para configurar: {path_from_context_menu}")

    master_instance = False
    if is_configure_action and path_from_context_menu:
        if _acquire_lock():
            master_instance = True; print("MASTER: Lock adquirido.")
            _cleanup_pending_file(); _append_pending_path(path_from_context_menu)
            initial_mtime = _get_lock_mtime(); print(f"MASTER: Mtime inicial del lock: {initial_mtime}.")
        else:
            print("SECONDARY: Lock ya existe.")
            _append_pending_path(path_from_context_menu); _touch_lock()
            print("SECONDARY: Path añadido y lock 'touched'. Saliendo."); sys.exit(0)

    if not is_configure_action or master_instance:
        root = tk.Tk()
        app = TempodelApp(root)

        # Iniciar el checker de la GUI
        if checker_thread is None or not checker_thread.is_alive():
            print("Iniciando checker thread de borrado de la GUI...")
            # El checker de la GUI (check_and_delete de este archivo) se auto-reprograma con Timer.
            # Hacemos la primera llamada.
            initial_delay_checker = 1 # Pequeño delay para que la GUI se asiente
            checker_thread = threading.Timer(initial_delay_checker, check_and_delete)
            checker_thread.daemon = True
            checker_thread.start()
            print(f"Checker thread de borrado de la GUI programado para iniciar en {initial_delay_checker}s.")

        if master_instance and 'initial_mtime' in locals() and initial_mtime is not None:
             print(f"MASTER: Programando _check_if_ready_to_process en {MULTI_SELECT_WAIT_MS} ms (mtime esperado: {initial_mtime})")
             root.after(MULTI_SELECT_WAIT_MS, lambda inst_main=app, mtime_main=initial_mtime: _check_if_ready_to_process(inst_main, mtime_main))
        elif master_instance:
             print("ERROR CRITICO: Master instance sin initial_mtime valido. No se puede programar check de multi-select."); _cleanup_temp_files()
        
        root.mainloop()
        print("Saliendo del script principal de Tempodel GUI.")