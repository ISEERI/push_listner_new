# json_viewer_tables/autoconnect.py

from json_viewer_tables.base_display_analyze import BaseDisplay
from utils import _format_datetime


class AutoConnectDisplay(BaseDisplay):
    """
    Класс для отображения списка автоконнектов в табличной форме (плоский список).

    Наследуется от BaseDisplay, который предоставляет общую логику работы с ttk.Treeview.
    Предназначен для отображения данных типа "autoconnect", сохранённых в JSON-файлах.
    """

    def display(self, data: list):
        # Очищаем существующее содержимое таблицы
        self.clear_tree()

        # Устанавливаем режим отображения: только заголовки колонок (без иерархии)
        # Это важно, чтобы не отображался первый столбец (#0) как в дереве
        self.tree.configure(show="headings")

        # Определяем имена внутренних колонок (используются для идентификации в Treeview)
        columns = ("received_at", "sn", "ip", "port")

        # Определяем заголовки, отображаемые пользователю
        headings = ["Дата получения", "SN", "IP", "Порт"]

        # Настраиваем колонки: ширины заданы в пикселях
        # Порядок ширины соответствует порядку колонок:
        #   received_at — 150px, sn — 80px, ip — 100px, port — 60px
        self.setup_columns(columns, headings, [150, 80, 100, 60])

        # Проходим по всем записям и добавляем их в таблицу
        for entry in data:
            # Форматируем timestamp в человекочитаемый вид (например, "22.01.2026 12:00:00")
            received_at = _format_datetime(entry.get("received_at", ""))

            # Вставляем строку в таблицу с четырьмя значениями в порядке колонок
            self.insert_row((
                received_at,  # Отформатированная дата/время
                entry.get("sn", ""),  # Серийный номер (если отсутствует — пустая строка)
                entry.get("ip", ""),  # IP-адрес
                entry.get("port", "")  # Порт
            ))