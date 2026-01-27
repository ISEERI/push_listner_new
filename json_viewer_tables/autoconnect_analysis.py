# json_viewer_tables/autoconnect_analysis.py

import tkinter as tk
from datetime import datetime
from json_viewer_tables.base_display_analyze import BaseDisplay
from utils import _format_datetime


class AutoConnectAnalysisDisplay(BaseDisplay):
    """
        Класс для иерархического отображения автоконнектов, сгруппированных по серийным номерам (SN).

        Особенности:
        - Группировка записей по SN с возможностью сворачивания/разворачивания
        - Фильтрация групп по подстроке в SN
        - Валидация периодичности подключений (12 часов ± 1 минута)
        - Сохранение состояния развёрнутости групп при сортировке и фильтрации
        - Сортировка как по группам (SN), так и внутри групп по колонкам
    """
    def __init__(self, tree, parent_window):
        super().__init__(tree, parent_window)
        self.all_sn_groups = {}  # Хранит все данные, сгруппированные по SN
        self.current_filter = ""  # Текущая строка фильтрации для поиска по SN
        self.open_states_cache = set()  # Кэш SN, которые были развёрнуты пользователем

    def display(self, data: list, search_filter: str = ""):
        self.current_filter = search_filter.lower()
        self.clear_tree()

        # Инициализация данных только при первом вызове (для сохранения состояния при фильтрации)
        if not self.all_sn_groups:
            self.all_sn_groups = {}
            for entry in data:
                sn = entry.get("sn", "Неизвестен")
                if sn not in self.all_sn_groups:
                    self.all_sn_groups[sn] = []
                self.all_sn_groups[sn].append(entry)

            # Сортировка каждой группы по времени получения сообщения
            for entries in self.all_sn_groups.values():
                try:
                    entries.sort(key=lambda x: x.get("received_at", ""))
                except:
                    pass

        # Применение фильтрации: оставляем только группы, содержащие подстроку
        filtered_sn_groups = {
            sn: entries for sn, entries in self.all_sn_groups.items()
            if self.current_filter in sn.lower()
        }

        self.tree.configure(show="tree headings")

        columns = ("received_at", "ip", "port", "validation")
        headings = ["Получено", "IP", "Порт", "Валидация"]
        widths = [150, 100, 60, 80]

        # Настройка колонок с обработчиками сортировки
        self.tree["columns"] = columns
        for col, heading, width in zip(columns, headings, widths):
            self.tree.heading(col, text=heading, anchor=tk.W, command=lambda c=col: self._sort_by_column(c))
            self.tree.column(col, width=width, minwidth=50, anchor=tk.W)

        # Настройка корневого столбца (#0) для отображения SN
        self.tree.heading("#0", text="Счётчик (SN)", anchor=tk.W, command=self._sort_by_sn)
        self.tree.column("#0", width=200, minwidth=150, stretch=True, anchor=tk.W)

        # Сохранение состояния развёрнутости перед перестроением дерева
        self._cache_open_states()

        # Построение иерархического дерева
        for sn, entries in filtered_sn_groups.items():
            parent_id = self.tree.insert("", "end", text=sn, values=("", "", "", ""), open=False)
            if sn in self.open_states_cache:
                self.tree.item(parent_id, open=True)

            # Преобразуем received_at в datetime для расчётов
            parsed_entries = []
            for entry in entries:
                raw_time = entry.get("received_at", "")
                try:
                    dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                except:
                    dt = None
                parsed_entries.append((entry, dt))

            # Расчёт валидации для каждой записи
            for i, (entry, current_dt) in enumerate(parsed_entries):
                validation = "✅"
                if i > 0 and current_dt is not None and parsed_entries[i - 1][1] is not None:
                    prev_dt = parsed_entries[i - 1][1]
                    delta = current_dt - prev_dt
                    # Ожидаемый интервал: 12 часов = 43200 секунд
                    expected_sec = 12 * 3600  # 43200
                    actual_sec = abs(delta.total_seconds())
                    # Допуск: ±10 минут = ±600 секунд
                    if not (expected_sec - 600 <= actual_sec <= expected_sec + 600):
                        validation = "❌"

                # Форматирование данных для отображения
                received_at = _format_datetime(entry.get("received_at", ""))
                ip = entry.get("ip", "")
                port = entry.get("port", "")

                self.tree.insert(parent_id, "end", values=(received_at, ip, port, validation))

    def _cache_open_states(self):
        """Кэширует, какие SN сейчас открыты."""
        self.open_states_cache = set()
        for item in self.tree.get_children():
            if self.tree.item(item, "open"):
                sn = self.tree.item(item, "text")
                self.open_states_cache.add(sn)

    def _get_sort_key(self, entry, col):
        """Возвращает ключ для сортировки с унификацией типов данных.

        Возвращает кортеж (приоритет_типа, нормализованное_значение):
        - Приоритет 0: дата, IP, порт, валидация (специальная обработка)
        - Приоритет 2: строка (по умолчанию)
        """
        val = ""
        if col == "received_at":
            val = entry.get("received_at", "")
            # Попытка преобразовать в datetime
            try:
                return (0, datetime.fromisoformat(val.replace("Z", "+00:00")))
            except:
                return (2, val)
        elif col == "ip":
            val = entry.get("ip", "")
            # Сортировка IP как кортеж чисел: "192.168.1.10" → (192, 168, 1, 10)
            try:
                parts = [int(x) for x in val.split(".")]
                return (0, tuple(parts))
            except:
                return (2, val.lower())
        elif col == "port":
            val = str(entry.get("port", ""))
            try:
                return (0, int(val))
            except:
                return (2, val.lower())
        elif col == "validation":
            val = str(entry.get("validation", ""))
            # Сортируем "OK" перед "Ошибка"
            priority = 0 if val == "✅" else 1
            return (0, priority)
        else:
            val = str(entry.get(col, ""))
            return (2, val.lower())

    def _get_open_states(self):
        """Возвращает множество SN, которые сейчас открыты."""
        open_sn = set()
        for item in self.tree.get_children():
            if self.tree.item(item, "open"):
                sn = self.tree.item(item, "text")
                open_sn.add(sn)
        return open_sn

    def _restore_open_states(self, open_sn):
        """Восстанавливает открытые состояния по множеству SN."""
        for item in self.tree.get_children():
            sn = self.tree.item(item, "text")
            if sn in open_sn:
                self.tree.item(item, open=True)

    def _sort_by_column(self, col):
        """Сортирует дочерние элементы внутри каждой группы по указанной колонке, сохраняя открытые состояния."""
        # Сохраняем открытые группы
        open_sn = self._get_open_states()

        if self.sorted_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
            self.sorted_column = col

        # Сортируем каждую группу
        for sn in self.sn_groups:
            self.sn_groups[sn].sort(
                key=lambda x: self._get_sort_key(x, col),
                reverse=self.sort_reverse
            )

        # Перестраиваем дерево
        self.clear_tree()

        # Восстанавливаем открытые состояния
        self._restore_open_states(open_sn)

        # Обновляем стрелки в заголовках
        for c in list(self.tree["columns"]) + ["#0"]:
            current_text = self.tree.heading(c, "text")
            if current_text.endswith(" ↑") or current_text.endswith(" ↓"):
                current_text = current_text[:-2]
            if c == col:
                arrow = " ↓" if self.sort_reverse else " ↑"
                current_text += arrow
            self.tree.heading(c, text=current_text)

    def _sort_by_sn(self):
        """Сортирует группы по SN (алфавитно), сохраняя открытые состояния."""
        # Сохраняем открытые группы
        open_sn = self._get_open_states()

        reverse = not (getattr(self, '_sn_sorted_reverse', False))
        self._sn_sorted_reverse = reverse

        items = list(self.sn_groups.items())
        items.sort(key=lambda x: x[0].lower(), reverse=reverse)
        self.sn_groups = dict(items)

        # Перестраиваем дерево
        self.clear_tree()

        # Восстанавливаем открытые состояния
        self._restore_open_states(open_sn)

        # Обновляем стрелку в #0
        current_text = self.tree.heading("#0", "text")
        if " ↑" in current_text or " ↓" in current_text:
            current_text = current_text.split(" ")[0]
        arrow = " ↓" if reverse else " ↑"
        self.tree.heading("#0", text=current_text + arrow)

        # Сбрасываем сортировку по колонкам
        self.sorted_column = None