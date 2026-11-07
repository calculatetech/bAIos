"""Independent complete Presario summary frame and retained-provider font oracle."""
from pathlib import Path
import json
from datetime import datetime

def check(cells,font,reference,ram=16384,positions=(0,),types=0,cache='512 KB',fpu=True,warnings=0,base_kib=632):
    expected=bytearray(b' \x07'*2000)
    def text(row,column,value,attribute=7):
        value=value.encode('cp437')
        for i,c in enumerate(value):expected[(row*80+column+i)*2:(row*80+column+i)*2+2]=bytes((c,attribute))
    text(0,0,' '*80,0x1F)
    text(0,3,'Packard Bell PB430',0x1B);text(0,37,'bAIos',0x1F)
    identity=json.loads((Path(__file__).resolve().parents[1]/'port.json').read_text())['identity']
    date=datetime.strptime(identity['release_date'],'%m/%d/%Y').strftime('%m/%d/%y')
    text(0,58,'ROM build:',0x1B);text(0,69,date,0x1F)
    for row,left,right in ((1,'\u2554','\u2557'),(5,'\u2560','\u2563'),(8,'\u2560','\u2563'),(11,'\u255a','\u255d')):text(row,0,left+'\u2550'*78+right,0x0B)
    for row in (2,3,4,6,7,9,10):text(row,0,'\u2551',0x0B);text(row,79,'\u2551',0x0B)
    for row,label in ((2,'Processor'),(3,'FPU'),(4,'L2 cache'),(6,'Floppy Drive A'),(7,'Floppy Drive B')):text(row,3,label,0x0B)
    for row,label in ((2,'Base Memory'),(3,'Extended Memory'),(4,'Memory Banks'),(6,'COM Ports'),(7,'LPT Ports')):text(row,40,label,0x0B)
    for row,value in ((2,'486+'),(3,'Detected' if fpu else 'Not detected'),(4,cache)):text(row,20,value)
    text(2,58,str(base_kib));text(2,64,'KB');text(3,58,str(ram-1024));text(3,64,'KB');text(4,58,' '.join(str(i) for i in range((ram+16383)//16384)))
    labels=('Not installed','360 KB','1.2 MB','720 KB','1.44 MB, 3.5 in','2.88 MB')
    text(6,20,labels[types>>4]);text(7,20,labels[types&15]);text(6,58,'02F8');text(7,58,'0378')
    for row,position,label in ((9,0,'Primary IDE Master'),(10,1,'Primary IDE Slave')):
        text(row,3,label,0x0B)
        if position in positions:
            text(row,23,'86B_HD'+f'{positions.index(position):02d}')
            text(row,64,'[',0x0B);text(row,65,'15 MB PIO3');text(row,75,']',0x0B)
        else:text(row,23,'Not detected')
    if warnings:
        text(13,3,'POST warnings:',0x0E)
        for bit,column,label in ((1,18,'Clock'),(2,24,'Floppy'),(4,31,'Settings'),(8,40,'Keyboard'),(16,49,'ROM')):
            if warnings&bit:text(13,column,label,0x0E)
    # The controlled86Box input has no ISA PnP cards and no PCI bus. These
    # literal expected rows come from that inventory, not candidate screen data.
    row=14 if warnings else 13
    text(row,0,'PnP/PCI Device Listing')
    text(row+1,0,'Device ID  Device Class CSN:LDN Status     Resources')
    text(row+2,0,'ISA PnP: None')
    if warnings:
        labels=((1,'Clock '),(2,'Floppy '),(4,'Settings '),(8,'Keyboard '),(16,'ROM '),(32,'Other '),(64,'PnP '))
        text(row+3,0,'POST warnings: '+''.join(label for bit,label in labels if warnings&bit))
    assert cells==expected,[(i//160,(i%160)//2,hex(a),hex(b)) for i,(a,b) in enumerate(zip(cells,expected)) if a!=b][:20]
    assert font==Path(reference).read_bytes()[28169:28169+4096],'Original retained Cirrus8x16 font'
    return 'all2000 characters, all2000 attributes and4096 font bytes'
