import os
from datetime import datetime
from typing import Optional, Tuple


class LogManager:
    """Управление логированием событий."""

    def __init__(self, log_dir: str = "./logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

    def save_to_file(self, message: str, address: Optional[Tuple[str, int]] = None) -> None:
        """Сохраняет сообщение в файл лога."""
        try:
            log_filename = f"dlms_log_{datetime.now().strftime('%Y-%m-%d')}.txt"
            log_filepath = os.path.join(self.log_dir, log_filename)

            current_time = datetime.now().strftime('%H:%M:%S')
            file_prefix = f"[{current_time}] "
            if address:
                file_prefix += f"[{address[0]}:{address[1]}] "
            log_line = file_prefix + message + "\n"

            with open(log_filepath, 'a', encoding='utf-8') as f:
                f.write(log_line)
        except Exception as e:
            print(f"Ошибка записи лога: {e}")
