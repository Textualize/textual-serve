from textual_serve.server import Server

server = Server("python dictionary.py")
server.serve(debug=False)
