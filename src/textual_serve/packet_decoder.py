from .codec import Codec, CodecDataType
from .packets import Packet, PACKET_MAP


class PacketError(Exception):
    pass


class PacketDecoder:
    """Base class for an object which encodes and decodes packets."""

    def __init__(self, codec: Codec) -> None:
        self.codec = codec

    def decode(self, data: bytes) -> Packet | None:
        """Build a packet from raw data.

        Raises:
            PacketError: If the packet is invalid.

        Returns:
            One of the packet objects defined in packets.py
        """
        try:
            packet_envelope = self.codec.decode(data)
        except Exception as error:
            raise PacketError(f"failed to decode packet; {error}")
        packet = self.decode_envelope(packet_envelope)
        return packet

    @classmethod
    def decode_envelope(
        cls, packet_envelope: tuple[CodecDataType, ...]
    ) -> Packet | None:
        """Decode a packet envelope.

        Packet envelopes are a list where the first value is an integer denoting the type.
        The type is used to look up the appropriate Packet class which is instantiated with
        the rest of the data.

        If the envelope contains *more* data than required, then that data is silently dropped.
        This is to provide an extension mechanism.

        Raises:
            PacketError: If the packet_envelope is empty.
            PacketError: If the packet type is not an int.

        Returns:
            One of the Packet classes defined in packets.py or None if the packet was of an unknown type.
        """
        if not packet_envelope:
            raise PacketError("Packet data is empty")

        packet_data: list[CodecDataType]
        packet_type, *packet_data = packet_envelope
        if not isinstance(packet_type, int):
            raise PacketError(f"Packet id expected int, found {packet_type!r}")
        if (packet_class := PACKET_MAP.get(packet_type)) is None:
            # Unknown packet
            return None
        try:
            packet = packet_class.build(*packet_data[: len(packet_class._attributes)])
        except TypeError as error:
            raise PacketError(f"Packet failed to validate; {error}")
        return packet
