# Push_Parser.py

import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
import json
import os


def _find_parent(root, child):
    """
    Рекурсивно находит родительский элемент для заданного дочернего элемента в XML-дереве.

    Используется, потому что стандартный xml.etree.ElementTree не предоставляет метод getparent().

    Args:
        root (Element): Корень XML-дерева.
        child (Element): Элемент, для которого ищется родитель.

    Returns:
        Element | None: Родительский элемент или None, если не найден.
    """

    def _iter(parent, target):
        for elem in parent:
            if elem is target:
                return parent
            result = _iter(elem, target)
            if result is not None:
                return result
        return None

    return _iter(root, child) if root is not child else None


def extract_obis_values_and_invoke_id(xml_str: str) -> Dict[str, Any]:
    """
    Парсит XML-представление DLMS DataNotification и извлекает:
      - Invoke ID из <LongInvokeIdAndPriority>
      - Список OBIS-кодов и соответствующих значений из основного массива
      - Обрабатывает значения как простые типы или структуры

    Особенности:
      - Первому OBIS-коду всегда присваивается пустое значение ("")
      - Значения начинаются со второго OBIS-кода
      - Поддерживаются вложенные структуры и массивы

    Args:
        xml_str (str): XML-строка, полученная от GXDLMSTranslator.

    Returns:
        dict: Словарь с ключами:
            - 'invoke_id': int | None — идентификатор вызова
            - 'records': list — список записей вида:
                {
                    "obis": "0.0.25.9.0.255",
                    "value": { ... },  # объект с типом и значением
                    "comment": "Push1"
                }
            - 'extra_structures': list — зарезервировано (не используется в текущей версии)

    Raises:
        ValueError: Если XML некорректен.
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}")

    result = {
        "invoke_id": None,
        "records": [],
        "extra_structures": []  # зарезервировано для будущего расширения
    }

    # === 1. Извлечение Invoke ID ===
    long_invoke = root.find(".//LongInvokeIdAndPriority")
    if long_invoke is not None:
        hex_val = long_invoke.get("Value", "")
        if hex_val:
            # Очищаем от не-hex символов и приводим к верхнему регистру
            clean = ''.join(c for c in hex_val.upper() if c in "0123456789ABCDEF")
            if len(clean) >= 8:
                # Первые 2 символа — байт приоритета, остальное — invoke ID
                invoke_hex = clean[2:]
                try:
                    result["invoke_id"] = int(invoke_hex, 16)
                except ValueError:
                    pass  # игнорируем ошибки парсинга

    # === 2. Поиск массива OBIS-структур ===
    # Находим первый Array внутри DataValue/Structure — это всегда массив OBIS-структур
    obis_array = root.find(".//DataValue/Structure/Array")
    if obis_array is None:
        return result  # если массив не найден — возвращаем пустой результат

    # Извлекаем OBIS-коды и комментарии
    obis_entries = []
    for struct in obis_array.findall("Structure"):
        octet = struct.find("OctetString")
        if octet is None:
            continue
        hex_val = octet.get("Value", "")
        comment = ""
        # Извлекаем комментарий из текста (<!-- ... -->)
        if octet.text and "<!--" in octet.text:
            comment = octet.text.strip().replace("<!--", "").replace("-->", "").strip()
        # Или из дочерних элементов (если Gurux использует <Comment>)
        elif list(octet):
            for c in octet:
                if 'Comment' in c.tag:
                    comment = (c.text or "").strip()

        # Преобразуем hex OBIS в точечную нотацию A.B.C.D.E.F
        if len(hex_val) == 12:  # 6 байт = 12 hex-символов
            try:
                parts = [int(hex_val[i:i + 2], 16) for i in range(0, 12, 2)]
                obis_dot = ".".join(str(p) for p in parts)
            except ValueError:
                obis_dot = hex_val  # оставляем как есть при ошибке
        else:
            obis_dot = hex_val

        obis_entries.append({"obis": obis_dot, "hex": hex_val, "comment": comment})

    # === 3. Нахождение родительского Structure и элементов после массива ===
    parent_struct = _find_parent(root, obis_array)
    if parent_struct is None:
        # Если родитель не найден — заполняем заглушками
        result["records"] = [
            {"obis": e["obis"], "value": "[no data]", "comment": e["comment"]}
            for e in obis_entries
        ]
        return result

    # Получаем все дочерние элементы родителя
    all_children = list(parent_struct)
    try:
        idx = all_children.index(obis_array)
        elements_after = all_children[idx + 1:]  # всё, что после массива
    except ValueError:
        elements_after = []

    # === 4. Подготовка к обработке значений ===
    # Первому OBIS всегда пустое значение → значений на 1 меньше, чем OBIS-кодов
    expected_values = max(0, len(obis_entries) - 1)
    values = []
    extra = []  # элементы, не вошедшие в основной список (например, доп. метаданные)

    def _parse_xml_element_value(elem):
        """
        Рекурсивно парсит XML-элемент и возвращает унифицированное представление
        с указанием типа данных и всех возможных интерпретаций значения.

        Поддерживаемые типы:
          - Enum, UInt16/32, Int8, OctetString
          - Structure, Array (рекурсивно)

        Для OctetString дополнительно:
          - пытается распознать OBIS-код (если 12 hex-символов)
          - пытается декодировать как ASCII-строку

        Args:
            elem (Element): XML-элемент для парсинга.

        Returns:
            dict: Объект с полями:
                - "type": имя тега (например, "UInt16")
                - "value": исходное hex-значение
                - опционально: "decimal", "ascii", "obis" и др.
        """
        tag = elem.tag
        result_elem = {"type": tag}

        if tag == "Enum":
            result_elem["value"] = elem.get("Value", "")
        elif tag == "OctetString":
            hex_val = elem.get("Value", "")
            result_elem["value"] = hex_val
            # Попытка распознать OBIS (6 байт = 12 hex-символов)
            if len(hex_val) == 12:
                try:
                    parts = [int(hex_val[i:i + 2], 16) for i in range(0, 12, 2)]
                    result_elem["obis"] = ".".join(str(p) for p in parts)
                except:
                    pass
            # Попытка декодировать как ASCII
            try:
                ascii_val = bytes.fromhex(hex_val).decode('ascii')
                result_elem["ascii"] = ascii_val
            except:
                pass
        elif tag == "UInt32":
            hex_val = elem.get("Value", "")
            result_elem["value"] = hex_val
            try:
                num = int(hex_val, 16)
                result_elem["decimal"] = str(num)
            except:
                pass
        elif tag == "UInt16":
            hex_val = elem.get("Value", "")
            result_elem["value"] = hex_val
            try:
                result_elem["decimal"] = str(int(hex_val, 16))
            except:
                pass
        elif tag == "UInt8":
            hex_val = elem.get("Value", "")
            result_elem["value"] = hex_val
            try:
                result_elem["decimal"] = str(int(hex_val, 16))
            except:
                pass
        elif tag == "Int8":
            hex_val = elem.get("Value", "")
            result_elem["value"] = hex_val
            try:
                num = int(hex_val, 16)
                # Обработка signed int8
                if num > 127:
                    num -= 256
                result_elem["decimal"] = str(num)
            except:
                pass
        elif tag == "Structure":
            qty = elem.get("Qty", "0")
            fields = []
            for child in elem:
                fields.append(_parse_xml_element_value(child)) # Используем рекурсию для нахождения значений в структурах
            result_elem["qty"] = qty
            result_elem["fields"] = fields
        elif tag == "Array":
            qty = elem.get("Qty", "0")
            items = []
            for child in elem:
                items.append(_parse_xml_element_value(child)) # Используем рекурсию для нахождения значений в массивах
            result_elem["qty"] = qty
            result_elem["items"] = items
        else:
            result_elem["value"] = f"[{tag}]"

        return result_elem

    # === 5. Обработка элементов после массива ===
    for i, elem in enumerate(elements_after):
        if i < expected_values:
            value = _parse_xml_element_value(elem)
            values.append(value)
        else:
            # Элементы, не относящиеся к основным значениям (например, подпись)
            extra.append(elem)

    # === 6. Формирование финального списка записей ===
    for i, entry in enumerate(obis_entries):
        if i == 0:
            # Первому OBIS всегда пустое значение (по спецификации push-сообщения)
            value = {"type": "Empty", "value": ""}
        else:
            # Со второго OBIS — берём значения из списка со смещением -1
            value = values[i - 1] if (i - 1) < len(values) else {"type": "Missing", "value": "[missing]"}
        result["records"].append({
            "obis": entry["obis"],
            "value": value,
            "comment": entry["comment"]
        })

    return result


def _parse_dlms_datetime(hex_str: str) -> str:
    """Преобразует hex-строку DLMS DateTime в ISO 8601 с таймзоной."""
    b = bytes.fromhex(hex_str)
    if len(b) < 12:
        raise ValueError("Invalid DLMS DateTime length")

    year = int.from_bytes(b[0:2], 'big')
    month = b[2]
    day = b[3]
    hour = b[5]
    minute = b[6]
    second = b[7]
    deviation_bytes = b[9:11]  # signed int16, в минутах от UTC
    deviation = int.from_bytes(deviation_bytes, 'big', signed=True)

    tz = timezone(timedelta(minutes=deviation)) if deviation != 0x8000 else timezone.utc
    dt = datetime(year, month, day, hour, minute, second, tzinfo=tz)
    return dt.isoformat()


def _hex_to_ascii(hex_str: str) -> str:
    """Преобразует hex-строку в ASCII (если возможно)."""
    try:
        return bytes.fromhex(hex_str).decode('ascii')
    except:
        return hex_str


def is_new_style_push(xml_str: str) -> bool:
    """
    Определяет, является ли push-сообщение нового типа:
      - В NotificationBody/DataValue есть Structure
      - Первый дочерний элемент этой Structure — OctetString
      - Длина hex-значения OctetString != 12 (т.е. не OBIS)
        (обычно 32+ символов — ASCII-имя вроде "PEN...")
    """
    try:
        root = ET.fromstring(xml_str)
        # Находим корневую Structure внутри DataValue
        data_value = root.find(".//NotificationBody/DataValue")
        if data_value is None:
            return False

        # Ищем первый Structure на любом уровне внутри DataValue
        structure = None
        for elem in data_value.iter():
            if elem.tag == "Structure":
                structure = elem
                break

        if structure is None:
            return False

        children = list(structure)
        if not children:
            return False

        first = children[0]
        if first.tag != "OctetString":
            return False

        hex_val = first.get("Value", "")
        # Если длина != 12 — это НЕ OBIS → значит, это logical name → новый тип
        if len(hex_val) != 12:
            return True

        # Дополнительная проверка: если длина 12, но содержит не-цифры/буквы A-F → маловероятно, но всё же
        # Но основное правило: OBIS всегда 12 hex символов.
        return False

    except Exception:
        return False

def parse_dlms_push_xml(xml_str: str) -> Dict[str, Any]:
    """
    Парсит XML и возвращает унифицированный словарь.
    Для day-push: { "type": "day_push", "invoke_id": ..., "logical_name": ..., "data": [...] }
    Для OBIS-push: { "type": "obis_push", "invoke_id": ..., "records": [...] }
    """
    if is_new_style_push(xml_str):
        result = parse_new_style_push(xml_str)
        result["type"] = "day_push"
    else:
        result = extract_obis_values_and_invoke_id(xml_str)
        result["type"] = "obis_push"
    return result

def parse_new_style_push(xml_str: str) -> Dict[str, Any]:
    root = ET.fromstring(xml_str)

    # === Извлечение Invoke ID (как в extract_obis_values_and_invoke_id) ===
    invoke_id = None
    long_invoke = root.find(".//LongInvokeIdAndPriority")
    if long_invoke is not None:
        hex_val = long_invoke.get("Value", "")
        if hex_val:
            clean = ''.join(c for c in hex_val.upper() if c in "0123456789ABCDEF")
            if len(clean) >= 8:
                invoke_hex = clean[2:]
                try:
                    invoke_id = int(invoke_hex, 16)
                except ValueError:
                    pass

    data_value = root.find(".//NotificationBody/DataValue")
    structure = None
    for child in data_value:
        if child.tag == "Structure":
            structure = child
            break
    if structure is None:
        raise ValueError("No root Structure in DataValue")

    children = list(structure)
    logical_name_hex = children[0].get("Value", "")
    logical_name = _hex_to_ascii(logical_name_hex)

    array_elem = children[1]
    data_entries = []

    for struct_elem in array_elem.findall("Structure"):
        struct_children = list(struct_elem)
        if not struct_children:
            continue

        date_octet = struct_children[0]
        if date_octet.tag != "OctetString":
            continue
        try:
            timestamp_iso = _parse_dlms_datetime(date_octet.get("Value", ""))
        except:
            continue

        values = []
        for val_elem in struct_children[1:]:
            if val_elem.tag == "UInt32":
                try:
                    values.append(int(val_elem.get("Value", "0")))
                except:
                    values.append(0)

        data_entries.append({
            "timestamp": timestamp_iso,
            "values": values
        })

    return {
        "type": "day_push",  # метка типа
        "invoke_id": invoke_id,  # ← добавлено
        "logical_name": logical_name,
        "data": data_entries
    }

def get_current_json_filename(output_dir: str = ".") -> str:
    """Генерирует полный путь к файлу dlms_push_YYYY-MM-DD.json."""
    filename = f"dlms_push_{datetime.now().strftime('%Y-%m-%d')}.json"
    return os.path.join(output_dir, filename)


def get_current_day_json_filename(output_dir: str = ".") -> str:
    """Генерирует полный путь к файлу dlms_day_push_YYYY-MM-DD.json."""
    filename = f"dlms_day_push_{datetime.now().strftime('%Y-%m-%d')}.json"
    return os.path.join(output_dir, filename)


def get_current_autoconnect_filename(output_dir: str = ".") -> str:
    """Генерирует полный путь к файлу autoconnect_YYYY-MM-DD.json."""
    filename = f"autoconnect_{datetime.now().strftime('%Y-%m-%d')}.json"
    return os.path.join(output_dir, filename)


def append_to_json_file(data: Dict[str, Any], filename: str):
    """
    Добавляет запись в JSON-файл (создаёт директорию, если нужно).
    """
    os.makedirs(os.path.dirname(filename), exist_ok=True)  # ← создаём папку, если не существует

    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                records = json.load(f)
                if not isinstance(records, list):
                    records = []
            except json.JSONDecodeError:
                records = []
    else:
        records = []

    records.append(data)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def process_dlms_message(xml_str: str) -> dict:
    """Фасад-функция для обработки любого типа DLMS push-сообщения."""
    if is_new_style_push(xml_str):
        result = parse_new_style_push(xml_str)
        result["type"] = "day_push"
    else:
        result = extract_obis_values_and_invoke_id(xml_str)
        result["type"] = "obis_push"
    return result