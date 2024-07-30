from textual_serve.server import Server

server = Server("python open_link.py")
server.serve(debug=False)
