#!/usr/bin/env python3
from enum import Enum
import array


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

if __name__ == "__main__":
    slip = Slip()
    tx = [0x1, 0x2, 0x3, 0xC0, 0xDB]
    buf = bytes(tx)
    tx_encoded = slip.encode(buf)
    print(tx_encoded)
    for b in tx_encoded:
        msg = slip.decode(b)
        if msg != None:
            print(msg)
