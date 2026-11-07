"""Focused live POST probe policy and actual-device console proofs."""
import os,argparse,importlib.util,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=load('live_pnp','shared/tests/test-pnp.py')
from shared.tools.isa_pnp_proof import Bus,Card,serial
from shared.tools.pci_proof import PCI,Endpoint
from unicorn import x86_const as x
OUTPUT=os.environ.get('BAIOS_BUILD_DIRECTORY','build/tests/pnp-live-table');p.OUTPUT=OUTPUT
PORTS=('m919','pb430','presario-800')
CANDIDATES=(0x20B,0x20F,0x213,0x217,0x21B,0x21F,0x263,0x283,0x2A3,0x2C3,0x2E3,0x323,0x343,0x363,0x383,0x3A3,0x3E3)
PREFIX=b'\x0A\x10\0\x82\x03\0ISA'
def device(base=0x300):return b'\x15\x41\xD0\x05\x01\x01\x47'+struct.pack('<BHHBB',1,base,base,0,8)
def card(n,body=None):return Card(serial(b'\x41\xD0\xFF\xFF',n),PREFIX+(device(0x300+n*16) if body is None else body)+b'\x79\0')
class ProbeBus(Bus):
 def __init__(self,cards=(),kind='plain'):
  super().__init__(cards);self.pause=False;self.probes=[];self.kind=kind
 def output(self,port,size,value):
  if port==0x279 and value==1 and self.enabled:self.probes.append(self.read_port)
  return super().output(port,size,value)
 def input(self,port,size):
  if port==self.read_port and self.address==1:
   if self.kind=='retry':self.conflicts[port]='checksum' if port==CANDIDATES[0] else None
   if self.kind=='unresolved':self.conflicts[port]='checksum' if port==CANDIDATES[0] else 'no-pair'
   if self.kind=='late':self.conflicts[port]='checksum' if any(c.csn for c in self.cards) else None
  return super().input(port,size)
def root(m):return bytes(m.cpu.mem_read(int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little'),32))
def configure(m):
 if m.port=='m919':m.cpu.mem_write(m.base+0x1000,b'\xFF\xFF')
def probes(port):
 rows=[]
 for kind,count,owned in (('empty',0,False),('present',3,False),('retry',2,False),('unresolved',1,False),('late',2,False),('skip',1,True),('all-owned',0,True)):
  cards=[card(n+1) for n in range(count)];bus=ProbeBus(cards,kind)
  policy=bytearray(15)
  if owned:policy[3:7]=struct.pack('<HH',CANDIDATES[0],0x200 if kind=='all-owned' else 1)
  m,bus=p.allocation_fixture(port,cards,policy,bus=bus,configure=configure)
  data=root(m);status=data[19];csns=data[18]
  if kind=='empty':
   assert bus.probes==[0x20B] and csns==0 and status==0
   assert bus.status_reads==bus.resource_reads==0
   elapsed=bus.ticks/1193182;assert .018<elapsed<.021,elapsed
  elif kind=='unresolved':
   assert status and not csns and bus.probes==list(CANDIDATES)
   assert bus.status_reads==bus.resource_reads==0
  elif kind=='late':assert status and csns==1 and set(bus.probes)=={0x20B}
  elif kind=='all-owned':assert status and csns==0 and not bus.probes and not bus.status_reads
  else:
   expected=0x20F if kind in ('retry','skip') else 0x20B
   assert status==0 and csns==count and bus.read_port==expected,(kind,status,csns,bus.probes)
   assert all(c.registers[0][0x30]==1 for c in cards)
   assert bus.probes[-1]==expected and bus.bit==64,'Normal silent list end must omit checksum'
  rows.append({'kind':kind,'probes':bus.probes,'CSNs':csns,'incomplete':bool(status),'PIT_seconds':bus.ticks/1193182,'resource_polls':bus.status_reads})
 return rows
class Console:
 def __init__(self):self.text='';self.row=0;self.col=0;self.scrolls=0;self.rows=[' '*80 for _ in range(25)]
 def interrupt(self,cpu,vector):
  if vector!=0x10:return False
  ax=cpu.reg_read(x.UC_X86_REG_AX)
  if ax>>8==0:
   self.row=self.col=0;self.rows=[' '*80 for _ in range(25)]
  elif ax>>8==2:self.col=cpu.reg_read(x.UC_X86_REG_DL);self.row=cpu.reg_read(x.UC_X86_REG_DH)
  elif ax>>8==3:cpu.reg_write(x.UC_X86_REG_DX,self.row<<8|self.col)
  if ax>>8==0xE:
   self.rows=[''.join(chr(v) for v in bytes(cpu.mem_read(0xB8000+n*160,160))[::2]) for n in range(25)]
   ch=chr(ax&255);self.text+=ch
   if ch=='\r':self.col=0
   elif ch=='\n':self.row+=1
   else:
    line=self.rows[self.row];self.rows[self.row]=line[:self.col]+ch+line[self.col+1:];self.col+=1
    if self.col==80:self.col=0;self.row+=1
   if self.row==25:self.rows.pop(0);self.rows.append(' '*80);self.row=24;self.scrolls+=1
  cpu.mem_write(0x450,bytes([self.col,self.row]))
  if ax>>8==0xE:
   for n,line in enumerate(self.rows):cpu.mem_write(0xB8000+n*160,b''.join(bytes([ord(ch),7]) for ch in line))
  return True
def table(port):
 cases=[]
 for kind in ('empty','devices','resources','malformed','incomplete'):
  cards=[] if kind=='empty' else [card(1,b''.join(device(0x500+n*16) for n in range(28)))]
  if cards:cards[0].ldns=28;cards[0].reset()
  if kind=='resources':cards=[card(1,device()+b'\x23\x00\x04\x01\x2A\x02\x08'+b'\x81\x09\0\x04'+struct.pack('<HHHH',0xD00,0xD00,256,16))]
  if kind=='malformed':cards=[card(1,b'\x15\x41\xD0\x05\x01\x01\x47'+bytes([0xFF,0,3,0,3,0,8]))]
  bus=ProbeBus(cards,'unresolved' if kind=='incomplete' else 'plain')
  if port=='m919':
   endpoint=Endpoint(cls=0x020000,pin=1);endpoint.write(4,2,3);endpoint.write(0x3C,2,0x010B)
   bus.pci=PCI({0x68:endpoint});bus.pci_address=0
  m,bus=p.allocation_fixture(port,cards,bus=bus,configure=configure)
  console=Console();m.runtime_interrupt=console.interrupt
  before=m.snapshot();m.writes.clear()
  assert m.call('pnp_post_invoke',BX=m.listing.symbol('pnp_post_table'))
  assert m.snapshot()==before and not m.writes
  output=console.text
  assert 'PnP/PCI Device Listing' in output and 'Device ID' in output
  if port=='m919':assert 'PCI 00:0D.0' in output and 'Network' in output and '11 Enabled' in output,output
  if kind=='empty':assert 'ISA PnP: None' in output and 'incomplete' not in output
  elif kind=='incomplete':assert 'configuration incomplete' in output and 'ISA PnP: None' not in output
  elif kind=='resources':
   assert 'Active' in output and 'IRQ10' in output and 'DMA1' in output and 'MEM 000D0000-000D0FFF' in output,output
  elif kind=='malformed':
   assert 'Inactive' in output and 'Active' not in output and 'configuration incomplete' in output,output
  else:
   assert output.count('PNP0501')==28 and console.scrolls>0,(output,console.scrolls)
   assert '01:1B' in output and 'Active' in output and 'IO 0500-0507' in output and 'IO 06B0-06B7' in output,output
   assert all(c.state=='wait' for c in cards)
  cases.append({'kind':kind,'rendered':output,'scrolls':console.scrolls,'writes':len(m.writes)})
 return cases
def summary(port):
 rows=[]
 for amount in (0,5,6,28):
  cards=[] if not amount else [card(1,b''.join(device(0x500+n*16) for n in range(amount)))]
  if cards:cards[0].ldns=amount;cards[0].reset()
  m,bus=p.allocation_fixture(port,cards,bus=ProbeBus(cards),configure=configure)
  m.put('C_POST_DELAY',[0]);console=Console();m.runtime_interrupt=console.interrupt
  original=m.base;before=m.snapshot();m.call('pnp_publish_finish')
  final=int.from_bytes(m.cpu.mem_read(0x40E,2),'little')<<4
  kib=int.from_bytes(m.cpu.mem_read(0x413,2),'little')
  assert kib==final>>10 and final<original
  assert m.cpu.mem_read(final+0x338,4)==bytes(4)
  assert bytes(m.cpu.mem_read(final,1))[0]>=original//1024-kib
  text='\n'.join(''.join(chr(v) for v in bytes(m.cpu.mem_read(0xB8000+n*160,160))[::2]) for n in range(25))
  assert str(kib)+' ' in text,(text,console.text)
  assert text.count('Base Memory')+text.count('Base memory:')==1,text
  if amount==28:assert '01:1B' in text,text
  assert m.snapshot()==before
  rows.append({'LDNs':amount,'final_base':final,'BDA413':kib,'visible':text,'resident_release':True})
 return rows

def screen(port):
 bus=ProbeBus();m=p.isa_machine(port,bus,OUTPUT);m.call('settings_load')
 states=[]
 for armed in (0,1):
  m.cpu.mem_write(0x400+m.state['KB_POST_STATE'],bytes([armed]))
  m.call('post_ui_begin')
  raw=bytes(m.cpu.mem_read(0xB8000,4000))[::2]
  footer=raw[24*80:25*80].decode('cp437')
  assert ('Delete' in footer or 'Del' in footer)==bool(armed),footer
  states.append({'keyboard_ready':armed,'footer':footer})
 class Complete(Exception):pass
 class Display(ProbeBus):
  def __init__(self):super().__init__();self.visited=False;self.done=False
  def observe_startup(self,model,cpu,address,listing):
   if not hasattr(self,'entries'):
    self.entries={name:0xF0000+listing.symbol(name) for name in ('post_ui_begin','init_keyboard')}
    for target in self.entries.values():cpu.hook_add(p.UC_HOOK_CODE,lambda c,a,z,u:self.observe_startup(model,c,a,listing),None,target,target)
   if address==self.entries['post_ui_begin'] and 'post_header' not in self.entries:
    from shared.tools.post_fixture import installed_address
    target=installed_address(listing,cpu.mem_read,'post_header');self.entries['post_header']=target
    cpu.hook_add(p.UC_HOOK_CODE,lambda c,a,z,u:self.observe_startup(model,c,a,listing),None,target,target)
   if address==self.entries['init_keyboard']:self.visited=True
   if address==self.entries.get('post_header'):
    assert not self.visited,'Keyboard initialization preceded visible POST'
    assert cpu.mem_read(0x400+m.state['KB_POST_STATE'],1)==b'\0'
    self.done=True;raise Complete
 d=Display();seed=p.settings.Settings(port,OUTPUT);seed.call('settings_load');seed.call('setup_defaults');seed.draft();seed.put('U_HALT',[1]);assert seed.call('settings_save')
 try:p.startup(port,bytes(seed.cmos).hex(),'',pnp_bus=d,phases=(False,))
 except Complete:pass
 assert d.done
 return {'real_rendered_footer':states,'actual_reset_first_header_before_keyboard':True}

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--port',choices=PORTS,required=True);a.add_argument('--case',choices=('probes','table','screen','summary'),required=True);args=a.parse_args()
 result={args.port:{args.case:globals()[args.case](args.port)}}
 out=ROOT/args.port/OUTPUT/('live-'+args.case+'.json');out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


