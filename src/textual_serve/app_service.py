import asyncio
import base64
import os
import pickle
import sys
from typing import Callable
from asyncio.subprocess import Process

from importlib.metadata import version

import rich.repr
from textual.app import App

from .packets import Handlers
from .json_codec import JSONCodec
from .packet_decoder import PacketDecoder


@rich.repr.auto
class AppService(Handlers):
    def __init__(self, app_factory: Callable[[], App]) -> None:
        self.app_factory = app_factory
        self._pickled_app_factory: bytes = pickle.dumps(app_factory)
        self.codec = JSONCodec()
        self._packet_decoder = PacketDecoder(self.codec)

        self._task: asyncio.Task | None = None

    def _build_environment(self, width: int = 80, height: int = 24) -> dict[str, str]:
        """Build an environment dict for the App subprocess.

        Args:
            width: Initial width.
            height: Initial height.

        Returns:
            A environment dict.
        """
        environment = dict(os.environ.copy())
        environment["TEXTUAL_DRIVER"] = "textual.drivers.web_driver:WebDriver"
        environment["TEXTUAL_FPS"] = "60"
        environment["TEXTUAL_COLOR_SYSTEM"] = "truecolor"
        environment["TERM_PROGRAM"] = "textual"
        environment["TERM_PROGRAM_VERSION"] = version("textual-serve")
        environment["COLUMNS"] = str(width)
        environment["ROWS"] = str(height)
        return environment

    async def _open_app_process(self, width: int = 80, height: int = 24) -> Process:
        """Open a process to run the app.

        Args:
            width: Width of the terminal.
            height: height of the terminal.
        """
        environment = self._build_environment(width=width, height=height)
        encoded_app_factory = base64.b64encode(self._pickled_app_factory)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "textual_server.runner",
            encoded_app_factory,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        assert process.stdin is not None
        process.stdin.write(encoded_app_factory + b"\n")
        await process.stdin.drain()
        return process

    async def run(self, width: int = 80, height: int = 24) -> None:
        process = await self._open_app_process(width, height)
        stdout = process.stdout
        assert stdout is not None
        while True:
            initial = await stdout.readexactly(1)

            size_bytes = await stdout.readexactly(4)
            size = int.from_bytes(size_bytes, "big")
            payload = await stdout.readexactly(size)

            if initial == "D":
                await self.on_data(payload)
            elif initial == "M":
                await self.on_meta(payload)
            else:
                raise RuntimeError("unknown packet")

    async def on_data(self, payload: bytes) -> None:
        packet = self._packet_decoder.decode(payload)
        assert packet is not None
        await self.dispatch_packet(packet)

    async def on_meta(self, data: object) -> None:
        pass
