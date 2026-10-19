"""Independent decoded UART and printer registers for firmware transaction proofs."""
class UART:
    def __init__(self):
        self.regs=bytearray((0,9,0,0x1B,0,0,0,0x3A));self.dll=2;self.dlm=0;self.tx=[];self.rx=[0xA6];self.writes=[]
    def read(self,offset):
        if offset==0:return self.dll if self.regs[3]&0x80 else self.rx.pop(0) if self.rx else 0
        if offset==1:return self.dlm if self.regs[3]&0x80 else self.regs[1]
        if offset==5:return 0x60|bool(self.rx)
        if offset==6:return 0x30
        return self.regs[offset]
    def write(self,offset,value):
        self.writes.append((offset,value))
        if offset==0:
            if self.regs[3]&0x80:self.dll=value
            else:self.tx.append(value)
        elif offset==1 and self.regs[3]&0x80:self.dlm=value
        else:self.regs[offset]=value


class Printer:
    def __init__(self):self.latch=0xA5;self.control=0x20;self.tx=[];self.writes=[]
    def read(self,offset):return (0x3C if self.control&0x20 else self.latch) if offset==0 else 0x90 if offset==1 else self.control
    def write(self,offset,value):
        self.writes.append((offset,value))
        if offset==0:self.latch=value
        if offset==2:
            if value&1 and not self.control&1:self.tx.append(self.latch)
            self.control=value
