"""Validate and serialize the shared private POST module's existing bank."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[2]
RAW=b'BAIPNP2\0'
PACKED=b'BAIZX02\0'
HEADER=16
ENCODER_SHA256='e6aec5cdfc3535b808610cb54412ce375b5b13e17b59f2bc878a54a00a8acbac'


def raw_info(raw):
    if len(raw)<15 or len(raw)>=65536 or len(raw)&1 or raw[:8]!=RAW:
        raise ValueError('Invalid raw POST module identity/extent')
    length,entry=struct.unpack_from('<HH',raw,8)
    if length!=len(raw) or not 12<=entry<length or raw[entry:entry+3]!=bytes.fromhex('FFD3CB'):
        raise ValueError('Invalid raw POST module size/entry')
    return {'raw_bytes':length,'entry':entry,'raw_SUM16':sum(raw)&65535,'raw_sha256':hashlib.sha256(raw).hexdigest()}


def decode_zx0(source,length):
    """Forward v2 stream oracle; exact source and output extents, no prefix."""
    cursor=0;queue=0;remaining=0;output=bytearray();offset=-1
    def byte():
        nonlocal cursor
        if cursor==len(source):raise ValueError('Truncated ZX0 input')
        value=source[cursor];cursor+=1;return value
    def bit():
        nonlocal queue,remaining
        if not remaining:queue=byte();remaining=8
        remaining-=1;return queue>>remaining&1
    def elias(value=1,data_first=False):
        while data_first or not bit():
            value=value*2+bit()
            if value>65535:raise ValueError('ZX0 Elias overflow')
            data_first=False
        return value
    def copy(count,literal=False):
        if len(output)+count>length:raise ValueError('ZX0 output overflow')
        for _ in range(count):
            if literal:output.append(byte())
            else:
                if -offset>len(output):raise ValueError('ZX0 lookback before output')
                output.append(output[offset])
    while True:
        copy(elias(),True)
        new=bit()
        while True:
            if new:
                high=elias(254)
                low=(high+1)&255
                if not low:
                    if cursor!=len(source) or len(output)!=length:raise ValueError('ZX0 terminal extent mismatch')
                    return bytes(output)
                if high&0x8000:raise ValueError('ZX0 offset high overflow')
                packed=byte();offset=((low<<8|packed)>>1|0x8000)-65536
                count=1 if packed&1 else elias(data_first=True)
                count+=1
                if count>65535:raise ValueError('ZX0 match length overflow')
            else:count=elias()
            copy(count)
            if not bit():break
            new=True


def encode(raw,work):
    encoder=ROOT/'tools/deps/zx0/zx0.exe'
    if not encoder.exists():
        raise RuntimeError('ZX0 encoder is required. Run python -B tools/install-zx0.py before building.')
    if hashlib.sha256(encoder.read_bytes()).hexdigest()!=ENCODER_SHA256:
        raise RuntimeError('ZX0 encoder identity differs from the pinned version. Run tools/install-zx0.py.')
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    source=work/'post-module.raw.bin';target=work/'post-module.zx0'
    source.write_bytes(raw)
    subprocess.run([str(encoder),'-f',str(source),str(target)],check=True,capture_output=True)
    packed=target.read_bytes()
    if decode_zx0(packed,len(raw))!=raw:raise ValueError('ZX0 encoder roundtrip differs')
    return packed


def inspect_bank(bank):
    if len(bank)<HEADER+1 or sum(bank)&255:raise ValueError('POST bank size/checksum mismatch')
    if bank[:8]==RAW:
        length=struct.unpack_from('<H',bank,8)[0]
        if not 15<=length<=len(bank)-1:raise ValueError('Raw POST bank extent exceeds checksum boundary')
        raw=bank[:length];info=raw_info(raw);stored=length;kind='raw';metadata=12
    elif bank[:8]==PACKED:
        length,packed,checksum,entry=struct.unpack_from('<HHHH',bank,8)
        stored=HEADER+packed
        if not packed or stored>len(bank)-1 or not 15<=length<65536 or length&1:
            raise ValueError('Packed POST bank extent mismatch')
        raw=decode_zx0(bank[HEADER:stored],length);info=raw_info(raw)
        if info['raw_SUM16']!=checksum or info['entry']!=entry:raise ValueError('Decoded POST checksum/entry mismatch')
        kind='zx0-v2';metadata=HEADER
    else:raise ValueError('Unknown POST bank identity')
    if bank[stored:-1]!=b'\xFF'*(len(bank)-1-stored):raise ValueError('POST bank padding changed')
    return raw,info|{'storage':kind,'stored_bytes':stored,'metadata_bytes':metadata,'bank_bytes':len(bank),
                    'bank_checksum_bytes':1,'bank_padding_bytes':len(bank)-1-stored,'bank_sha256':hashlib.sha256(bank).hexdigest()}


def serialize(raw,work,bank_size):
    info=raw_info(raw)
    if bank_size<HEADER+1:raise ValueError('POST bank is too small for its header/checksum')
    if len(raw)<=bank_size-1:body=raw
    else:
        stream=encode(raw,work)
        body=PACKED+struct.pack('<HHHH',len(raw),len(stream),info['raw_SUM16'],info['entry'])+stream
    if len(body)>bank_size-1:raise ValueError('Complete private POST module does not fit the declared bank')
    bank=bytearray(body+b'\xFF'*(bank_size-len(body)))
    bank[-1]=(-sum(bank[:-1]))&255
    decoded,report=inspect_bank(bytes(bank))
    if decoded!=raw:raise ValueError('Final serialized POST bank roundtrip differs')
    return bytes(bank),report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('intermediate','system','bank','report'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--bank-size',type=lambda value:int(value,0),required=True)
    args=parser.parse_args();assembled=args.intermediate.read_bytes()
    if len(assembled)<65536:raise ValueError('Incomplete resident section')
    raw=assembled[65536:];raw_info(raw)
    bank,report=serialize(raw,args.bank.parent,args.bank_size)
    args.system.write_bytes(assembled[:65536]);args.bank.write_bytes(bank)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
