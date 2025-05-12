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
import traceback # Para mejor logging de errores

# --- Constantes y Configuración ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_FILE = os.path.join(SCRIPT_DIR, "schedule.json")
CHECK_INTERVAL_SECONDS = 60 # Intervalo para el checker de borrado normal
app = None
checker_thread = None

# --- Archivos Temporales para Multi-Selección ---
TEMP_DIR = tempfile.gettempdir()
# Usar nombres específicos para evitar colisiones
CONFIGURE_LOCK_FILE = os.path.join(TEMP_DIR, "tempodel_configure_multiselect.lock")
PENDING_PATHS_FILE = os.path.join(TEMP_DIR, "tempodel_pending_paths_multiselect.txt")
# Tiempo de espera *inicial* y de *extensión*
MULTI_SELECT_WAIT_MS = 600 # Aumentado ligeramente a 600ms

# --- Funciones de Gestión del Schedule (Sin cambios respecto a la versión anterior) ---
# ... (load_schedule, save_schedule, add_item_to_schedule, remove_item_from_schedule) ...
# (Asegúrate de copiar aquí las versiones más recientes de estas funciones)
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
    finally:
        if lock_created and os.path.exists(lock_file):
             try: os.remove(lock_file)
             except OSError: pass

def add_item_to_schedule(item_path, delete_timestamp):
    # (Igual que antes, maneja actualización)
    if not os.path.exists(item_path):
        print(f"WARN: Path no existe al añadir/actualizar: {item_path}")
        return False
    schedule = load_schedule()
    normalized_path = os.path.normpath(item_path)
    is_directory = os.path.isdir(normalized_path)
    existing_item_index = -1
    for i, item in enumerate(schedule):
        if 'path' in item and os.path.normpath(item['path']) == normalized_path:
            existing_item_index = i
            break
    if existing_item_index != -1:
        schedule[existing_item_index]['delete_at'] = delete_timestamp
        schedule[existing_item_index]['is_dir'] = is_directory
        print(f"'{os.path.basename(normalized_path)}' actualizado. Nuevo borrado: {datetime.datetime.fromtimestamp(delete_timestamp)}")
    else:
        schedule.append({"path": normalized_path, "delete_at": delete_timestamp, "is_dir": is_directory})
        print(f"'{os.path.basename(normalized_path)}' añadido para borrar el {datetime.datetime.fromtimestamp(delete_timestamp)}")
    save_schedule(schedule)
    return True

def remove_item_from_schedule(item_path):
    # (Igual que antes)
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
# --- Fin Funciones Schedule ---

# --- Lógica del Background Checker (Sin cambios respecto a la versión anterior) ---
# ... (check_and_delete) ...
# (Asegúrate de copiar aquí la función check_and_delete más reciente)
def check_and_delete():
    global SCHEDULE_FILE
    print(f"{datetime.datetime.now()}: Comprobando schedule en {SCHEDULE_FILE}...")
    schedule = load_schedule()
    current_time = time.time()
    items_to_keep = []
    items_processed_paths = set()

    for item in schedule:
        if not all(k in item for k in ('path', 'delete_at', 'is_dir')): continue
        path_to_process = os.path.normpath(item['path'])
        is_dir = item['is_dir']
        if path_to_process in items_processed_paths: continue
        delete_time = item.get('delete_at', 0)

        if current_time >= delete_time:
            print(f"Tiempo cumplido para: {path_to_process}")
            items_processed_paths.add(path_to_process)
            try:
                if os.path.exists(path_to_process):
                    if is_dir:
                        print(f"Intentando borrar carpeta: {path_to_process}")
                        shutil.rmtree(path_to_process)
                        print(f"Carpeta borrada: {path_to_process}")
                    else:
                        print(f"Intentando borrar archivo: {path_to_process}")
                        os.remove(path_to_process)
                        print(f"Archivo borrado: {path_to_process}")
                else: print(f"Elemento ya no existia: {path_to_process}")
            except OSError as e:
                print(f"Error borrando {path_to_process}: {e}")
                if app and app.root.winfo_exists(): app.root.after(0, lambda p=path_to_process, err=e: messagebox.showerror("Error de Borrado", f"No se pudo borrar:\n{p}\n\nError: {err}"))
            except Exception as e:
                print(f"Error inesperado procesando {path_to_process}: {e}")
                if app and app.root.winfo_exists(): app.root.after(0, lambda p=path_to_process, err=e: messagebox.showerror("Error Inesperado", f"Error procesando:\n{p}\n\nError: {err}"))
        else:
            if os.path.exists(path_to_process): items_to_keep.append(item)
            else:
                print(f"Elemento no encontrado (se quitara): {path_to_process}")
                items_processed_paths.add(path_to_process)

    if items_processed_paths:
         save_schedule(items_to_keep)
         if app is not None and app.root.winfo_exists(): app.root.after(0, app.refresh_list)

    global checker_thread
    if checker_thread is not None and checker_thread.is_alive():
         timer = threading.Timer(CHECK_INTERVAL_SECONDS, check_and_delete)
         timer.daemon = True
         timer.start()
# --- Fin Background Checker ---

# --- Interfaz Gráfica (Tkinter) ---
class TempodelApp:
    # ... ( __init__ , update_button_states, on_tree_select, format_item_for_treeview, refresh_list ) ...
    # (Estas funciones son iguales que en la versión anterior)
    def __init__(self, root):
        self.root = root
        self.root.title("Tempodel - Gestor de Borrado Programado")
        # ... (resto del __init__ igual) ...
        icon_path = os.path.join(SCRIPT_DIR, 'icon.ico')
        if os.path.exists(icon_path):
            try: self.root.iconbitmap(icon_path)
            except Exception as e: print(f"No se pudo cargar el icono: {e}")
        window_width = 750; window_height = 450
        screen_width = root.winfo_screenwidth(); screen_height = root.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2); center_y = int(screen_height/2 - window_height / 2)
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        main_frame = ttk.Frame(root, padding="10"); main_frame.pack(fill=tk.BOTH, expand=True)
        list_frame = ttk.LabelFrame(main_frame, text="Archivos/Carpetas Programados", padding="10"); list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.tree = ttk.Treeview(list_frame, columns=('Tipo', 'Nombre', 'Ubicacion', 'Fecha Borrado'), show='headings', height=15)
        self.tree.heading('Tipo', text='Tipo'); self.tree.heading('Nombre', text='Nombre'); self.tree.heading('Ubicacion', text='Ubicacion'); self.tree.heading('Fecha Borrado', text='Fecha Borrado')
        self.tree.column('Tipo', width=60, anchor=tk.W); self.tree.column('Nombre', width=150, anchor=tk.W); self.tree.column('Ubicacion', width=300, anchor=tk.W); self.tree.column('Fecha Borrado', width=140, anchor=tk.CENTER)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree_item_paths = {}; self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        button_frame = ttk.Frame(main_frame, padding="5"); button_frame.pack(fill=tk.X, pady=(5,0))
        style = ttk.Style(); style.configure('TButton', padding=5, font=('Segoe UI', 9))
        add_file_button = ttk.Button(button_frame, text="Añadir Archivo", command=self.add_file, style='TButton'); add_file_button.pack(side=tk.LEFT, padx=5)
        add_folder_button = ttk.Button(button_frame, text="Añadir Carpeta", command=self.add_folder, style='TButton'); add_folder_button.pack(side=tk.LEFT, padx=5)
        self.modify_button = ttk.Button(button_frame, text="Modificar Fecha", command=self.modify_selected, style='TButton', state=tk.DISABLED); self.modify_button.pack(side=tk.LEFT, padx=5)
        self.remove_button = ttk.Button(button_frame, text="Quitar Seleccionado", command=self.remove_selected, style='TButton', state=tk.DISABLED); self.remove_button.pack(side=tk.LEFT, padx=5)
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
        return kind, name, parent_dir, delete_str, path

    def refresh_list(self):
        # ... (Igual que antes) ...
        for i in self.tree.get_children(): self.tree.delete(i)
        self.tree_item_paths.clear()
        schedule = load_schedule()
        schedule.sort(key=lambda x: x.get('delete_at', 0))
        for item in schedule:
            if not all(k in item for k in ('path', 'delete_at', 'is_dir')): continue
            try:
                 kind, name, parent_dir, delete_str, full_path = self.format_item_for_treeview(item)
                 item_id = self.tree.insert('', tk.END, values=(kind, name, parent_dir, delete_str))
                 self.tree_item_paths[item_id] = full_path
            except Exception as e: print(f"Error formateando item: {item} - Error: {e}")
        self.update_button_states()


    # --- Diálogo de Configuración (Sin cambios respecto a la versión anterior) ---
    def _configure_items_dialog(self, item_paths):
        # ... (Esta función es igual que en la versión anterior) ...
        if not item_paths: return
        first_item_path = item_paths[0]; first_item_name = os.path.basename(first_item_path)
        num_items = len(item_paths)
        dialog_title = f"Configurar Borrado ({num_items} Items) - Tempodel"
        label_text = f"Borrar {num_items} items seleccionados en:" if num_items > 1 else f"Borrar '{first_item_name}' en:"
        dialog = tk.Toplevel(self.root); dialog.title(dialog_title); dialog.geometry("400x250"); dialog.resizable(False, False); dialog.transient(self.root); dialog.grab_set()
        x = self.root.winfo_x(); y = self.root.winfo_y(); dialog.geometry(f"+{x + 150}+{y + 100}")
        ttk.Label(dialog, text=label_text, font=('Segoe UI', 10, 'bold')).pack(pady=(10, 5))
        if num_items == 1: ttk.Label(dialog, text=f"({first_item_path})", wraplength=380).pack(pady=(0,5))
        time_frame = ttk.Frame(dialog, padding=(20, 10)); time_frame.pack(fill=tk.X)
        ttk.Label(time_frame, text="Tiempo:").grid(row=0, column=0, padx=(0, 5), pady=5, sticky=tk.W)
        value_var = tk.StringVar(value="7"); value_entry = ttk.Entry(time_frame, textvariable=value_var, width=10); value_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        units = ["Días", "Horas", "Minutos", "Segundos"]; unit_var = tk.StringVar(value=units[0]); unit_combobox = ttk.Combobox(time_frame, textvariable=unit_var, values=units, state="readonly", width=10); unit_combobox.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)

        def on_ok():
            try:
                value_str = value_var.get().strip(); value = float(value_str)
                if not value_str or value <= 0: raise ValueError("Tiempo debe ser > 0")
            except ValueError as e: messagebox.showerror("Entrada Invalida", f"Numero positivo invalido.\n({e})", parent=dialog); return
            unit = unit_var.get(); duration_seconds = 0
            if unit == "Días": duration_seconds = value * 24 * 3600
            elif unit == "Horas": duration_seconds = value * 3600
            elif unit == "Minutos": duration_seconds = value * 60
            elif unit == "Segundos": duration_seconds = value
            delete_timestamp = time.time() + duration_seconds
            success_count = 0; fail_count = 0
            print(f"Aplicando timestamp {delete_timestamp} a {len(item_paths)} items...")
            for path in item_paths:
                if add_item_to_schedule(path, delete_timestamp): success_count += 1
                else: fail_count += 1
            print(f"Completado. Exitos: {success_count}, Fallos: {fail_count}")
            self.refresh_list(); dialog.destroy()
        def on_cancel(): dialog.destroy()
        button_frame_dialog = ttk.Frame(dialog, padding="10"); button_frame_dialog.pack(side=tk.BOTTOM, fill=tk.X, pady=5, anchor=tk.S)
        cancel_button = ttk.Button(button_frame_dialog, text="Cancelar", command=on_cancel, style='TButton'); cancel_button.pack(side=tk.RIGHT, padx=5)
        ok_button = ttk.Button(button_frame_dialog, text="Aceptar", command=on_ok, style='TButton'); ok_button.pack(side=tk.RIGHT, padx=5)
        ok_button.focus(); dialog.protocol("WM_DELETE_WINDOW", on_cancel); dialog.bind('<Return>', lambda e=None: ok_button.invoke()); dialog.bind('<Escape>', lambda e=None: cancel_button.invoke())
        value_entry.focus(); value_entry.selection_range(0, tk.END); self.root.wait_window(dialog)


    # --- Métodos de Acción (add_file, add_folder, modify_selected, remove_selected sin cambios) ---
    # (Estas funciones son iguales que en la versión anterior, llaman a _configure_items_dialog)
    def add_file(self):
        filepath = filedialog.askopenfilename(title="Seleccionar Archivo")
        if filepath: self._configure_items_dialog([filepath])
    def add_folder(self):
        folderpath = filedialog.askdirectory(title="Seleccionar Carpeta")
        if folderpath: self._configure_items_dialog([folderpath])
    def modify_selected(self):
        selected_items = self.tree.selection()
        if not selected_items: return
        paths = [self.tree_item_paths.get(sid) for sid in selected_items if self.tree_item_paths.get(sid)]
        if paths: self._configure_items_dialog(paths) # Modificar todos los seleccionados
        else: messagebox.showerror("Error", "No se pudo obtener la ruta.")
    def remove_selected(self):
        selected_items = self.tree.selection()
        if not selected_items: return
        paths_to_remove = []; names_to_remove = []
        for sid in selected_items:
             path = self.tree_item_paths.get(sid)
             if path: paths_to_remove.append(path); names_to_remove.append(os.path.basename(path))
        if not paths_to_remove: messagebox.showerror("Error", "No se pudo obtener la ruta."); return
        names_str = "\n - ".join(names_to_remove); num = len(paths_to_remove)
        if messagebox.askyesno("Confirmar", f"Cancelar borrado de {num} elemento(s)?\n - {names_str}", parent=self.root):
            removed_count = sum(1 for path in paths_to_remove if remove_item_from_schedule(path))
            print(f"Quitados {removed_count} de {num}."); self.refresh_list()

    def on_closing(self):
        # ... (Igual que antes, llama a _cleanup_temp_files) ...
        print("Cerrando Tempodel GUI...")
        _cleanup_temp_files() # Intenta limpiar al cerrar
        self.root.destroy()
        global app
        app = None
        print("Tempodel GUI cerrada.")

# --- Funciones Auxiliares para Multi-Selección (MODIFICADAS) ---

def _acquire_lock():
    """Intenta crear el lock file. Devuelve True si lo crea, False si ya existe."""
    try:
        fd = os.open(CONFIGURE_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        print(f"Lock adquirido: {CONFIGURE_LOCK_FILE}")
        return True
    except FileExistsError:
        print(f"Lock ya existe: {CONFIGURE_LOCK_FILE}")
        return False
    except Exception as e:
        print(f"Error adquiriendo lock: {e}")
        return False

def _release_lock():
    """Elimina el lock file."""
    try:
        if os.path.exists(CONFIGURE_LOCK_FILE):
            os.remove(CONFIGURE_LOCK_FILE)
            print(f"Lock liberado: {CONFIGURE_LOCK_FILE}")
    except Exception as e:
        print(f"Error liberando lock: {e}")

def _touch_lock():
    """Actualiza la fecha de modificación del lock file."""
    try:
        if os.path.exists(CONFIGURE_LOCK_FILE):
            os.utime(CONFIGURE_LOCK_FILE, None) # None usa tiempo actual
            print(f"Lock 'touched': {CONFIGURE_LOCK_FILE}")
            return True
    except Exception as e:
        print(f"Error 'touching' lock: {e}")
    return False

def _get_lock_mtime():
    """Obtiene la fecha de modificación del lock file."""
    try:
        if os.path.exists(CONFIGURE_LOCK_FILE):
            return os.path.getmtime(CONFIGURE_LOCK_FILE)
    except Exception as e:
        print(f"Error obteniendo mtime del lock: {e}")
    return 0 # Devolver 0 si no existe o hay error

def _append_pending_path(path):
    """Añade ruta al archivo de pendientes."""
    try:
        os.makedirs(os.path.dirname(PENDING_PATHS_FILE), exist_ok=True)
        # Usar 'with' asegura que el archivo se cierre
        with open(PENDING_PATHS_FILE, "a", encoding='utf-8') as f:
            f.write(path + "\n")
            print(f"Path añadido a pendientes: {path}")
    except Exception as e:
        print(f"Error añadiendo path a pendientes: {e}")

def _read_pending_paths():
    """Lee rutas del archivo de pendientes."""
    paths = []
    try:
        if os.path.exists(PENDING_PATHS_FILE):
            with open(PENDING_PATHS_FILE, "r", encoding='utf-8') as f:
                paths = [line.strip() for line in f if line.strip()]
            print(f"Leidos {len(paths)} paths de pendientes.")
    except Exception as e:
        print(f"Error leyendo paths pendientes: {e}")
    return paths

def _cleanup_pending_file():
     """Elimina el archivo de pendientes."""
     try:
         if os.path.exists(PENDING_PATHS_FILE):
             os.remove(PENDING_PATHS_FILE)
             print("Archivo de paths pendientes eliminado.")
     except Exception as e:
        print(f"Error eliminando archivo de pendientes: {e}")

def _cleanup_temp_files():
    """Limpia ambos archivos temporales."""
    print("Limpiando archivos temporales de configuracion multi-select...")
    _release_lock()
    _cleanup_pending_file()

# --- NUEVA Lógica de Comprobación y Procesamiento (MODIFICADA) ---

def _process_collected_paths(app_instance):
    """Función final que lee, limpia y muestra el diálogo."""
    print(">>> Procesando paths recolectados...")
    pending_paths = _read_pending_paths()
    _release_lock() # Liberar lock AHORA que vamos a procesar

    if pending_paths:
        print(f"Mostrando dialogo de configuracion para {len(pending_paths)} items.")
        existing_paths = [p for p in pending_paths if os.path.exists(p)]
        omitted = len(pending_paths) - len(existing_paths)
        if omitted > 0:
             print(f"WARN: {omitted} paths ya no existen y fueron omitidos.")
        
        if existing_paths:
            # Asegurarse que se llama en el hilo de la GUI si app_instance existe
            if app_instance and app_instance.root.winfo_exists():
                 app_instance.root.after(0, lambda paths=existing_paths: app_instance._configure_items_dialog(paths))
            else: # Si la GUI se cerró mientras esperábamos? improbable pero posible
                 print("ERROR: Instancia de la App no disponible para mostrar dialogo.")
        else:
             print("WARN: Ninguno de los paths pendientes existe.")
             if app_instance and app_instance.root.winfo_exists():
                 messagebox.showwarning("Items no encontrados", "Los archivos/carpetas seleccionados ya no existen.", parent=app_instance.root)
    else:
        print("No se encontraron paths pendientes para procesar (quizás solo se lanzó una instancia).")
        # Podríamos opcionalmente abrir el diálogo para el único path del master si es necesario,
        # pero la lógica actual asume que si no hay pendientes es que ya se procesó o no hubo más.


def _check_if_ready_to_process(app_instance, expected_mtime):
    """Comprueba si el lock file ha sido modificado recientemente."""
    print(f"Check: Verificando si mtime del lock ha cambiado (esperado <= {expected_mtime})...")
    current_mtime = _get_lock_mtime()
    print(f"Check: Mtime actual: {current_mtime}")

    # Asegurarnos que el lock todavía existe (podría haber sido eliminado por error)
    if not os.path.exists(CONFIGURE_LOCK_FILE):
        print("WARN: Lock file desaparecio durante la espera. Cancelando proceso.")
        _cleanup_temp_files() # Limpiar por si acaso
        return

    # Comparar con una pequeña tolerancia por posibles fluctuaciones del sistema de archivos
    if current_mtime > expected_mtime + 0.1:
        print(f"Check: Mtime ha cambiado ({current_mtime} > {expected_mtime}). Alguien mas escribio. Reprogramando check...")
        # Reprogramar la misma comprobación, pasando la nueva mtime como la esperada
        if app_instance and app_instance.root.winfo_exists():
             app_instance.root.after(MULTI_SELECT_WAIT_MS,
                                     lambda inst=app_instance, mtime=current_mtime: _check_if_ready_to_process(inst, mtime))
        else:
             print("ERROR: No se puede reprogramar check, instancia de app no disponible.")
             _cleanup_temp_files() # Limpiar si no podemos continuar
    else:
        print("Check: Mtime no ha cambiado. Intervalo completado. Listo para procesar.")
        # ¡Listo! Llamar a la función que realmente procesa los paths
        # Asegurarse que se ejecuta en el hilo principal
        if app_instance and app_instance.root.winfo_exists():
             # No necesitamos after(0) aquí porque _process_collected_paths ya lo usa si es necesario
             _process_collected_paths(app_instance)
        else:
             print("ERROR: No se puede procesar, instancia de app no disponible.")
             _cleanup_temp_files() # Limpiar


# --- Punto de Entrada Principal (MODIFICADO) ---
if __name__ == "__main__":
    path_from_context_menu = None
    is_configure_action = False

    if len(sys.argv) > 1:
        potential_path = sys.argv[1]
        if os.path.exists(potential_path):
            path_from_context_menu = os.path.normpath(potential_path)
            is_configure_action = True
            print(f"Instancia GUI iniciada para configurar: {path_from_context_menu}")
        else:
            print(f"ERROR: Ruta de argumento no existe: '{potential_path}'")
            sys.exit(1)

    master_instance = False
    if is_configure_action:
        if _acquire_lock():
            # --- MASTER ---
            master_instance = True
            print("MASTER: Lock adquirido.")
            _cleanup_pending_file() # Limpiar pendientes anteriores
            _append_pending_path(path_from_context_menu) # Añadir mi path
            # Guardar el mtime inicial justo después de crearlo/añadir path
            initial_mtime = _get_lock_mtime()
            print(f"MASTER: Mtime inicial del lock: {initial_mtime}. Programando primer check.")
            # El inicio de la GUI y la programación del check se hacen más abajo
        else:
            # --- SECONDARY ---
            print("SECONDARY: Lock ya existe.")
            _append_pending_path(path_from_context_menu) # Añadir mi path
            _touch_lock() # Actualizar mtime del lock para señalar actividad
            print("SECONDARY: Path añadido y lock 'touched'. Saliendo.")
            sys.exit(0) # Salir inmediatamente

    # --- Iniciar GUI (Solo si soy Master o si no es acción de configurar) ---
    if not is_configure_action or master_instance:
        # Crear instancia de la app ANTES de programar el 'after'
        root = tk.Tk()
        app = TempodelApp(root) # Instancia global 'app' se establece aquí

        # Iniciar checker de borrado normal
        if checker_thread is None or not checker_thread.is_alive():
            checker_thread = threading.Thread(target=check_and_delete, daemon=True, name="TempodelChecker")
            checker_thread.start()
            print("Checker thread de borrado iniciado.")

        # Si soy Master de una acción de configurar, programar la PRIMERA comprobación
        if master_instance:
            if 'initial_mtime' in locals(): # Asegurarse que la variable existe
                 print(f"MASTER: Programando _check_if_ready_to_process en {MULTI_SELECT_WAIT_MS} ms (mtime esperado: {initial_mtime})")
                 # Pasar la instancia 'app' y el mtime esperado
                 root.after(MULTI_SELECT_WAIT_MS,
                            lambda inst=app, mtime=initial_mtime: _check_if_ready_to_process(inst, mtime))
            else:
                 print("ERROR CRITICO: Master instance sin initial_mtime. No se puede programar check.")
                 _cleanup_temp_files() # Limpiar

        # Iniciar el bucle principal de la GUI
        root.mainloop()

        print("Saliendo del script principal de Tempodel.")
        app = None # Limpiar referencia global