import asyncio
import io
import json
import os
from typing import Awaitable, Callable, Literal, TypeAlias
from asyncio.subprocess import Process

from importlib.metadata import version

import rich.repr

from .packets import Handlers
from .json_codec import JSONCodec
from .packet_decoder import PacketDecoder


Meta: TypeAlias = "dict[str, str | None | int | bool]"


@rich.repr.auto
class AppService(Handlers):
    def __init__(
        self,
        command: str,
        remote_write_bytes: Callable[[bytes], Awaitable],
        remote_write_str: Callable[[str], Awaitable],
    ) -> None:
        self.command = command
        self.remote_write_bytes = remote_write_bytes
        self.remote_write_str = remote_write_str
        self.codec = JSONCodec()
        self._packet_decoder = PacketDecoder(self.codec)
        self._task: asyncio.Task | None = None
        self._stdin: asyncio.StreamWriter | None = None
        self._exit_event = asyncio.Event()

    @property
    def stdin(self) -> asyncio.StreamWriter:
        assert self._stdin is not None
        return self._stdin

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
        process = await asyncio.create_subprocess_shell(
            self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        assert process.stdin is not None
        return process

    @classmethod
    def encode_packet(cls, packet_type: Literal[b"D", b"M"], payload: bytes) -> bytes:
        """Encode a packet.

        Args:
            packet_type: The packet type (b"D" for data or b"M" for meta)
            payload: The payload.

        Returns:
            Data as bytes.
        """
        return b"%s%s%s" % (packet_type, len(payload).to_bytes(4, "big"), payload)

    async def send_bytes(self, data: bytes) -> bool:
        """Send bytes to process.

        Args:
            data: Data to send.

        Returns:
            True if the data was sent, otherwise False.
        """
        stdin = self.stdin
        try:
            stdin.write(self.encode_packet(b"D", data))
        except RuntimeError:
            return False
        await stdin.drain()
        return True

    async def send_meta(self, data: Meta) -> bool:
        """Send meta information to process.

        Args:
            data: Meta dict to send.

        Returns:
            True if the data was sent, otherwise False.
        """
        stdin = self.stdin
        data_bytes = json.dumps(data).encode("utf-8")
        try:
            stdin.write(self.encode_packet(b"M", data_bytes))
        except RuntimeError:
            return False
        await stdin.drain()
        return True

    async def set_terminal_size(self, width: int, height: int) -> None:
        await self.send_meta(
            {
                "type": "resize",
                "width": width,
                "height": height,
            }
        )

    def start(self, width: int, height: int) -> None:
        self._task = asyncio.create_task(self.run(width, height))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await self._task
            self._task = None

    async def run(self, width: int = 80, height: int = 24) -> None:
        META = b"M"
        DATA = b"D"

        process = await self._open_app_process(width, height)

        stdout = process.stdout
        stderr = process.stderr
        assert stdout is not None
        assert stderr is not None
        self._stdin = process.stdin

        stderr_data = io.BytesIO()

        async def read_stderr() -> None:
            """Task to read stderr."""
            try:
                while True:
                    data = await stderr.read(1024 * 4)
                    if not data:
                        break
                    stderr_data.write(data)
            except asyncio.CancelledError:
                pass

        stderr_task = asyncio.create_task(read_stderr())

        try:
            ready = False
            for _ in range(10):
                line = await stdout.readline()
                if not line:
                    break
                if line == b"__GANGLION__\n":
                    ready = True
                    break

            if ready:
                while not self._exit_event.is_set():
                    type_bytes = await stdout.readexactly(1)
                    size_bytes = await stdout.readexactly(4)
                    size = int.from_bytes(size_bytes, "big")
                    payload = await stdout.readexactly(size)

                    if type_bytes == DATA:
                        await self.on_data(payload)
                    elif type_bytes == META:
                        await self.on_meta(payload)
                    else:
                        raise RuntimeError("unknown packet")
        except asyncio.IncompleteReadError:
            pass
        except asyncio.CancelledError:
            pass
        finally:
            stderr_task.cancel()
            await stderr_task

    async def on_data(self, payload: bytes) -> None:
        await self.remote_write_bytes(payload)

    async def on_meta(self, data: object) -> None:
        meta_data = json.loads(data)
        print("on_meta", meta_data)
