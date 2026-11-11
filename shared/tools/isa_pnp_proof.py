"""External ISA PnP cards and a PIT clock; no firmware algorithm replacement."""
from dataclasses import dataclass, field


KEY = bytes.fromhex('6AB5DAEDF6FB7DBEDF6F371B0D86C361B0582C168B45A2D1E8743A9DCEE77339')


def serial(vendor_product, number):
    raw = vendor_product + number.to_bytes(4, 'little')
    checksum = 0x6A
    for byte in raw:
        for shift in range(8):
            feedback = ((checksum >> 1) ^ checksum ^ (byte >> shift)) & 1
            checksum = (checksum >> 1) | feedback << 7
    return raw + bytes((checksum,))


@dataclass
class Card:
    identity: bytes
    resources: bytes = b'\x79\0'
    csn: int = 0
    state: str = 'wait'
    cursor: int = 0
    ldns: int = 1
    powerup_active: bool = False
    memory_upper: bool = False
    registers: dict = field(default_factory=dict)

    def reset(self):
        self.registers={n:{0x30:int(self.powerup_active),0x71:2,0x73:2,0x74:4,0x75:4} for n in range(self.ldns)}
        for row in self.registers.values():
            for control in (0x42,0x4A,0x52,0x5A,0x7A,0x84,0x94,0xA4):row[control]=int(self.memory_upper)

    def __post_init__(self):
        self.reset()


class Bus:
    def __init__(self, cards=(), conflicts=None):
        self.cards = list(cards)
        self.conflicts = conflicts or {}
        self.address = 0
        self.key = bytearray()
        self.enabled = False
        self.read_port = 0
        self.candidates = []
        self.selected = None
        self.selected_ldn = 0
        self.config_writes = []
        self.bit = self.pair = 0
        self.sense = False
        self.ticks = self.last_pair = 0
        self.isolation_start = 0
        self.latch = self.latch_byte = 0
        self.transactions = []
        self.delays = []
        self.ready = False
        self.pause = True
        self.never_ready = False
        self.resource_reads = 0
        self.status_reads = 0
        self.reset_at = None
        self.reset_settles = []

    def output(self, port, size, value):
        if port == 0x43 and value == 0:
            self.ticks += 8
            # Intel8254 mode3, even divisor65536: two decrements/input clock,
            # reload each half-period. ticks always counts actual input clocks.
            self.latch = (-2*self.ticks) & 65535
            self.latch_byte = 0
            return True
        if port == 0x279:
            assert size == 1, 'ISA ADDRESS must be byte I/O'
            self.transactions.append(('address', value))
            if not self.enabled:
                self.key.append(value)
                if self.key[-34:] == b'\0\0' + KEY:
                    self.enabled = True
                    for card in self.cards:card.state = 'sleep'
            self.address = value
            if value == 1 and self.enabled:
                self.bit = self.pair = 0
                self.isolation_start = self.ticks
            return True
        if port != 0xA79:return False
        assert size == 1 and self.enabled
        if self.reset_at is not None and self.address!=2:
            elapsed=self.ticks-self.reset_at
            assert elapsed>=2387,('reset settle',elapsed)
            self.reset_settles.append(elapsed);self.reset_at=None
        self.transactions.append(('write', self.address, value))
        if self.address == 0:
            self.read_port = (value << 2) | 3
        elif self.address == 2:
            if value & 1:
                for card in self.cards:card.cursor = 0;card.reset()
                self.reset_at=self.ticks
            if value & 4:
                for card in self.cards:card.csn = 0
            if value & 2:
                self.enabled = False
                self.key.clear()
                for card in self.cards:card.state = 'wait'
        elif self.address == 3:
            self.selected = None
            self.ready = False
            for card in self.cards:
                card.cursor = 0
                card.state = ('isolate' if value == 0 else 'config') if card.csn == value else 'sleep'
                if value and card.csn == value:self.selected = card
            self.candidates = [card for card in self.cards if card.state == 'isolate']
        elif self.address == 6:
            assert value and len(self.candidates) == 1 and self.bit == 72
            self.selected = self.candidates[0]
            self.selected.csn = value
            self.selected.state = 'config'
            self.selected.cursor = 9
            self.ready = False
        elif self.address==7:
            assert self.selected is not None and self.selected.state=='config'
            self.selected_ldn=value
        else:
            assert self.selected is not None and self.selected.state=='config'
            registers=self.selected.registers.get(self.selected_ldn)
            if registers is not None:
                assert self.address in (0x30,0x31,*range(0x60,0x76),
                    *[b+i for b in (0x40,0x48,0x50,0x58) for i in range(5)],
                    *[b+i for b in (0x76,0x80,0x90,0xA0) for i in range(9)]),('Reserved/filler write',self.address)
                if self.address!=0x30:assert not registers[0x30], 'Programming while active'
                if self.address in (0x42,0x4A,0x52,0x5A,0x7A,0x84,0x94,0xA4):
                    value=(value&~1)|(registers[self.address]&1)
                registers[self.address]=value
                self.config_writes.append((self.selected.csn,self.selected_ldn,self.address,value))
        return True

    def input(self, port, size):
        if port == 0x40:
            result = (self.latch >> (8*self.latch_byte)) & 255
            self.latch_byte ^= 1
            return result
        if port != self.read_port or not self.enabled:return None
        assert size == 1
        self.transactions.append(('read', self.address))
        if self.address == 1:
            assert self.bit < 72
            if not self.pair:
                elapsed = self.ticks - (self.last_pair if self.bit else self.isolation_start)
                assert elapsed >= (299 if self.bit else 1194), ('isolation delay', self.bit, elapsed)
                self.delays.append(elapsed)
                self.sense = any(card.identity[self.bit//8] & (1 << (self.bit%8)) for card in self.candidates)
                if self.conflicts.get(port) == 'no-pair':self.sense = False
                if self.conflicts.get(port) == 'checksum' and self.bit == 71:self.sense = not self.sense
                self.pair = 1
                return 0x55 if self.sense else 0xFF
            result = 0xAA if self.sense else 0xFF
            if self.sense:
                self.candidates = [card for card in self.candidates if card.identity[self.bit//8] & (1 << (self.bit%8))]
            self.pair = 0
            self.bit += 1
            self.last_pair = self.ticks
            return result
        assert self.selected is not None and self.selected.state == 'config'
        if self.address>=0x30:
            return self.selected.registers.get(self.selected_ldn,{}).get(self.address,0)
        if self.address == 5:
            self.status_reads += 1
            if self.never_ready or self.selected.cursor >= 9+len(self.selected.resources):return 0
            old = self.ready or not self.pause
            self.ready = True
            return int(old)
        assert self.address == 4 and self.ready, 'Resource byte without readiness poll'
        self.ready = False
        # The reopened ninth byte is deliberately not a valid isolation checksum.
        stream = self.selected.identity[:8] + b'\xA5' + self.selected.resources
        assert self.selected.cursor < len(stream)
        result = stream[self.selected.cursor]
        self.selected.cursor += 1
        self.resource_reads += 1
        return result
