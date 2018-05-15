#!/usr/bin/env python3
from enum import Enum
import argparse
import array
import struct


class SlipState(Enum):
    WAIT_END = "Wait End"
    ESCAPING = "Escaping"
    STORE_INCOMING = "Store Incoming"

class Slip(object):
    SLIP_END = 0xC0
    SLIP_ESC = 0xDB
    SLIP_ESC_END = 0xDC
    SLIP_ESC_ESC = 0xDD
    def __init__(self):
        self.state = SlipState.WAIT_END
        self.rx = bytes()

    def decode(self, b):
        """Decode slip byte and update internal state"""
        if self.state == SlipState.WAIT_END:
            # Discard everything until we receive END byte
            if b == self.SLIP_END:
                self.state = SlipState.STORE_INCOMING
        elif self.state == SlipState.ESCAPING:
            self.state = SlipState.STORE_INCOMING
            # There are two bytes which can be escaped
            if b == self.SLIP_ESC_ESC:
                self.rx += bytes([self.SLIP_ESC])
            elif b == self.SLIP_ESC_END:
                self.rx += bytes([self.SLIP_END])
            else:
                # We should not be here, store byte anyway and let upper
                # layer figure it out
                self.rx += bytes([b])
        elif self.state == SlipState.STORE_INCOMING:
            if b == self.SLIP_ESC:
                # next byte is escaped
                self.state = SlipState.ESCAPING
            elif b == self.SLIP_END:
                # End of packet only if there are already data in rx buffer
                if len(self.rx) > 0:
                    # End of packet
                    self.state = SlipState.WAIT_END
                    # Save rx buffer to return
                    rx = self.rx
                    # Clear rx buffer
                    self.rx = bytes()
                    return rx
            else:
                # store regular byte
                self.rx += bytes([b])
        return None

    @classmethod
    def encode(cls, buf):
        """Encode buffer to slip protocol: header/footer and escaper special chars"""
        ret = bytes([cls.SLIP_END])
        for b in buf:
            if b == cls.SLIP_END:
                ret += bytes([cls.SLIP_ESC])
                ret += bytes([cls.SLIP_ESC_END])
            elif b == cls.SLIP_ESC:
                ret += bytes([cls.SLIP_ESC])
                ret += bytes([cls.SLIP_ESC_ESC])
            else:
                ret += bytes([b])
        ret += bytes([cls.SLIP_END])
        return ret

class SlipPayload(object):
    """Payload of a slip message"""
    def __init__(self, pid, seq, data):
        self.pid = pid
        self.seq = seq
        if type(data) != bytes:
            raise TypeError("Expect type bytes for data argument")
        self.data = data
        self.pack()

    def __repr__(self):
        return "SlipPayload(pid=%r, seq=%r, data=%r)" % (self.pid, self.seq, self.data)

    def __str__(self):
        s = ""
        s += "pid: %d\n" % (self.pid)
        s += "seq: %d\n" % (self.seq)
        s += "len: %d\n" % (len(self.data))
        if len(self.data) > 0:
            s += "data: %s\n" % (self.data.hex())
        # Update crc and packed data
        self.pack()
        s += "crc: %04X\n" % self.crc
        s += "packed_payload: %s\n" % self.packed_payload.hex()
        return s

    def pack(self):
        """Pack fields into packed data to serialize"""
        # header
        self.packed_payload = struct.pack("<BBB", self.pid, self.seq, len(self.data))
        # data
        self.packed_payload += self.data
        # Comput CRC
        self.crc = self.crc16_ccitt(0xFFFF, self.packed_payload)
        # Add crc to packed payload
        self.packed_payload += struct.pack("<H", self.crc)
        return self.packed_payload

    @classmethod
    def get_msg(cls, data):
        header_fmt = "<BBB"
        header_size = struct.calcsize(header_fmt)
        crc_fmt = "<H"
        crc_size = struct.calcsize(crc_fmt)

        # Unpack header
        (pid, seq, length) = struct.unpack(header_fmt, data[0:header_size])
        # Check length
        expected_length = len(data) - header_size - crc_size
        if length != expected_length:
            print("Mismatch in length, got %d, expected %d" % (length, expected_length))
            return None

        # Unpack CRC, compute CRC on received data and compare
        (crc,) = struct.unpack(crc_fmt, data[header_size + length:])
        computed_crc = cls.crc16_ccitt(0xFFFF, data[:header_size + length])
        if crc != computed_crc:
            print("Mismatch in CRC, got %04X, expected %04X" % (crc, computed_crc))
            return None

        # everything good, build the message
        msg = cls(pid, seq, data[header_size:-crc_size])
        return msg

    @staticmethod
    def crc16_ccitt(crc, data):
        msb = crc >> 8
        lsb = crc & 255
        for c in data:
            x = c ^ msb
            x ^= (x >> 4)
            msb = (lsb ^ (x >> 3) ^ (x << 4)) & 255
            lsb = (x ^ (x << 5)) & 255
        return (msb << 8) + lsb


def main():
    parser = argparse.ArgumentParser(description="Send Slip message",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("slip_interface", type=str, help="Slip interface")
    parser.add_argument("--pid", type=int, choices=range(0,128), metavar="[0-127]",
                        default=0, help="Primitive ID field")
    parser.add_argument("--seq", type=int, choices=range(0,256), metavar="[0-255]",
                        default=0, help="Sequence number field")
    parser.add_argument("--data", type=int, choices=range(0,256), metavar="[0-255]",
                        nargs="*", help="data")
    args = parser.parse_args()

    payload = SlipPayload(args.pid, args.seq, bytes(args.data))
    print(payload)
    slip = Slip()
    tx_buf = slip.encode(payload.pack())
    print("sending %s" % tx_buf.hex())
    #fd = open(args.slip_interface, "wb")
    #fd.write(tx_buf)
    for b in tx_buf:
        rx_buf = slip.decode(b)
        if rx_buf != None:
            msg = SlipPayload.get_msg(rx_buf)
            print(msg)






if __name__ == "__main__":
    main()
