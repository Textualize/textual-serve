import sys
from textual_serve.server import Server

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "python -m textual"
    password = sys.argv[2] if len(sys.argv) > 2 else None
    server = Server(command, password=password)
    server.serve()
