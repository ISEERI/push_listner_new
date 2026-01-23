# message_processor.py
import re
from datetime import datetime
from typing import Callable

from gurux_dlms import GXByteBuffer
from DLMS_Parser import hdlc_to_enhanced_xml, extract_dlms_request_info, bytes_to_hex_str
from utils import calculate_fcs

# Autoconnect pattern moved here
AUTOCONNECT_PATTERN = re.compile(r'<sn=(\S+)\s+ip=([\d.]+)\s+pt=(\d+)>')


class MessageProcessor:
    """Обработка входящих сообщений и генерация ответов."""

    def __init__(self, on_dlms_push=None, on_autoconnect=None, logger: Callable[[str], None] = None):

        self.on_dlms_push = on_dlms_push
        self.on_autoconnect = on_autoconnect
        self.logger = logger

    def process_message(self, raw_data, client_info=None, local_port=None):
        """
        Обрабатывает любое входящее сообщение.
        Возвращает ответ (bytes) или None.
        """
        port_info = f" (port {local_port})" if local_port else ""

        # Проверка autoconnect
        if self._is_autoconnect(raw_data, port_info):
            return None

        # Проверка DLMS
        if not self._is_dlms_frame(raw_data):
            # Логирование не-DLMS сообщения
            try:
                text_msg = raw_data.decode('utf-8', errors='replace')
            except:
                import binascii
                text_msg = f"[Non-text data: {binascii.hexlify(raw_data[:32]).decode()}...]"
            self.logger(f"[TEXT]{port_info} Получено не-DLMS сообщение: {text_msg}")
            return None

        # Обработка DLMS
        return self._process_dlms_frame(raw_data, client_info, port_info)

    def _is_autoconnect(self, raw_data, port_info):
        """Проверяет и обрабатывает autoconnect-сообщения."""
        try:
            text_msg = raw_data.decode('utf-8', errors='replace')
            match = AUTOCONNECT_PATTERN.search(text_msg)
            if match:
                sn, ip, port_str = match.groups()
                if self.on_autoconnect:
                    self.on_autoconnect(sn, ip, int(port_str))
                self.logger(f"[Autoconnect]{port_info} <sn={sn} ip={ip} pt={port_str}>")
                return True
        except:
            pass
        return False

    def _is_dlms_frame(self, raw_data):
        """Проверяет, является ли сообщение DLMS-фреймом."""
        return raw_data and raw_data[0] == 0x7E

    def _process_dlms_frame(self, raw_data, client_info, port_info):
        """Обрабатывает DLMS-фрейм и генерирует ответ."""
        try:
            # Логирование получения пакета
            hex_display = bytes_to_hex_str(raw_data)
            self.logger(f"[→]{port_info} Получен пакет ({len(raw_data)} байт):\n{hex_display}")

            if len(raw_data) < 10:
                self.logger("[!] Слишком короткий пакет")
                return None

            # Парсинг XML
            xml_output = hdlc_to_enhanced_xml(raw_data)
            self.logger(f"\n[XML]{port_info} Расшифровка входящего пакета:\n{xml_output}")

            if self.on_dlms_push:
                self.on_dlms_push(xml_output, client_info, port_info)

            # Извлечение адресной информации
            your_addr = raw_data[3:4]
            meter_addr = raw_data[4:8]
            self.logger(f"[✓]{port_info} Ваш адрес: {bytes_to_hex_str(your_addr)}")
            self.logger(f"[✓]{port_info} Адрес счётчика: {bytes_to_hex_str(meter_addr)}")

            address_field = meter_addr + your_addr
            self.logger(f"[✓]{port_info} Address Field ответа: {bytes_to_hex_str(address_field)}")

            # Извлечение invoke_id
            info = extract_dlms_request_info(xml_output)
            if not info or not info.get('invoke_id'):
                self.logger("[!] Не удалось извлечь invoke_id из XML")
                return None

            invoke_hex = info['invoke_id'].upper()
            invoke_clean_hex = invoke_hex[2:].zfill(8) if len(invoke_hex) >= 8 else invoke_hex.zfill(8)
            invoke_dec = int(invoke_hex.replace(" ", ""), 16)
            self.logger(f"[✓]{port_info} Invoke ID: {invoke_hex} -> {invoke_dec}")

            # Генерация ответа
            response = self._generate_response(address_field, invoke_clean_hex)
            if response:
                resp_hex = bytes_to_hex_str(response)
                self.logger(f"[←]{port_info} Отправлен ответ ({len(response)} байт):\n{resp_hex}")

            return response

        except Exception as e:
            self.logger(f"[ERROR] Ошибка обработки DLMS: {e}")
            import traceback
            self.logger(traceback.format_exc())
            return None

    def _generate_response(self, address_field, invoke_clean_hex):
        """Генерирует подтверждающий ответ на DLMS-фрейм."""
        try:
            now = datetime.now()
            bb = GXByteBuffer()
            bb.setUInt8(0x10)
            for b in bytes.fromhex(invoke_clean_hex):
                bb.setUInt8(b)

            bb.setUInt8(0x0C)
            bb.setUInt8((now.year >> 8) & 0xFF)
            bb.setUInt8(now.year & 0xFF)
            bb.setUInt8(now.month)
            bb.setUInt8(now.day)
            bb.setUInt8(0xFF)
            bb.setUInt8(now.hour)
            bb.setUInt8(now.minute)
            bb.setUInt8(now.second)
            bb.setUInt8(0xFF)
            bb.setUInt8(0xFF)
            bb.setUInt8(0x4C)
            bb.setUInt8(0x00)
            bb.setUInt8(0x00)

            pdu_response = bb.array()
            control_byte = b'\xA0'
            fixed_prefix = b'\x13'
            llc = b'\xE6\xE7\x00'
            information_field = fixed_prefix + llc + pdu_response

            length = len(address_field + information_field) + 6
            fcs_handler = calculate_fcs(control_byte + bytes([length]) + address_field + fixed_prefix).to_bytes(2,
                                                                                                                'big')
            payload = address_field + fixed_prefix + fcs_handler + llc + pdu_response

            data_for_fcs = control_byte + bytes([length]) + payload
            fcs = calculate_fcs(data_for_fcs).to_bytes(2, 'big')

            frame = bytearray([0x7E, 0xA0, length])
            frame.extend(payload)
            frame.extend(fcs)
            frame.append(0x7E)
            return bytes(frame)

        except Exception as e:
            self.logger(f"[!] Ошибка генерации ответа: {e}")
            return None