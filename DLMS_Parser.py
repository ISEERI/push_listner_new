# DLMS_Parser.py

import binascii
import xml.etree.ElementTree as ET
from datetime import datetime
from gurux_dlms import GXDLMSTranslator
from gurux_dlms.enums import TranslatorOutputType

import utils


# === Вспомогательные функции ===

def hex_to_obis(obis_hex: str) -> str:
    """
    Преобразует 12-символьную hex-строку OBIS-кода в точечную нотацию.

    Args:
        obis_hex (str): Hex-строка длиной 12 символов (6 байт), например "0000190900FF".

    Returns:
        str: OBIS в формате "A.B.C.D.E.F", например "0.0.25.9.0.255".
             Если длина не 12 — возвращает исходную строку.
    """
    if len(obis_hex) != 12:
        return obis_hex
    parts = [int(obis_hex[i:i + 2], 16) for i in range(0, 12, 2)]
    return ".".join(map(str, parts))


def try_decode_ascii(hex_str: str) -> str | None:
    """
    Пытается декодировать hex-строку как ASCII.

    Args:
        hex_str (str): Hex-строка без пробелов.

    Returns:
        str | None: Декодированная строка или None в случае ошибки.
    """
    try:
        return binascii.unhexlify(hex_str).decode('ascii')
    except Exception:
        return None


def try_decode_dlms_datetime(hex_str: str) -> str | None:
    """
    Декодирует DLMS-время из hex-строки в человекочитаемый формат.

    Поддерживает:
      - Дату (год, месяц, день)
      - Время (час, минута, секунда)
      - Часовой пояс (deviation)

    Args:
        hex_str (str): Hex-строка длиной от 10 до 24 символов.

    Returns:
        str | None: Строка вида "2026-01-13 14:33:20 UTC-03" или None.
    """
    try:
        if len(hex_str) < 10 or len(hex_str) > 24 or len(hex_str) % 2 != 0:
            return None
        data = binascii.unhexlify(hex_str)
        if len(data) < 5:
            return None

        year = (data[0] << 8) | data[1]
        month = data[2]
        day = data[3]
        hour = data[5] if len(data) > 5 else 0xFF
        minute = data[6] if len(data) > 6 else 0xFF
        second = data[7] if len(data) > 7 else 0xFF

        has_date = (year != 0xFFFF and month != 0xFF and day != 0xFF)
        has_time = (hour != 0xFF and minute != 0xFF and second != 0xFF)

        if not (has_date or has_time):
            return None

        parts = []
        if has_date:
            parts.append(f"{year:04d}-{month:02d}-{day:02d}")
        if has_time:
            parts.append(f"{hour:02d}:{minute:02d}:{second:02d}")

        result = " ".join(parts)

        if len(data) >= 11:
            dev_high = data[9]
            dev_low = data[10]
            dev_raw = (dev_high << 8) | dev_low
            if dev_raw != 0x8000:
                if dev_raw > 32767:
                    dev_raw -= 65536
                if dev_raw != 0:
                    sign = "+" if dev_raw >= 0 else "-"
                    total_min = abs(dev_raw)
                    h, m = divmod(total_min, 60)
                    if m == 0:
                        result += f" UTC{sign}{h:02d}"
                    else:
                        result += f" UTC{sign}{h:02d}:{m:02d}"

        return result
    except Exception:
        return None


def bytes_to_hex_str(data) -> str:
    """
    Преобразует байтовые данные в строку hex с пробелами.

    Args:
        data: bytes, bytearray или list[int].

    Returns:
        str: Строка вида "A0 22 00 02".

    Raises:
        TypeError: Если тип данных не поддерживается.
    """
    if isinstance(data, (bytes, bytearray)):
        return " ".join(f"{b:02X}" for b in data)
    elif isinstance(data, list):
        return " ".join(f"{b:02X}" for b in data if isinstance(b, int))
    else:
        raise TypeError(f"Неподдерживаемый тип: {type(data)}")


def get_current_dlms_datetime_hex() -> str:
    """
    Генерирует текущую дату и время в формате DLMS (hex).

    Используется для формирования ответов.

    Returns:
        str: Hex-строка текущего времени в DLMS-формате.
    """
    now = datetime.now()
    year = now.year
    month = now.month
    day = now.day
    weekday = 0xFF  # не указано
    hour = now.hour
    minute = now.minute
    second = now.second
    hundredths = 0
    before_deviation = 0xFFFF  # signed int16
    deviation = 0x4C  # -180 минут = UTC-03
    clock_status = 0x00

    data = bytearray()
    data.extend(year.to_bytes(2, 'big'))
    data.append(month)
    data.append(day)
    data.append(weekday)
    data.append(hour)
    data.append(minute)
    data.append(second)
    data.append(hundredths)
    data.extend(before_deviation.to_bytes(2, 'big'))  # big-endian!
    data.append(deviation)
    data.append(clock_status)
    return data.hex().upper()


def enhance_xml_element(element: ET.Element) -> None:
    """
    Рекурсивно обогащает XML-элемент комментариями с расшифровкой.

    Модифицирует дерево XML на месте, добавляя ET.Comment с пояснениями.

    Args:
        element (ET.Element): Текущий XML-элемент.
    """
    tag = element.tag
    value = element.get("Value", "")

    if tag == "TargetAddress" and value:
        # Расшифровка TargetAddress как простого числа
        dec = int(value, 16)
        element.append(ET.Comment(f" TargetAddress {dec} "))

    elif tag == "SourceAddress":
        # Расшифровка SourceAddress на logical/physical
        dec = int(value, 16)
        if dec > 0x3FFF:
            logical = int(dec >> 14)
            physical = int(dec & 0x3FFF)
        else:
            logical = int(dec >> 7)
            physical = int(dec & 0x7F)
        element.append(ET.Comment(f" Logical address - {logical}, Physical address - {physical}"))

    elif tag == "ClassId" and value:
        # Замена hex на decimal + имя класса
        try:
            dec = int(value, 16)
            element.set("Value", str(dec))
            class_name = utils.CLASS_NAMES.get(dec)
            if class_name:
                element.append(ET.Comment(f" {class_name} "))
        except ValueError:
            pass

    elif tag == "AttributeId" and value:
        # AttributeId → decimal
        try:
            dec = int(value, 16)
            element.set("Value", str(dec))
        except ValueError:
            pass

    elif tag == "InstanceId" and value:
        # InstanceId → OBIS в точечной нотации
        obis_str = hex_to_obis(value)
        element.set("Value", obis_str)

    elif tag == "LongInvokeIdAndPriority" and value:
        # Расшифровка invoke-id и приоритета
        clean = ''.join(c for c in value.upper() if c in "0123456789ABCDEF")
        if clean and len(clean) >= 8:
            high_byte = clean[:2]
            invoke_id_hex = clean[2:]
            try:
                invoke_id_dec = int(invoke_id_hex, 16)
            except ValueError:
                invoke_id_dec = None

            # Комментарии по приоритету и типу сервиса
            if high_byte == "40":
                priority_comment = "Normal priority."
                confirmed_comment = "Confirmed service."
            elif high_byte == "80":
                priority_comment = "High priority."
                confirmed_comment = "Non-confirmed service."
            elif high_byte == "C0":
                priority_comment = "High priority."
                confirmed_comment = "Confirmed service."
            else:
                priority_comment = f"Priority byte: 0x{high_byte}"
                confirmed_comment = "Service type unknown."

            element.append(ET.Comment(f" {priority_comment} "))
            element.append(ET.Comment(f" {confirmed_comment} "))
            if invoke_id_dec is not None:
                element.append(ET.Comment(f" Invoke ID: {invoke_id_dec} "))

    elif tag == "DateTime" and value:
        # Расшифровка даты/времени
        dt_str = try_decode_dlms_datetime(value)
        if dt_str:
            element.append(ET.Comment(f" {dt_str} "))

    elif tag == "OctetString" and value:
        # Попытка распознать ASCII, OBIS или DateTime
        added = False
        ascii_str = try_decode_ascii(value)
        if ascii_str and ascii_str.isprintable():
            element.append(ET.Comment(f" {ascii_str} "))
            added = True
        else:
            if len(value) == 12:
                try:
                    obis_dot = hex_to_obis(value)
                    comment = f" OBIS: {obis_dot} "
                    name = utils.OBIS_NAMES.get(value.upper())
                    if name:
                        comment += f"({name})"
                    element.append(ET.Comment(comment))
                    added = True
                except Exception:
                    pass
            if not added:
                dt_str = try_decode_dlms_datetime(value)
                if dt_str:
                    element.append(ET.Comment(f" DateTime: {dt_str} "))

    # Рекурсивная обработка дочерних элементов
    for child in element:
        enhance_xml_element(child)


def hdlc_to_enhanced_xml(data_input) -> str:
    """
    Преобразует HDLC-пакет (hex или bytes) в расширенный XML с комментариями.

    Args:
        data_input (str | bytes): Hex-строка или байты HDLC-фрейма.

    Returns:
        str: XML-строка с комментариями.

    Raises:
        ValueError: При некорректных входных данных.
        TypeError: Если тип данных не str или bytes.
    """
    if isinstance(data_input, str):
        clean_hex = data_input.replace(" ", "").replace("-", "").strip()
        if not clean_hex:
            raise ValueError("Пустая hex-строка")
        try:
            data = binascii.unhexlify(clean_hex)
        except binascii.Error as e:
            raise ValueError(f"Некорректный hex: {e}")
    elif isinstance(data_input, bytes):
        data = data_input
    else:
        raise TypeError("Ожидался str (hex) или bytes")

    translator = GXDLMSTranslator()
    translator.outputType = TranslatorOutputType.SIMPLE_XML
    translator.useLogicalNameReferencing = True

    xml_str = translator.messageToXml(data)
    if not xml_str.strip():
        raise ValueError("Пустой XML — пакет не распознан")

    root = ET.fromstring(xml_str)
    enhance_xml_element(root)

    if hasattr(ET, 'indent'):
        ET.indent(root, space="  ")
    rough = ET.tostring(root, encoding='unicode')

    if not rough.startswith('<?xml'):
        rough = '<?xml version="1.0" ?>\n' + rough
    return rough


def extract_dlms_request_info(xml_str: str) -> dict | None:
    """
    Извлекает структурированную информацию из XML-расшифровки.

    Args:
        xml_str (str): XML-строка.

    Returns:
        dict | None: Словарь с ключами:
            - 'target_address': int
            - 'source_address': int
            - 'invoke_id': str (hex)
            - 'has_long_invoke': bool
            - 'attribute_count': int
            - 'high_byte': str
            Или None в случае ошибки.
    """
    try:
        root = ET.fromstring(xml_str)
        info = {
            'target_address': None,
            'source_address': None,
            'invoke_id': None,
            'has_long_invoke': False,
            'attribute_count': 0,
            'high_byte': None
        }

        def search(elem):
            if elem.tag == "TargetAddress":
                val = elem.get("Value", "").strip()
                if val:
                    try:
                        info['target_address'] = int(val, 16) if all(
                            c in "0123456789ABCDEFabcdef" for c in val) else int(val)
                    except:
                        pass
            elif elem.tag == "SourceAddress":
                val = elem.get("Value", "").strip()
                if val:
                    try:
                        info['source_address'] = int(val, 16) if all(
                            c in "0123456789ABCDEFabcdef" for c in val) else int(val)
                    except:
                        pass
            elif elem.tag == "LongInvokeIdAndPriority":
                val = elem.get("Value", "").strip()
                if val:
                    clean = ''.join(c for c in val.upper() if c in "0123456789ABCDEF")
                    if clean and len(clean) >= 8:
                        info['invoke_id'] = clean[2:]
                        info['high_byte'] = clean[:2]
                        info['has_long_invoke'] = True
            elif elem.tag == "AttributeDescriptor":
                info['attribute_count'] += 1
            for child in elem:
                search(child)

        search(root)
        return info
    except Exception:
        return None