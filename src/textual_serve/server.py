from __future__ import annotations

import asyncio

import logging
import os
from pathlib import Path
import signal

from typing import Any, Callable
import pickle


import aiohttp_jinja2
from aiohttp import web
from aiohttp import WSMsgType
from aiohttp.web_runner import GracefulExit
import jinja2

from rich import print

from textual.app import App


from .app_service import AppService

log = logging.getLogger("textual")


class Server:
    """Serve a Textual app."""

    def __init__(
        self,
        command: str,
        host: str = "0.0.0.0",
        port: int = 8000,
        name: str = "Textual App",
        public_url: str | None = None,
        statics_path: str | os.PathLike = "./static",
        templates_path: str | os.PathLike = "./templates",
    ):
        """_summary_

        Args:
            app_factory: A callable that returns a new App instance.
            host: Host of web application.
            port: Port for server.
            statics_path: Path to statics folder. May be absolute or relative to server.py.
            templates_path" Path to templates folder. May be absolute or relative to server.py.
        """
        self.command = command
        self.host = host
        self.port = port
        self.name = name

        if public_url is None:
            if self.port == 80:
                self.public_url = f"http://{self.host}"
            else:
                self.public_url = f"http://{self.host}:{self.port}"
        else:
            self.public_url = public_url

        base_path = (Path(__file__) / "../").resolve().absolute()
        self.statics_path = base_path / statics_path
        self.templates_path = base_path / templates_path

    def request_exit(self, reason: str | None = None) -> None:
        """Gracefully exit the application, optionally supplying a reason.

        Args:
            reason: The reason for exiting which will be included in the Ganglion server log.
        """
        log.info(f"Exiting - {reason if reason else ''}")
        raise GracefulExit()

    async def _make_app(self) -> web.Application:
        """Make the aiohttp web.Application.

        Returns:
            New aiohttp application.
        """
        app = web.Application()

        aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(self.templates_path))

        ROUTES = [
            web.get("/", self.handle_index, name="index"),
            web.get("/ws", self.handle_websocket, name="websocket"),
            web.static("/static", self.statics_path, show_index=True, name="static"),
        ]
        app.add_routes(ROUTES)
        return app

    async def on_shutdown(self, app: web.Application) -> None:
        pass

    def serve(self) -> None:
        """Serve the Textual application.

        This will run a local webserver until it is closed with Ctrl+C

        """
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self.request_exit)
        loop.add_signal_handler(signal.SIGTERM, self.request_exit)
        web.run_app(self._make_app(), port=self.port, handle_signals=False, loop=loop)

    @aiohttp_jinja2.template("app_index.html")
    async def handle_index(self, request: web.Request) -> dict[str, Any]:
        router = request.app.router

        def get_url(route: str, **args) -> str:
            """Get a URL from the aiohttp router."""
            path = router[route].url_for(**args)
            return f"{self.public_url}{path}"

        context = {
            "font_size": 14,
            "app_websocket_url": get_url("websocket"),
        }
        context["config"] = {
            "static": {
                "url": get_url("static", filename="/") + "/",
            },
        }
        context["application"] = {
            "name": self.name,
        }

        print(context)
        return context

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        websocket = web.WebSocketResponse(heartbeat=15)

        def to_int(number: str, default: int) -> int:
            try:
                return int(number)
            except ValueError:
                return default

        width = to_int(request.query.get("width", "80"), 80)
        height = to_int(request.query.get("height", "24"), 24)

        TEXT = WSMsgType.TEXT
        BINARY = WSMsgType.BINARY

        try:
            await websocket.prepare(request)

            app_service = AppService(
                self.command, websocket.send_bytes, websocket.send_str
            )
            app_service.start(width, height)

            async for message in websocket:
                if message.type == TEXT:
                    match message.json():
                        case ["stdin", data]:
                            await app_service.send_bytes(data.encode("utf-8"))
                        case ["resize", {"width": width, "height": height}]:
                            await app_service.set_terminal_size(width, height)
                elif message.type == BINARY:
                    pass

        except asyncio.CancelledError:
            await websocket.close()

        finally:
            await app_service.stop()

        return websocket
