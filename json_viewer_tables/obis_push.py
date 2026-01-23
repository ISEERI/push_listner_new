# table_display/obis_push.py

from json_viewer_tables.base_display_analyze import BaseDisplay
from utils import _format_datetime
from utils import EVENT_DESCRIPTIONS  # Словарь описаний событий для битовой маски


class ObisPushDisplay(BaseDisplay):
    """
    Класс для отображения стандартных DLMS push-сообщений с OBIS-кодами в табличной форме.

    Особенности:
    - Обрабатывает сложные структуры данных (Structure, Array)
    - Специальная обработка битовой маски событий (OBIS 0.0.97.98.0.255)
    - Преобразует технические значения в человекочитаемый формат
    - Объединяет все OBIS-записи в одну строку для компактного отображения

    Используется при выборе режима "Стандартные пуши" в интерфейсе JSON Viewer.
    """

    def display(self, data: list):
        # Очищаем существующее содержимое таблицы
        self.clear_tree()

        # Устанавливаем режим отображения: только заголовки (без иерархии)
        self.tree.configure(show="headings")

        # Определяем структуру таблицы
        columns = ("received_at", "invoke_id", "obis_values", "comment")
        headings = ["Получено", "Invoke ID", "OBIS и значения", "Комментарии"]
        # Ширины колонок оптимизированы под содержимое
        self.setup_columns(columns, headings, [150, 80, 400, 100])

        # Обработка каждой записи
        for entry in data:
            # Форматирование времени получения сообщения
            received_at = _format_datetime(entry.get("received_at", ""))
            invoke_id = entry.get("invoke_id", "")

            # Обработка всех OBIS-записей в текущем сообщении
            obis_list = []
            for record in entry.get("records", []):
                obis = record.get("obis", "")
                value_obj = record.get("value", {})

                # Преобразование значения в строку с помощью вспомогательной функции
                value_str = _format_value(value_obj)

                # Специальная обработка битовой маски событий (OBIS 0.0.97.98.0.255)
                if obis == "0.0.97.98.0.255":
                    hex_val = value_obj.get("value", "")
                    # Проверка корректной длины (4 байта = 8 hex символов)
                    if len(hex_val) == 8:
                        try:
                            # Преобразование hex-строки в целое число (битовая маска)
                            bitmask = int(hex_val, 16)
                            events = []
                            # Анализ каждого бита (0-31)
                            for bit in range(32):
                                if bitmask & (1 << bit):
                                    # Получение описания события из глобального словаря
                                    desc = EVENT_DESCRIPTIONS.get(bit, f"Неизвестное событие {bit}")
                                    events.append(f"Бит {bit:2d}: {desc}")

                            # Формирование расширенного описания активных событий
                            if events:
                                value_str += "\n Активные события:\n" + "\n".join(f"  • {e}" for e in events)
                            else:
                                value_str = "Нет активных событий"
                        except ValueError:
                            value_str = f"Ошибка парсинга '{hex_val}'"
                    else:
                        value_str = f"Некорректная длина ({len(hex_val)})"

                # Добавление OBIS-записи в список
                obis_list.append(f"{obis}: {value_str}")

            # Объединение всех OBIS-записей в одну строку через точку с запятой
            obis_str = "; ".join(obis_list)

            # Вставка строки в таблицу (колонка "Комментарии" пока не используется)
            self.insert_row((received_at, invoke_id, obis_str, ""))


def _format_value(value_obj) -> str:
    """
    Рекурсивно преобразует объект значения в человекочитаемую строку.

    Поддерживает различные типы данных из DLMS:
    - Простые типы с десятичным представлением
    - ASCII-строки
    - OBIS-коды
    - Сложные структуры (Structure, Array)
    """
    # Защита от некорректных входных данных
    if not isinstance(value_obj, dict):
        return str(value_obj)

    # Приоритетные форматы (десятичное представление предпочтительнее hex)
    if "decimal" in value_obj:
        return value_obj["decimal"]
    elif "ascii" in value_obj:
        return f"ASCII: {value_obj['ascii']}"
    elif "obis" in value_obj:
        return f"OBIS: {value_obj['obis']}"
    # Простое значение без дополнительных представлений
    elif "value" in value_obj and len(value_obj) == 2 and "type" in value_obj:
        return value_obj["value"]

    # Рекурсивная обработка сложных структур
    if value_obj.get("type") == "Structure" and "fields" in value_obj:
        fields = value_obj["fields"]
        formatted = [_format_value(f) for f in fields]
        return f"Struct[{', '.join(formatted)}]"

    if value_obj.get("type") == "Array" and "items" in value_obj:
        items = value_obj["items"]
        formatted = [_format_value(item) for item in items]
        return f"Array[{', '.join(formatted)}]"

    # Fallback для неподдерживаемых форматов
    return str(value_obj)