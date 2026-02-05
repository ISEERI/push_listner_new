# DLMS_UI.py
import re
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from JSON_Viewer import JSONViewer
from Network_Server import DLMSNetworkServer
from Push_Parser import process_dlms_message
from config_manager import ConfigManager
from data_handler import DataSaver
from log_manager import LogManager
import os
import pystray
from PIL import Image, ImageDraw


class DLMSApp:
    """Основной класс GUI-приложения для работы с DLMS push-сообщениями."""

    def __init__(self, root):
        self.root = root
        self.root.title("Push Listener")
        self.root.geometry("1280x720")
        self.root.iconphoto(True, tk.PhotoImage(file="PushListener.png"))

        # Загрузка конфигурации
        self.config_manager = ConfigManager()
        config = self.config_manager.load()
        self.save_data_dir = config["save_data_dir"]
        self.load_data_dir = config["load_data_dir"]

        # Флаг для управления работой в фоне
        self.running = True

        # Создаём иконку в трее
        self.setup_tray_icon()

        # Перехватываем закрытие окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

        # Инициализация компонентов
        self.data_saver = DataSaver(self.save_data_dir)
        self.log_manager = LogManager()

        # Создание сетевого сервера
        self.server = DLMSNetworkServer(
            output_callback=self.append_log,
            on_dlms_push=self.on_dlms_push_received,
            on_autoconnect=self.on_autoconnect
        )

        # Создание системы вкладок
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Вкладка сервера
        self.server_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.server_frame, text="Сервер")
        self.setup_server_tab()

        # Вкладка анализа
        self.analysis_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.analysis_frame, text="Анализ")
        self.json_viewer = JSONViewer(
            self.analysis_frame,
            initial_load_dir=self.load_data_dir,
            on_load_dir_change=self.on_json_viewer_load_dir_change
        )
        self.json_viewer.set_load_directory(self.load_data_dir)

        self.logging_enabled = True

    def create_image(self):
        """Загружает пользовательскую иконку из файла."""
        try:
            # Попробуем загрузить PNG
            return Image.open("PushListener.png")
        except FileNotFoundError:
            try:
                # Или ICO
                return Image.open("PushListener.ico")
            except FileNotFoundError:
                # Если иконка не найдена — создаём запасную
                width, height = 64, 64
                image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
                dc = ImageDraw.Draw(image)
                dc.rectangle((16, 16, 48, 48), fill=(0, 120, 215, 255))  # Синий квадрат
                return image

    def setup_tray_icon(self):
        """Настраивает иконку в системном трее."""
        image = self.create_image()
        menu = (
            pystray.MenuItem("Показать", self.show_window),
            pystray.MenuItem("Выход", self.quit_app)
        )
        self.icon = pystray.Icon("DLMS_Listener", image, "DLMS Push Listener", menu)

        # Запускаем иконку в отдельном потоке
        self.tray_thread = threading.Thread(target=self.icon.run, daemon=True)
        self.tray_thread.start()

    def show_window(self, icon=None, item=None):
        """Показывает главное окно."""
        self.root.deiconify()  # Восстанавливает окно
        self.root.lift()  # Поднимает поверх других окон
        self.root.focus_force()  # Делает активным

    def on_close_window(self):
        """Обработчик закрытия окна — сворачивает в трей."""
        self.root.withdraw()  # Скрывает окно
        # Опционально: показываем уведомление
        if hasattr(self, 'icon'):
            self.icon.notify("Программа работает в фоне", "DLMS Push Listener")

    def quit_app(self, icon=None, item=None):
        """Полностью завершает приложение."""
        self.running = False
        self.stop_all()  # Останавливаем серверы

        # Сохраняем конфигурацию через config_manager
        config = {
            "save_data_dir": self.save_data_dir,
            "load_data_dir": self.load_data_dir,
        }
        self.config_manager.save(config)

        # Закрываем иконку трея
        if hasattr(self, 'icon'):
            self.icon.stop()

        # Закрываем главное окно
        self.root.quit()
        self.root.destroy()

    def on_close(self):
        """Вызывается при закрытии (уже не используется напрямую)."""
        pass  # Теперь управление через tray

    def on_json_viewer_load_dir_change(self, new_dir):
        """Обновляет путь загрузки при изменении в JSONViewer."""
        self.load_data_dir = new_dir

    def setup_server_tab(self):
        """Настраивает интерфейс вкладки сервера."""
        control_frame = ttk.Frame(self.server_frame, padding="10")
        control_frame.pack(fill=tk.X)

        ttk.Label(control_frame, text="Порты (вводить несколько портов через запятую):").grid(row=0, column=2,
                                                                                              sticky=tk.W)
        self.ports_var = tk.StringVar(value="5000")
        ttk.Entry(control_frame, textvariable=self.ports_var, width=20).grid(row=0, column=3, padx=5)

        self.tcp_btn = ttk.Button(control_frame, text="Запустить по TCP", command=self.start_tcp)
        self.tcp_btn.grid(row=0, column=4, padx=5)

        self.udp_btn = ttk.Button(control_frame, text="Запустить UDP", command=self.start_udp)
        self.udp_btn.grid(row=0, column=5, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="Остановить всё", command=self.stop_all, state="disabled")
        self.stop_btn.grid(row=0, column=6, padx=5)

        ttk.Label(control_frame, text="Папка для сохранения:").grid(row=0, column=7, sticky=tk.W)
        self.save_dir_label = ttk.Label(control_frame, text=self.save_data_dir, width=30, anchor=tk.W)
        self.save_dir_label.grid(row=0, column=8, sticky=tk.W, padx=5)
        ttk.Button(control_frame, text="Выбрать...", command=self.select_save_directory).grid(row=0, column=9, padx=5)

        log_frame = ttk.LabelFrame(self.server_frame, text="Журнал", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            state="normal"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Настройка цветовой кодировки
        self.log_text.tag_configure("obis", foreground="green")
        self.log_text.tag_configure("debug", foreground="#e0cf36")
        self.log_text.tag_configure("save", foreground="orange")
        self.log_text.tag_configure("error", foreground="red", underline=True)
        self.log_text.tag_configure("autoconnect", foreground="blue")

        # Контекстное меню
        self.context_menu = tk.Menu(self.log_text, tearoff=0)
        self.context_menu.add_command(label="Копировать", command=self.copy_selection)
        self.log_text.bind("<Button-3>", self.show_context_menu)

        # Поддержка Ctrl+C
        def on_text_key(event):
            if event.state & 0x4 and event.keycode == 67:
                self.copy_selection()
                return "break"

        self.log_text.bind("<Key>", on_text_key)

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def copy_selection(self):
        """Копирует выделенный текст в буфер обмена."""
        try:
            selected_text = self.log_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
        except tk.TclError:
            pass

    def parse_ports(self, ports_str):
        """Преобразует строку портов в список целых чисел."""
        try:
            ports = []
            for p in ports_str.split(','):
                p = p.strip()
                if p:
                    port = int(p)
                    if 1 <= port <= 65535:
                        ports.append(port)
                    else:
                        raise ValueError
            return ports
        except:
            messagebox.showerror("Error", "Invalid port format. Use comma-separated numbers (1-65535).")
            return None

    def append_log(self, message, address=None):
        """Добавляет сообщение в журнал с цветовой кодировкой."""
        if not self.logging_enabled:
            return

        # Сохранение в файл
        self.log_manager.save_to_file(message, address)

        prefix = ""
        if address:
            prefix = f"[{address[0]}:{address[1]}] "
        full_message = prefix + message + "\n"

        # Проверка количества строк перед добавлением
        current_line_count = int(self.log_text.index('end-1c').split('.')[0])
        if current_line_count >= 10000:
            # Очищаем журнал, оставляя последние 1000 строк для контекста
            all_lines = self.log_text.get('1.0', 'end-1c').split('\n')
            if len(all_lines) > 1000:
                keep_lines = all_lines[-1000:]  # Последние 1000 строк
                self.log_text.delete('1.0', 'end')
                self.log_text.insert('1.0', '\n'.join(keep_lines) + '\n')
                # Добавляем уведомление об очистке
                self.log_text.insert('end', "[!] Журнал очищен: сохранены последние 1000 строк\n")
                self.log_text.tag_add("error", "end-2l", "end-1c")  # Подсветка уведомления

        start_idx = self.log_text.index("end-1c")
        self.log_text.insert(tk.END, full_message)
        end_idx = self.log_text.index("end-1c")
        inserted_text = self.log_text.get(start_idx, end_idx)

        # Подсветка комментариев <!-- ... -->
        for match in re.finditer(r"<!--[^>]*-->", inserted_text):
            comment_start = match.start()
            comment_end = match.end()
            self.log_text.tag_add(
                "obis",
                f"{start_idx}+{comment_start}c",
                f"{start_idx}+{comment_end}c"
            )

        # Цветовая кодировка
        if "[✓]" in full_message:
            self.log_text.tag_add("debug", start_idx, end_idx)
        elif "[+] Данные сохранены в " in full_message:
            self.log_text.tag_add("save", start_idx, end_idx)
        elif "[Autoconnect:" in full_message or '<sn=' in full_message:
            self.log_text.tag_add("autoconnect", start_idx, end_idx)
        elif "[ERROR]" in full_message or "[XML Parse Error]" in full_message or "[!]" in full_message:
            self.log_text.tag_add("error", start_idx, end_idx)

        self.log_text.see(tk.END)

    def select_save_directory(self):
        """Выбор папки для сохранения JSON-файлов."""
        selected_dir = filedialog.askdirectory(
            initialdir=self.save_data_dir,
            title="Выберите папку для сохранения JSON-файлов"
        )
        if selected_dir:
            self.save_data_dir = os.path.normpath(selected_dir)
            self.save_dir_label.config(text=self.save_data_dir)
            self.data_saver = DataSaver(self.save_data_dir)

    def on_dlms_push_received(self, xml_str: str, address, port):
        """Обработчик полученных DLMS push-сообщений."""
        try:
            parsed = process_dlms_message(xml_str)
            filename = self.data_saver.save_dlms_push(parsed)
            self.append_log(f"[+] Данные сохранены в {filename} (InvokeID: {parsed.get('invoke_id')})")
        except Exception as e:
            self.append_log(f"[ERROR] Не удалось разобрать и сохранить пуш: {e}")

    def on_autoconnect(self, sn: str, ip: str, port: int):
        """Обработчик autoconnect-сообщений."""
        filename = self.data_saver.save_autoconnect(sn, ip, port)
        self.append_log(f"[+] Autoconnect: {sn} ({ip}:{port}) → {filename}")

    def start_tcp(self):
        """Запускает TCP-серверы на указанных портах."""
        host = "0.0.0.0"
        ports = self.parse_ports(self.ports_var.get())
        if ports is None:
            return
        for port in ports:
            self.server.start_tcp(host, port)
        self.stop_btn.config(state="normal")

    def start_udp(self):
        """Запускает UDP-серверы на указанных портах."""
        host = "0.0.0.0"
        ports = self.parse_ports(self.ports_var.get())
        if ports is None:
            return
        for port in ports:
            self.server.start_udp(host, port)
        self.stop_btn.config(state="normal")

    def stop_all(self):
        """Останавливает все серверы."""
        self.server.stop()
        self.stop_btn.config(state="disabled")

    def on_close(self):
        """Обработчик закрытия приложения."""
        self.logging_enabled = False
        self.stop_all()
        # Сохранение конфигурации
        config = {
            "save_data_dir": self.save_data_dir,
            "load_data_dir": self.load_data_dir,
        }
        self.config_manager.save(config)
        self.root.destroy()



