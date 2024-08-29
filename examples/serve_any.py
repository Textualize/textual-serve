import sys
from textual_serve.server import Server

if __name__ == "__main__":
    server = Server(sys.argv[1])
    server.serve(debug=True)
