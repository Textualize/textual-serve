from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
import logging
from typing import AsyncGenerator, TYPE_CHECKING

if TYPE_CHECKING:
    from textual_serve.app_service import AppService

log = logging.getLogger("textual-serve")

DOWNLOAD_TIMEOUT = 4


@dataclass
class Download:
    app_service: "AppService"
    delivery_key: str
    file_name: str
    open_method: str
    incoming_chunks: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)


class DownloadManager:
    """Class which manages downloads for the server.

    Serves as the link between the web server and app processes during downloads.

    A single server has a single download manager, which manages all downloads for all
    running app processes.
    """

    def __init__(self):
        self._active_downloads_lock = asyncio.Lock()
        self._active_downloads: dict[str, Download] = {}
        """A dictionary of active downloads.

        When a delivery key is received in a meta packet, it is added to this set.
        When the user hits the "/download/{key}" endpoint, we ensure the key is in
        this set and start the download by requesting chunks from the app process.

        When the download is complete, the app process sends a "deliver_file_end"
        meta packet, and we remove the key from this set.
        """

    async def create_download(
        self,
        *,
        app_service: "AppService",
        delivery_key: str,
        file_name: str,
        open_method: str,
    ) -> None:
        """Prepare for a new download.

        Args:
            app_service: The app service to start the download for.
            delivery_key: The delivery key to start the download for.
            file_name: The name of the file to download.
            open_method: The method to open the file with.
        """
        async with self._active_downloads_lock:
            self._active_downloads[delivery_key] = Download(
                app_service,
                delivery_key,
                file_name,
                open_method,
            )

    async def finish_download(self, delivery_key: str) -> None:
        """Finish a download for the given delivery key.

        Args:
            delivery_key: The delivery key to finish the download for.
        """
        try:
            download = self._active_downloads[delivery_key]
        except KeyError:
            log.error(f"Download {delivery_key!r} not found")
            return

        # Shut down the download queue. Attempt graceful shutdown, but
        # timeout after DOWNLOAD_TIMEOUT seconds if the queue doesn't clear.
        await download.incoming_chunks.put(None)
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                download.incoming_chunks.join(), timeout=DOWNLOAD_TIMEOUT
            )

        async with self._active_downloads_lock:
            del self._active_downloads[delivery_key]

    async def download(self, delivery_key: str) -> AsyncGenerator[bytes, None]:
        """Download a file from the given app service.

        Args:
            app_service: The app service to download from.
            delivery_key: The delivery key to download.
        """

        app_service = await self._get_app_service(delivery_key)
        download = self._active_downloads[delivery_key]
        incoming_chunks = download.incoming_chunks

        while True:
            # Request a chunk from the app service.
            await app_service.send_meta(
                {
                    "type": "deliver_chunk_request",
                    "key": delivery_key,
                    "size": 1024 * 64,
                }
            )

            chunk = await incoming_chunks.get()
            if not chunk:
                # The app process has finished sending the file.
                incoming_chunks.task_done()
                break
            else:
                incoming_chunks.task_done()
                yield chunk

            await asyncio.sleep(0.01)

    async def chunk_received(self, delivery_key: str, chunk: bytes) -> None:
        """Handle a chunk received from the app service for a download.

        Args:
            delivery_key: The delivery key that the chunk was received for.
            chunk: The chunk that was received.
        """
        download = self._active_downloads[delivery_key]
        await download.incoming_chunks.put(chunk)

    async def _get_app_service(self, delivery_key: str) -> "AppService":
        """Get the app service that the given delivery key is linked to.

        Args:
            delivery_key: The delivery key to get the app service for.
        """
        async with self._active_downloads_lock:
            for key in self._active_downloads.keys():
                if key == delivery_key:
                    return self._active_downloads[key].app_service
            else:
                raise ValueError(
                    f"No active download for delivery key {delivery_key!r}"
                )

    async def get_download_metadata(self, delivery_key: str) -> Download:
        """Get the metadata for a download.

        Args:
            delivery_key: The delivery key to get the metadata for.
        """
        async with self._active_downloads_lock:
            return self._active_downloads[delivery_key]
