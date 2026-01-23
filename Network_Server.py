# Network_Server.py

import socket
import threading
from message_handler import MessageProcessor


class DLMSNetworkServer:
    """Сетевой сервер для приёма DLMS-сообщений."""

    def __init__(self, output_callback=None, on_dlms_push=None, on_autoconnect=None):
        self.output_callback = output_callback or print
        self.processor = MessageProcessor(on_dlms_push, on_autoconnect)
        self.tcp_servers = {}
        self.udp_servers = {}
        self.running = False
        # Создаём обёртку для логгера
        logger_func = lambda msg: self.output_callback(msg)

        self.processor = MessageProcessor(
            on_dlms_push=on_dlms_push,
            on_autoconnect=on_autoconnect,
            logger=logger_func
        )

    def log(self, msg):
        self.output_callback(msg)

    def _handle_message(self, raw_data, client_info=None, local_port=None):
        """Обрабатывает входящее сообщение через процессор."""
        response = self.processor.process_message(raw_data, client_info, local_port)
        return response

    def handle_tcp_client(self, client_socket, address, local_port):
        """Обрабатывает TCP-клиента."""
        self.log(f"[TCP] Подключение от {address} на порт {local_port}")
        try:
            while self.running:
                raw_data = client_socket.recv(4096)
                if not raw_data:
                    break
                self.log(f"\n{'=' * 60}\n[TCP→] Получен пакет от {address} на порт {local_port}")
                response = self._handle_message(raw_data, address, local_port)
                if response:
                    client_socket.sendall(response)
                    self.log(f"[TCP✓] Ответ отправлен")
        except Exception as e:
            self.log(f"[TCP] Ошибка: {e}")
        finally:
            client_socket.close()

    def handle_udp_packet(self, raw_data, address, local_port):
        """Обрабатывает UDP-пакет."""
        self.log(f"\n{'=' * 60}\n[UDP→] Получен пакет от {address} на порт {local_port}")
        response = self._handle_message(raw_data, address, local_port)
        if local_port in self.udp_servers and response:
            udp_sock = self.udp_servers[local_port][0]
            udp_sock.sendto(response, address)

    # Методы start_tcp, start_udp, stop остаются без изменений
    # (они только управляют сокетами, не содержат бизнес-логики)

    def start_tcp(self, host='0.0.0.0', port=4059):
        """Запускает TCP-сервер на указанном порту."""
        if port in self.tcp_servers:
            self.log(f"[!] TCP сервер на порту {port} уже запущен")
            return False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.listen(5)
            self.running = True

            def tcp_loop():
                while self.running:
                    try:
                        client_sock, addr = sock.accept()
                        threading.Thread(
                            target=self.handle_tcp_client,
                            args=(client_sock, addr, port),
                            daemon=True
                        ).start()
                    except socket.error:
                        break
                sock.close()

            thread = threading.Thread(target=tcp_loop, daemon=True)
            thread.start()
            self.tcp_servers[port] = (sock, thread)
            self.log(f"[*] TCP сервер запущен на порту {port}")
            return True
        except Exception as e:
            self.log(f"[!] Ошибка запуска TCP на порту {port}: {e}")
            return False

    def start_udp(self, host='0.0.0.0', port=4059):
        """Запускает UDP-сервер на указанном порту."""
        if port in self.udp_servers:
            self.log(f"[!] UDP сервер на порту {port} уже запущен")
            return False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((host, port))
            self.running = True

            def udp_loop():
                while self.running:
                    try:
                        raw_data, addr = sock.recvfrom(4096)
                        threading.Thread(
                            target=self.handle_udp_packet,
                            args=(raw_data, addr, port),
                            daemon=True
                        ).start()
                    except socket.error:
                        break
                sock.close()

            thread = threading.Thread(target=udp_loop, daemon=True)
            thread.start()
            self.udp_servers[port] = (sock, thread)
            self.log(f"[*] UDP сервер запущен на порту {port}")
            return True
        except Exception as e:
            self.log(f"[!] Ошибка запуска UDP на порту {port}: {e}")
            return False

    def stop(self):
        """Останавливает все серверы."""
        self.log("[*] Остановка всех серверов...")
        self.running = False

        # Остановка TCP
        for port, (sock, _) in self.tcp_servers.items():
            try:
                sock.close()
            except:
                pass
        self.tcp_servers.clear()

        # Остановка UDP
        for port, (sock, _) in self.udp_servers.items():
            try:
                sock.close()
            except:
                pass
        self.udp_servers.clear()

        self.log("[*] Все серверы остановлены")