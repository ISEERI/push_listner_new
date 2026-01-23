# json_viewer_tables/base_display.py

import tkinter as tk
from tkinter import ttk
from datetime import datetime


class BaseDisplay:
    """
    Базовый класс для отображения табличных данных в ttk.Treeview.

    Предоставляет общую функциональность:
    - Очистка таблицы
    - Настройка колонок с автоматической сортировкой
    - Вставка строк
    - Универсальный механизм сортировки с поддержкой разных типов данных

    Наследуется всеми конкретными классами отображения (AutoConnectDisplay,
    ObisPushDisplay, DayPushDisplay и т.д.).
    """

    def __init__(self, tree: ttk.Treeview, parent_window):
        self.tree = tree
        self.parent_window = parent_window
        self.sorted_column = None  # Текущая колонка сортировки
        self.sort_reverse = False  # Направление сортировки (False = по возрастанию)

    def clear_tree(self):
        """Очищает все строки из Treeview, сохраняя структуру колонок."""
        for item in self.tree.get_children():
            self.tree.delete(item)

    def setup_columns(self, columns, headings, widths=None):
        """
        Настраивает колонки Treeview с автоматической привязкой сортировки.

        Args:
            columns: Список внутренних имён колонок (используются как ключи)
            headings: Список заголовков, отображаемых пользователю
            widths: Список ширин колонок в пикселях (опционально)
        """
        self.tree["columns"] = columns
        for i, col in enumerate(columns):
            heading_text = headings[i]
            # Привязываем обработчик сортировки к клику по заголовку
            self.tree.heading(
                col,
                text=heading_text,
                anchor=tk.W,
                command=lambda c=col: self._sort_tree_column(c)
            )
            if widths and i < len(widths):
                self.tree.column(col, width=widths[i], minwidth=50, anchor=tk.W)
            else:
                self.tree.column(col, width=100, minwidth=50, anchor=tk.W)

    def _sort_tree_column(self, col: str):
        """
        Универсальный метод сортировки колонок с интеллектуальным определением типа данных.

        Поддерживает сортировку:
        - Дат и времени (формат "дд.мм.гггг чч:мм:сс")
        - Чисел (с поддержкой запятой как десятичного разделителя)
        - Строк (регистронезависимо)
        - Пустых значений (перемещаются в конец)

        Группы сортировки (в порядке приоритета):
        0 - даты/время
        1 - числа
        2 - строки
        3 - пустые значения
        """
        # Переключение направления сортировки
        if self.sorted_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
            self.sorted_column = col

        # Получение всех строк и их значений в указанной колонке
        data = [(self.tree.set(item, col), item) for item in self.tree.get_children()]

        def sort_key(x):
            """Определяет ключ сортировки с унификацией типов данных."""
            val = x[0]

            # Группа 3: пустые значения (идут в конец)
            if not val or val == "":
                return (3, "")

            # Группа 1: числа (поддержка запятой как десятичного разделителя)
            try:
                num_val = float(val.replace(',', '.'))
                return (1, num_val)
            except ValueError:
                pass

            # Группа 0: даты формата "дд.мм.гггг чч:мм:сс"
            try:
                if len(val) >= 19 and '.' in val and ':' in val:
                    dt = datetime.strptime(val[:19], '%d.%m.%Y %H:%M:%S')
                    return (0, dt)
            except ValueError:
                pass

            # Группа 2: строки (регистронезависимо)
            return (2, val.lower())

        # Сортировка данных
        data.sort(key=sort_key, reverse=self.sort_reverse)

        # Перемещение строк в новом порядке
        for index, (val, item) in enumerate(data):
            self.tree.move(item, '', index)

        # Обновление визуальных индикаторов сортировки (стрелки ↑/↓)
        for c in self.tree["columns"]:
            current_text = self.tree.heading(c, "text")
            # Удаление существующих стрелок
            if current_text.endswith(" ↑") or current_text.endswith(" ↓"):
                current_text = current_text[:-2]
            # Добавление стрелки для текущей колонки сортировки
            if c == col:
                new_text = current_text + (" ↓" if self.sort_reverse else " ↑")
            else:
                new_text = current_text
            self.tree.heading(c, text=new_text)

    def insert_row(self, values: tuple):
        """Вставляет новую строку в конец таблицы."""
        self.tree.insert("", "end", values=values)


