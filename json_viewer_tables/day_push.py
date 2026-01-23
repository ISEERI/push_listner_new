# table_display/day_push.py
from json_viewer_tables.base_display_analyze import BaseDisplay
from utils import _format_datetime, classify_day_push_entry, validate_day_push_intervals


class DayPushDisplay(BaseDisplay):
    """
    Класс для отображения новых типов DLMS push-сообщений (day push) в табличной форме.

    Особенности:
    - Отображает сводную информацию о профиле нагрузки
    - Показывает тип профиля и результат валидации периодичности
    - Предоставляет краткое представление временных меток данных

    Используется при выборе режима "Пуши профилей" в интерфейсе JSON Viewer.
    """

    def display(self, data: list):
        # Очищаем существующее содержимое таблицы
        self.clear_tree()

        # Устанавливаем режим отображения: только заголовки (без иерархии)
        self.tree.configure(show="headings")

        # Определяем структуру таблицы
        columns = ("received_at", "invoke_id", "logical_name", "profile_type", "valid", "data_records")
        headings = ["Получено", "Invoke ID", "Логическое имя", "Тип", "Валидность", "Данные"]
        widths = [150, 80, 150, 90, 80, 250]  # Ширины колонок в пикселях

        # Настраиваем колонки с автоматической сортировкой
        self.setup_columns(columns, headings, widths)

        # Обработка каждой записи
        for entry in data:
            # Форматирование времени получения сообщения
            received_at = _format_datetime(entry.get("received_at", ""))

            # Извлечение основных атрибутов
            logical_name = entry.get("logical_name", "")
            invoke_id = entry.get("invoke_id", "")

            # Определение типа профиля (суточный или получасовой)
            profile_type = classify_day_push_entry(entry)
            profile_label = {
                "daily": "Суточный профиль",
                "half_hourly": "Профиль энергии 1"
            }.get(profile_type, "???")  # "???" для неизвестных типов

            # Валидация периодичности записей в профиле
            is_valid = validate_day_push_intervals(entry, profile_type)
            valid_icon = "✅" if is_valid else "❌"  # Визуальные индикаторы

            # Формирование краткого представления данных профиля
            records = entry.get("data", [])
            if not records:
                data_str = "[Нет данных]"
            else:
                # Извлекаем и форматируем все временные метки
                timestamps = [_format_datetime(r.get("timestamp", "")) for r in records]
                summary = ", ".join(timestamps)
                data_str = summary

            # Вставка строки в таблицу
            self.insert_row((
                received_at,  # Отформатированное время получения
                invoke_id,  # Invoke ID
                logical_name,  # Логическое имя устройства
                profile_label,  # Человекочитаемый тип профиля
                valid_icon,  # Результат валидации (✅/❌)
                data_str  # Сводка временных меток данных
            ))