from textual_serve.server import Server

server = Server('textual run --dev -c "python dictionary.py"')
server.serve()
