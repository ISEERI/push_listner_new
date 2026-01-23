from datetime import datetime
from typing import Dict, Any
from Push_Parser import (
    get_current_json_filename,
    get_current_day_json_filename,
    get_current_autoconnect_filename,
    append_to_json_file
)


class DataSaver:
    """Обработка и сохранение данных в JSON-файлы."""

    def __init__(self, save_dir: str):
        self.save_dir = save_dir

    def save_autoconnect(self, sn: str, ip: str, port: int) -> str:
        """Сохраняет autoconnect-сообщение."""
        filename = get_current_autoconnect_filename(self.save_dir)
        entry = {
            "received_at": datetime.now().isoformat(),
            "sn": sn,
            "ip": ip,
            "port": port
        }
        append_to_json_file(entry, filename)
        return filename

    def save_dlms_push(self, parsed_data: Dict[str, Any]) -> str:
        """Сохраняет DLMS push-сообщение."""
        if parsed_data.get("type") == "day_push":
            filename = get_current_day_json_filename(self.save_dir)
            entry = {
                "received_at": datetime.now().isoformat(),
                "invoke_id": parsed_data.get("invoke_id"),
                "logical_name": parsed_data["logical_name"],
                "data": parsed_data["data"]
            }
        else:
            filename = get_current_json_filename(self.save_dir)
            entry = {
                "received_at": datetime.now().isoformat(),
                "invoke_id": parsed_data.get("invoke_id"),
                "records": parsed_data.get("records", [])
            }

        append_to_json_file(entry, filename)
        return filename
