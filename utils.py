# utils.py
import re
from datetime import datetime, timedelta
from typing import Dict, Any

from gurux_dlms import _GXFCS16

# === Словари ===

# Сопоставление классов DLMS по их числовому ID
CLASS_NAMES = {
    1: "Data", 3: "Register", 7: "ProfileGeneric", 18: "ImageTransfer",
    23: "IecHdlcSetup", 9: "ScriptTable", 11: "SpecialDaysTable",
    20: "ActivityCalendar", 6: "RegisterActivation", 22: "ActionSchedule",
    45: "GprsSetup", 29: "AutoConnect", 70: "DisconnectControl",
    71: "Limiter", 40: "PushSetup", 41: "TcpUdpSetup", 42: "Ip4Setup",
    47: "GSMDiagnostic", 64: "SecuritySetup", 124: "CommunicationPortProtection"
}

# Известные OBIS-коды с человекочитаемыми именами (можно дополнять)
OBIS_NAMES = {
    "0100620000FF": "Clock", "0000190900FF": "Push1", "0000290900FF": "Push2",
    "0000390900FF": "Push3", "0000A90900FF": "Push4", "0000B90900FF": "Push5",
}

# Словарь событий для OBIS 0.0.97.98.0.255
EVENT_DESCRIPTIONS = {
    0: "Событие в журнале самодиагностики",
    1: "Прерывание напряжения (согласно ГОСТ 32144-2013)",
    2: "Событие в журнале параметров качества сети",
    3: "Воздействие магнитного поля - начало",
    4: "Вскрытие клеммной крышки - начало",
    5: "Вскрытие корпуса - начало",
    6: "Превышение лимита активной мощности",
    7: "Сработка реле по максимальному току",
    8: "Сработка реле по магнитному полю",
    9: "Сработка реле по максимальному напряжению",
    10: "Сработка реле по небалансу токов",
    11: "Сработка реле по превышению температуры",
    12: "Изменение состояние дискретных входов",
    13: "Событие в журнале программирования",
    14: "Небаланс токов - начало",
    15: "Сработка реле по матрице событий",
    16: "Возврат реле в замкнутое состояние",
    17: "Нештатная ситуация (обрыв) нейтрального провода низкого напряжения с глухозаземленной нейтралью",
    18: "Нештатная ситуация (обрыв или КЗ) фазных проводов низкого напряжения с глухозаземленной нейтралью",
    19: "Нештатная ситуация (обрыв) фазных проводов в сети среднего напряжения с изолированной нейтралью",
    20: "Прерывание напряжения более 10 часов (согласно ГОСТ 32144-2013)",
    21: "Резерв СПОДЭС",
    22: "Резерв СПОДЭС",
    23: "Резерв СПОДЭС",
    24: "Воздействие магнитного поля - окончание",
    25: "Вскрытие клеммной крышки - окончание",
    26: "Вскрытие корпуса - окончание",
    27: "Небаланс токов - окончание",
    28: "Резерв",
    29: "Резерв",
    30: "Резерв",
    31: "Резерв"
}

AUTOCONNECT_PATTERN = re.compile(r'<sn=(\S+)\s+ip=([\d.]+)\s+pt=(\d+)>')

def _format_datetime(dt_str: str) -> str:
    """Преобразует ISO-8601 в 'дд.мм.гггг чч:мм:сс'."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y %H:%M:%S')
    except Exception:
        return dt_str

def classify_day_push_entry(entry: Dict[str, Any]) -> str:
    data = entry.get("data", [])
    if not data:
        return "unknown"
    first_values = data[0].get("values", [])
    if len(first_values) == 20:
        return "daily"
    elif len(first_values) == 4:
        return "half_hourly"
    else:
        return "unknown"

def validate_day_push_intervals(entry: Dict[str, Any], profile_type: str) -> bool:
    """
    Валидирует периодичность записей в профиле нагрузки (day push).

    Проверяет, что интервалы между последовательными записями соответствуют ожидаемым:
    - Для суточного профиля (daily): ровно 24 часа
    - Для получасового профиля (half_hourly): ровно 30 минут

    Args:
        entry: Словарь с данными профиля, содержащий ключ 'data' со списком записей
        profile_type: Тип профиля ('daily' или 'half_hourly')

    Returns:
        bool: True если все интервалы корректны, False если найдено нарушение

    Особенности:
    - Автоматически сортирует временные метки перед проверкой
    - Обрабатывает ISO 8601 формат с временной зоной
    - Возвращает True для профилей с менее чем 2 записями (нечего проверять)
    """
    data = entry.get("data", [])
    if len(data) < 2:
        return True

    try:
        # Определение ожидаемого интервала
        expected_delta = timedelta(days=1) if profile_type == "daily" else timedelta(minutes=30)

        # Парсинг и сортировка временных меток
        timestamps = []
        for record in data:
            ts_str = record.get("timestamp", "")
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            timestamps.append(dt)
        timestamps.sort()

        # Проверка каждого интервала
        for i in range(1, len(timestamps)):
            if timestamps[i] - timestamps[i - 1] != expected_delta:
                return False
        return True
    except Exception:
        # При любой ошибке парсинга или обработки считаем профиль недействительным
        return False


def calculate_fcs(data: bytes) -> int:
    """Расчёт FCS для HDLC-фреймов."""
    if _GXFCS16 is not None:
        return _GXFCS16.countFCS16(data, 0, len(data))
    else:
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc

def bytes_to_hex_display(data: bytes) -> str:
    """Форматирует байты для отображения."""
    return ' '.join(f'{b:02X}' for b in data)