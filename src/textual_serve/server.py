from __future__ import annotations

import asyncio

import logging
import os
from pathlib import Path
import signal

from typing import Any

import aiohttp_jinja2
from aiohttp import web
from aiohttp import WSMsgType
from aiohttp.web_runner import GracefulExit
import jinja2

from rich import print
from rich.logging import RichHandler
from rich.highlighter import RegexHighlighter

from .app_service import AppService

log = logging.getLogger("textual-serve")


class LogHighlighter(RegexHighlighter):
    base_style = "repr."
    highlights = [
        r"(?P<number>(?<!\w)\-?[0-9]+\.?[0-9]*(e[-+]?\d+?)?\b|0x[0-9a-fA-F]*)",
        r"(?P<path>\[.*?\])",
        r"(?<![\\\w])(?P<str>b?'''.*?(?<!\\)'''|b?'.*?(?<!\\)'|b?\"\"\".*?(?<!\\)\"\"\"|b?\".*?(?<!\\)\")",
    ]


def to_int(value: str, default: int) -> int:
    """Convert to an integer, or return a default if that's not possible.

    Args:
        number: A string possibly containing a decimal.
        default: Default value if value can't be decoded.

    Returns:
        Integer.
    """
    try:
        return int(value)
    except ValueError:
        return default


class Server:
    """Serve a Textual app."""

    def __init__(
        self,
        command: str,
        host: str = "localhost",
        port: int = 8000,
        title: str | None = None,
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
        self.title = title or command
        self.debug = False

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

    def initialize_logging(self) -> None:
        FORMAT = "%(message)s"
        logging.basicConfig(
            level="INFO",
            format=FORMAT,
            datefmt="[%X]",
            handlers=[
                RichHandler(
                    show_path=False,
                    show_time=False,
                    rich_tracebacks=True,
                    highlighter=LogHighlighter(),
                )
            ],
        )

    def request_exit(self) -> None:
        """Gracefully exit the app."""
        log.info("Exit requested")
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

    def serve(self, debug: bool = False) -> None:
        """Serve the Textual application.

        This will run a local webserver until it is closed with Ctrl+C

        """
        self.debug = debug
        self.initialize_logging()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self.request_exit)
        loop.add_signal_handler(signal.SIGTERM, self.request_exit)
        if self.debug:
            log.info("Running in debug mode. You may use textual dev tools.")
        web.run_app(
            self._make_app(),
            host=self.host,
            port=self.port,
            handle_signals=False,
            loop=loop,
        )

    @aiohttp_jinja2.template("app_index.html")
    async def handle_index(self, request: web.Request) -> dict[str, Any]:
        router = request.app.router
        font_size = to_int(request.query.get("fontsize", "16"), 16)

        def get_url(route: str, **args) -> str:
            """Get a URL from the aiohttp router."""
            path = router[route].url_for(**args)
            return f"{self.public_url}{path}"

        context = {
            "font_size": font_size,
            "app_websocket_url": get_url("websocket"),
        }
        context["config"] = {
            "static": {
                "url": get_url("static", filename="/") + "/",
            },
        }
        context["application"] = {
            "name": self.title,
        }
        return context

    async def _process_messages(
        self, websocket: web.WebSocketResponse, app_service: AppService
    ) -> None:
        """Process messages from the websocket.

        Args:
            websocket: Websocket instance.
            app_service: App service.
        """
        TEXT = WSMsgType.TEXT

        async for message in websocket:
            if message.type != TEXT:
                continue
            envelope = message.json()
            assert isinstance(envelope, list)
            type_ = envelope[0]
            if type_ == "stdin":
                data = envelope[1]
                await app_service.send_bytes(data.encode("utf-8"))
            elif type_ == "resize":
                data = envelope[1]
                await app_service.set_terminal_size(data["width"], data["height"])
            elif type_ == "ping":
                data = envelope[1]
                await websocket.send_json(["pong", data])
            elif type_ == "blur":
                await app_service.blur()
            elif type_ == "focus":
                await app_service.focus()

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle the websocket that drives the remote process.

        Args:
            request: Request object.

        Returns:
            Websocket response.
        """
        websocket = web.WebSocketResponse(heartbeat=15)

        width = to_int(request.query.get("width", "80"), 80)
        height = to_int(request.query.get("height", "24"), 24)

        try:
            await websocket.prepare(request)
            app_service = AppService(
                self.command,
                write_bytes=websocket.send_bytes,
                write_str=websocket.send_str,
                close=websocket.close,
                debug=self.debug,
            )
            await app_service.start(width, height)
            try:
                await self._process_messages(websocket, app_service)
            finally:
                await app_service.stop()

        except asyncio.CancelledError:
            await websocket.close()

        except Exception as error:
            log.exception(error)

        finally:
            await app_service.stop()

        return websocket
