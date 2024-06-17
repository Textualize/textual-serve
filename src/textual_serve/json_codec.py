import json

from typing import Sequence

from .codec import Codec, CodecDataType, DecodeError


class JSONCodec(Codec):
    """A codec using the msgpack format."""

    def encode(self, data: Sequence[object]) -> bytes:
        return json.dumps(data).encode("utf-8")

    def decode(self, packet: bytes) -> tuple[CodecDataType]:
        try:
            return json.loads(packet.decode("utf-8"))
        except Exception as error:
            raise DecodeError(f"Unable to decode packet; {error}")
