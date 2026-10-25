import unittest
import protocol


class TestProtocol(unittest.TestCase):

    def test_header_size(self):
        self.assertEqual(protocol.HEADER_SIZE, 15)

    def test_pack_unpack(self):
        data = protocol.pack(protocol.DATA, 1, 0, b"hello")
        packet = protocol.unpack(data)

        self.assertIsNotNone(packet)
        self.assertEqual(packet.ptype, protocol.DATA)
        self.assertEqual(packet.payload, b"hello")

    def test_binary_safe(self):
        payload = bytes([0, 255, 10, 0, 128])
        data = protocol.pack(protocol.DATA, 1, 0, payload)
        packet = protocol.unpack(data)

        self.assertEqual(packet.payload, payload)

    def test_truncated_packet(self):
        data = protocol.pack(protocol.DATA, 1, 0, b"hello")
        self.assertIsNone(protocol.unpack(data[:5]))

    def test_corrupted_payload(self):
        data = bytearray(protocol.pack(protocol.DATA, 1, 0, b"hello"))
        data[-1] ^= 1

        self.assertIsNone(protocol.unpack(bytes(data)))

    def test_unknown_type(self):
        data = bytearray(protocol.pack(protocol.DATA, 1, 0, b"hello"))
        data[0] = 99

        self.assertIsNone(protocol.unpack(bytes(data)))

    def test_split_file(self):
        chunks = protocol.split_file(b"abcdefgh", 3)
        self.assertEqual(chunks, [b"abc", b"def", b"gh"])

    def test_start_metadata(self):
        digest = b"a" * 32
        payload = protocol.pack_start(100, 2, digest, "test.bin")
        result = protocol.unpack_start(payload)

        self.assertEqual(result, (100, 2, digest, "test.bin"))


if __name__ == "__main__":
    unittest.main()
