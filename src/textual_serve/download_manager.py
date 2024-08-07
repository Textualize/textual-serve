import asyncio
from contextlib import suppress
from typing import Tuple

from textual_serve.app_service import AppService

DOWNLOAD_TIMEOUT = 4

DownloadKey = Tuple[str, str]
"""A tuple of (app_service_id, delivery_key)."""


class DownloadManager:
    """Class which manages downloads for the server.

    Serves as the link between the web server and app processes during downloads.

    A single server has a single download manager, which manages all downloads for all
    running app processes.
    """

    def __init__(self):
        self.running_app_sessions_lock = asyncio.Lock()
        self.running_app_sessions: list[AppService] = []
        """A list of running app sessions. An `AppService` will be added here when a browser
        client connects and removed when it disconnects."""

        self._active_downloads_lock = asyncio.Lock()
        self._active_downloads: dict[DownloadKey, asyncio.Queue[bytes | None]] = {}
        """Set of active deliveries (string 'delivery keys' -> queue of bytes objects).
        
        When a delivery key is received in a meta packet, it is added to this set.
        When the user hits the "/download/{key}" endpoint, we ensure the key is in
        this set and start the download by requesting chunks from the app process.

        When the download is complete, the app process sends a "deliver_file_end"
        meta packet, and we remove the key from this set.
        """

    async def register_app_service(self, app_service: AppService) -> None:
        """Register an app service with the download manager.

        Args:
            app_service: The app service to register.
        """
        async with self.running_app_sessions_lock:
            self.running_app_sessions.append(app_service)

    async def unregister_app_service(self, app_service: AppService) -> None:
        """Unregister an app service from the download manager.

        Args:
            app_service: The app service to unregister.
        """
        # TODO - remove any downloads for this app service.
        async with self.running_app_sessions_lock:
            self.running_app_sessions.remove(app_service)

    async def start_download(self, app_service: AppService, delivery_key: str) -> None:
        """Start a download for the given delivery key on the given app service.

        Args:
            app_service: The app service to start the download for.
            delivery_key: The delivery key to start the download for.
        """
        async with self.running_app_sessions_lock:
            if app_service not in self.running_app_sessions:
                raise ValueError("App service not registered")

        # Create a queue to write the received chunks to.
        self._active_downloads[(app_service.app_service_id, delivery_key)] = (
            asyncio.Queue[bytes | None]()
        )

    async def finish_download(self, app_service: AppService, delivery_key: str) -> None:
        """Finish a download for the given delivery key.

        Args:
            app_service: The app service to finish the download for.
            delivery_key: The delivery key to finish the download for.
        """
        download_key = (app_service.app_service_id, delivery_key)
        queue = self._active_downloads[download_key]
        await queue.put(None)
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(queue.join(), timeout=DOWNLOAD_TIMEOUT)
        del self._active_downloads[download_key]
