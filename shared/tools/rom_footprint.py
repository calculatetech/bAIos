"""Report final resident storage, private representation and POST-only RAM."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from shared.tools.post_module import PACKED,inspect_bank,raw_info


def symbol(lines,name):
    start=next(i for i,line in enumerate(lines) if re.search(r'(?<![\w.])'+re.escape(name)+r':\s*$',line))
    for line in lines[start+1:]:
        found=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line)
        if found:return int(found[1],16)
    raise ValueError('Missing assembled address for '+name)


def report(image,listing,*,module_offset=None,bank_bytes=0,transport='inline'):
    image=Path(image);raw=image.read_bytes();lines=Path(listing).read_text().splitlines()
    intervals=[]
    for line in lines:
        if not re.search(r'\btimes\s+(?:0xF065|0xFFF0|CFG_ROM_CHECKSUM_OFFSET)',line) or 'db 0xFF' not in line:continue
        found=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+FF<rep ([0-9A-F]+)h>',line)
        if found:
            start,length=(int(v,16) for v in found.groups())
            if start<0xFFF0:intervals.append({'offset':start,'bytes':length})
    free=sum(row['bytes'] for row in intervals)
    module={'transport':transport,'raw_bytes':0,'stored_bytes':0,'metadata_bytes':0,
            'bank_bytes':0,'decoder_resident_bytes':0,'source_staging_RAM_bytes':0,
            'decoded_RAM_bytes':0,'alignment_RAM_bytes':0,'charged_temporary_RAM_bytes':0}
    if module_offset is not None:
        bank=raw[module_offset:module_offset+bank_bytes]
        if len(bank)!=bank_bytes:raise ValueError('Private module exceeds physical image')
        if bank[:8]==PACKED:
            decoded,details=inspect_bank(bank);module.update(details)
        else:
            length=struct.unpack_from('<H',bank,8)[0];decoded=bank[:length]
            details=raw_info(decoded);module.update(details,storage='raw',stored_bytes=length,metadata_bytes=12,
                bank_bytes=bank_bytes,bank_checksum_bytes=1,bank_padding_bytes=bank_bytes-length-1)
        if transport=='top-alias':
            module['source_staging_RAM_bytes']=bank_bytes
            if module['storage']!='raw':
                module['decoded_RAM_bytes']=(len(decoded)+15)&~15
                module['alignment_RAM_bytes']=(-len(decoded))&15
            module['decoder_resident_bytes']=symbol(lines,'zx0_decode_end')-symbol(lines,'zx0_decode')
        elif transport=='window-copy':
            module['decoded_RAM_bytes']=(len(decoded)+15)&~15
            module['alignment_RAM_bytes']=(-len(decoded))&15
        module['charged_temporary_RAM_bytes']=module['source_staging_RAM_bytes']+module['decoded_RAM_bytes']
        module['physical_offset']=module_offset
    return {'schema':1,'artifact':{'path':image.name,'bytes':len(raw),'SUM32':f'{sum(raw)&0xffffffff:08X}',
            'sha256':hashlib.sha256(raw).hexdigest()},'resident':{'bytes':65536,'free_bytes':free,
            'occupied_bytes':65536-free,'free_intervals':intervals},'private_module':module,
            'variable_journal_and_runtime_records':'Additional allocation depends on actual devices and returning ROM reservations.'}


def write_report(image,listing,**options):
    result=report(image,listing,**options)
    Path(image).with_name('rom-footprint.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('image',type=Path);p.add_argument('listing',type=Path)
    p.add_argument('--module-offset',type=lambda v:int(v,0));p.add_argument('--bank-bytes',type=lambda v:int(v,0),default=0)
    p.add_argument('--transport',choices=('inline','direct-rom','window-copy','top-alias'),default='inline')
    a=p.parse_args();print(json.dumps(write_report(a.image,a.listing,module_offset=a.module_offset,bank_bytes=a.bank_bytes,transport=a.transport),indent=2))
