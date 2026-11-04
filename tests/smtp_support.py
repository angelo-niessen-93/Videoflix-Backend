"""Loopback-only SMTP sink for actual Django SMTP transport tests."""

from contextlib import contextmanager
from socketserver import StreamRequestHandler, ThreadingTCPServer
from threading import Thread


class SmtpHandler(StreamRequestHandler):
    def reply(self, value):
        self.wfile.write(value + b"\r\n")
        self.wfile.flush()

    def handle(self):
        self.connection.settimeout(5)
        self.reply(b"220 localhost test SMTP")
        while line := self.rfile.readline(65536):
            command = line.split(b" ", 1)[0].strip().upper()
            if command == b"DATA":
                self.receive_message()
            elif command == b"QUIT":
                self.reply(b"221 Bye")
                return
            else:
                self.reply(b"250 localhost")

    def receive_message(self):
        self.reply(b"354 End with dot")
        lines = []
        while line := self.rfile.readline(65536):
            if line == b".\r\n":
                self.server.messages.append(b"".join(lines))
                self.reply(b"250 Accepted locally")
                return
            lines.append(line[1:] if line.startswith(b"..") else line)


@contextmanager
def local_smtp_server():
    with ThreadingTCPServer(("127.0.0.1", 0), SmtpHandler) as server:
        server.daemon_threads = True
        server.messages = []
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)
