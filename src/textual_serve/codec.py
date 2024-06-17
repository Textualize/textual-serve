from abc import ABC, abstractmethod

from typing import Sequence


CodecDataType = int | bytes | str | None


class CodecError(Exception):
    """Base class for codec related errors."""


class EncodeError(CodecError):
    """An error has occurred in encoding."""


class DecodeError(CodecError):
    """An error has occurred in decoding."""


class Codec(ABC):
    """A base class responsible for encoding and decoding packets for the wire."""

    @abstractmethod
    def encode(self, data: Sequence[CodecDataType]) -> bytes:
        """Encode a sequence of data in to bytes.

        Args:
            data (Sequence[CodecDataType]): A sequence of atomic types.

        Returns:
            bytes: Encoded bytes.
        """

    @abstractmethod
    def decode(self, packet: bytes) -> tuple[CodecDataType]:
        """Decode a packet in to a sequence of atomic types.

        Args:
            packet (bytes): Encoded packet.

        Returns:
            Sequence[CodecDataType]: A sequence of atomic types.
        """
