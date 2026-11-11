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
OUTPUT=os.environ.get('BAIOS_BUILD_DIRECTORY','build');p.OUTPUT=OUTPUT
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

def video_first(port):
 """Execute reset through card activation after RAM and fixed-port checks."""
 messages={
  'init_keyboard':'Checking keyboard...',
  'chipset_visible_ram_test':'Checking memory...',
  'init_peripherals':'Detecting ports...',
  'pnp_configure_isa':'Configuring Plug and Play devices...',
  'init_floppy':'Detecting floppy drives...',
 }
 class Complete(Exception):pass
 class Display(ProbeBus):
  def __init__(self,cards):super().__init__(cards);self.header=False;self.done=False;self.stages=[]
  def output(self,port,size,value):
   if port in (0x279,0xA79):
    assert self.header,'ISA PnP accessed before visible POST'
    assert 'init_peripherals' in self.stages,'ISA PnP accessed before RAM and fixed ports'
   return super().output(port,size,value)
  def observe_startup(self,model,cpu,address,listing):
   if hasattr(self,'entries') and address not in self.entries.values():return
   base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
   if not getattr(self,'rom_scan_hooked',False) and any(cpu.mem_read(base+0x33A,2)):
    from shared.tools.post_fixture import installed_address
    target=installed_address(listing,cpu.mem_read,'pnp_rom_resources')
    def scan(c,a,z,u):assert self.header,'Full option-ROM resource scan preceded visible POST'
    cpu.hook_add(p.UC_HOOK_CODE,scan,None,target,target);self.rom_scan_hooked=True
   if not hasattr(self,'entries'):
    self.entries={name:0xF0000+listing.symbol(name) for name in ('post_ui_begin','init_keyboard','chipset_visible_ram_test','init_peripherals','pnp_configure_isa','init_floppy')}
    for target in self.entries.values():cpu.hook_add(p.UC_HOOK_CODE,lambda c,a,z,u:self.observe_startup(model,c,a,listing),None,target,target)
   if address==self.entries['post_ui_begin'] and 'post_header' not in self.entries:
    from shared.tools.post_fixture import installed_address
    target=installed_address(listing,cpu.mem_read,'post_header');self.entries['post_header']=target
    cpu.hook_add(p.UC_HOOK_CODE,lambda c,a,z,u:self.observe_startup(model,c,a,listing),None,target,target)
   if address==self.entries.get('post_header'):
    assert not self.config_writes and not self.probes
    self.header=True
   for name,target in self.entries.items():
    if address==target and name in messages and (not self.stages or self.stages[-1]!=name):
     row=bytes(cpu.mem_read(0xB8000+22*160,160))[::2].decode('cp437')
     assert row.strip()==messages[name],(name,row)
     self.stages.append(name)
   if address==self.entries['init_keyboard']:
    assert self.header and not self.probes
    header=bytes(cpu.mem_read(0xB8000,160))[::2].decode('cp437')
    cpu_row=bytes(cpu.mem_read(0xB8000+2*160,160))[::2].decode('cp437')
    assert 'bAIos' in header and 'Processor' in cpu_row and cpu_row[24:].strip(),(header,cpu_row)
    assert not any(c.registers[0][0x30] for c in self.cards)
   if address==self.entries['init_floppy']:
    assert self.header
    assert self.stages==['init_keyboard','chipset_visible_ram_test','init_peripherals','pnp_configure_isa','init_floppy'],self.stages
    assert all(c.registers[0][0x30]==1 for c in self.cards),'Card not activated before drives'
    assert bool(self.probes),'ISA discovery was skipped'
    self.done=True;raise Complete
 rows=[]
 for count in (1,):
  bus=Display([card(n+1) for n in range(count)])
  seed=p.settings.Settings(port,OUTPUT);seed.call('settings_load');seed.call('setup_defaults');seed.draft();seed.put('U_HALT',[1]);assert seed.call('settings_save')
  try:p.startup(port,bytes(seed.cmos).hex(),'',pnp_bus=bus,phases=(False,))
  except Complete:pass
  assert bus.done
  rows.append({'cards':count,'visible_header_before_ISA_access':True,'cards_active_before_drives':count,'order':bus.stages,'probes':bus.probes})
 return rows

def video_mode(port):
 from shared.tools.post_fixture import installed_address
 m=p.isa_machine(port,ProbeBus(),OUTPUT);m.call('settings_load');m.call('pnp_module_install')
 restored=[]
 address=installed_address(m.listing,m.cpu.mem_read,'setup_restore_text')
 m.cpu.hook_add(p.UC_HOOK_CODE,lambda c,a,z,u:restored.append(a),None,address,address)
 rows=[]
 for name,changed,theme in (
  ('early',None,0),('ready',None,0),('graphics',(0x449,b'\x13'),0),('columns',(0x44A,b'\x28\0'),0),
  ('page',(0x462,b'\x01'),0),('rows',(0x484,b'\x31'),0),('font',(0x485,b'\x08\0'),0),('theme',None,1)):
  for offset,value in ((0x449,b'\x03'),(0x44A,b'\x50\0'),(0x462,b'\0'),(0x484,b'\x18'),(0x485,b'\x10\0')):m.cpu.mem_write(offset,value)
  if changed:m.cpu.mem_write(*changed)
  m.cpu.mem_write(0x400+m.state['KB_POST_STATE'],bytes([int(name!='early')]))
  m.put('U_THEME_ACTIVE',[theme]);before=len(restored);m.call('post_ui_begin')
  assert len(restored)-before==int(name not in ('ready','early')),name
  rows.append({'case':name,'mode_restore_calls':len(restored)-before})
 return rows

def status(port):
 m=p.isa_machine(port,ProbeBus(),OUTPUT);m.call('settings_load')
 console=Console();m.runtime_interrupt=console.interrupt
 m.put('S_INSTALLED_KIB32',struct.pack('<I',31*1024));m.put('S_INSTALLED_KIB',struct.pack('<H',31*1024))
 m.call('post_ui_begin')
 raw=bytes(m.cpu.mem_read(0xB8000,4000))[::2].decode('cp437')
 assert 'Memory' in raw and '32768' in raw and 'Passed' not in raw,raw
 assert m.get('P_RAM_FLAGS')==b'\0'
 rows=[]
 for stage,expected in enumerate(('', 'Checking keyboard...', 'Checking memory...', 'Checking cache...', 'Detecting ports...', 'Configuring Plug and Play devices...', 'Detecting floppy drives...', 'Detecting IDE drives...', 'Initializing option ROMs...', 'POST complete. Waiting before summary...', 'Rebuilding ESCD...', 'Updating ESCD...', 'ESCD rebuilt.', 'ESCD update failed; will retry.')):
  before=m.snapshot();registers=dict(EAX=0x12340000|stage,EBX=0xABCD,ECX=0x12345678,EDX=0x87654321,ESI=0xDEADBEEF,EDI=0x10203040,EBP=0x55667788)
  m.call('post_status',**registers)
  assert m.snapshot()==before
  assert all(m.cpu.reg_read(getattr(x,'UC_X86_REG_'+name))==value for name,value in registers.items())
  row=bytes(m.cpu.mem_read(0xB8000+22*160,160))[::2].decode('cp437')
  assert row.strip()==expected,row
  assert m.get('P_RAM_FLAGS')==b'\0'
  rows.append({'stage':stage,'message':expected,'registers_preserved':True})
 m.put('C_POST_DELAY',[0]);m.call('post_status',AX=8)
 m.call('post_summary_pause')
 row=bytes(m.cpu.mem_read(0xB8000+22*160,160))[::2].decode('cp437')
 assert row.strip()=='POST complete. Waiting before summary...',row
 return {'unverified_memory_count_visible':True,'messages':rows,'summary_pause_replaces_ROM_status':True}

def post_resources(port):
 from shared.tools.post_fixture import installed_address
 rows=[]
 for count in (0,1):
  cards=[card(1)] if count else [];m=p.isa_machine(port,ProbeBus(cards),OUTPUT)
  m.call('settings_load');configure(m);m.call('pnp_prepare_video')
  refreshed=[];target=installed_address(m.listing,m.cpu.mem_read,'pnp_init_peripherals')
  m.cpu.hook_add(p.UC_HOOK_CODE,lambda c,a,z,u:refreshed.append(a),None,target,target)
  m.call('pnp_configure_post')
  assert len(refreshed)==count,(count,refreshed)
  assert all(c.registers[0][0x30]==1 for c in cards)
  rows.append({'cards':count,'BIOS_port_table_refreshes':len(refreshed),'active_cards':count})
 return rows

def presentation(port):
 m=p.isa_machine(port,ProbeBus(),OUTPUT);m.call('settings_load')
 if port=='mp386':
  original=m.call
  # The inline listing retains inactive facade labels before the real bodies.
  def inline(name,**registers):
   if name in ('post_ui_begin','post_ui_disks','post_ui_disk','post_ui_roms','post_ui_rom','post_message_cursor','post_debug_summary'):name='post_ui_'+name
   return original(name,**registers)
  m.call=inline
 m.state['S_PRESENT']=m.state['STATE_BASE']
 m.state['S_ATA_DEVICE']=m.state['STATE_BASE']+5
 console=Console();m.runtime_interrupt=console.interrupt
 if port=='m919':m.state.update(p.settings.constants(ROOT/port/'src/hardware/board-definition.inc'))
 def row(n):return bytes(m.cpu.mem_read(0xB8000+n*160,160))[::2].decode('cp437')
 m.put('P_PHASE',[4]);m.cpu.mem_write(0x400+m.state['KB_POST_STATE'],b'\1')
 count=4 if port=='m919' else 2
 names=('Primary IDE Master','Primary IDE Slave','Secondary Master','Secondary Slave')
 cases=[]
 for controllers,enables in (([1]*count,[1]*count),([1]*count,[0]+[1]*(count-1)),([1,1,0,0][:count],[1]*count),([0]*count,[1]*count)):
  for i in range(count):
   base=m.base+i*0x200
   for field,value in (('S_CONTROLLER',controllers[i]),('S_ENABLED' if count==4 else 'C_HDD',enables[i]),('S_PRESENT',1)):
    m.cpu.mem_write(base+m.state[field],bytes([value]))
   m.cpu.mem_write(base+m.state['S_MODEL'],f'Device{i}'.encode()+b'\0')
   m.cpu.mem_write(base+m.state['S_ATA_DEVICE'],bytes([0x10 if i%2 else 0]))
   if count==4:m.cpu.mem_write(base+m.state['HW_POSITION'],bytes([i]))
  m.call('post_ui_disks')
  expected=[bool(controllers[i] and enables[i]) for i in range(count)]
  for i,visible in enumerate(expected):
   assert (names[i] in row(11+i))==visible,(i,visible,row(11+i))
   if not visible:assert not row(11+i)[3:79].strip(),row(11+i)
  # Single-probe publication follows the same visibility rule as a redraw.
  for i in range(count):m.call('post_ui_disk',FS=(m.base+i*0x200)>>4)
  for i,visible in enumerate(expected):assert (names[i] in row(11+i))==visible,row(11+i)
  m.put('C_POST_DELAY',[0]);m.call('post_debug_summary')
  for i,visible in enumerate(expected):assert (names[i] in row(9+i))==visible,row(9+i)
  cases.append({'controllers':controllers,'enabled':enables,'visible':expected})
 m.call('post_ui_begin');m.call('post_ui_roms')
 assert not row(15).strip() and 'VGA BIOS' in row(16),(row(15),row(16))
 for _ in range(5):m.call('post_ui_rom',DX=0xC800)
 assert not row(15).strip() and 'Option ROMs' in row(18) and '5' in row(18)
 if port=='m919':
  m.put('HW_CACHE_CODE',[3]);m.put('HW_CACHE_FLAGS',[4])
  choice_row=next(i for i,line in enumerate(m.listing.lines) if 'chip_l2_values dw' in line)
  choices=0xF0000+m.listing.offset(choice_row-1)
  for saved in (0,1):
   # The actual Setup table owns stored-value meaning, including active-low fields.
   label=struct.unpack('<H',m.cpu.mem_read(choices+saved*2,2))[0]
   m.cpu.mem_write(0xB8000+4*160,b'\x20\x07'*80)
   m.call('setup_text',SI=label,DI=4*160+24*2,BX=7<<8)
   expected=row(4)[24:].strip()
   assert expected==('Enabled','Disabled')[saved],expected
   m.put('C_CHIP',bytes([0,0,saved,0x40]));m.call('post_ui_cache')
   assert row(4)[24:].strip()==expected,(saved,expected,row(4))
  m.call('post_debug_summary');assert '256 KB WB' in row(4),row(4)
  m.put('P_RAM_FLAGS',[4]);m.call('post_ui_begin')
  assert not row(5).strip() and 'RAM Test' in row(6),(row(5),row(6))
 features=row(24)[40:]
 assert 'APM 1.2' in features and ('PnP 1.0' in features)==(port!='mp386'),features
 assert row(24)[78]!=' ' and row(24)[79]==' ',row(24)
 assert len(features.strip())+10<=39,'Keep room for a future ACPI version'
 m.call('post_debug_summary');assert not row(24).strip(),row(24)
 m.call('post_ui_begin');assert row(24)[40:]==features,row(24)
 m.cpu.mem_write(0x400+m.state['KB_FLAGS'],b'\0')
 m.cpu.mem_write(0x400+m.state['KB_POST_STATE'],b'\1')
 regs=dict(EAX=0x12345300,EBX=0x12345678,ECX=0xAABBCCDD,EDX=0x11223344,ESI=0x10203040,EDI=0x55667788,EBP=0x1234,DS=0x40,ES=0x4567)
 m.call('keyboard_enqueue',**regs)
 assert m.get('S_SETUP_REQUEST')==b'\1' and row(24)[:40].strip()=='Entering setup...',row(24)
 assert row(24)[40:]==features,row(24)
 assert all(m.cpu.reg_read(getattr(x,'UC_X86_REG_'+name))==value for name,value in regs.items())
 for name,regs in (('post_status',{'AX':8}),('post_message_cursor',{}),('post_ui_disks',{}),('post_ui_roms',{}),('post_ui_begin',{})):
  m.call(name,**regs);assert row(24)[:40].strip()=='Entering setup...',(name,row(24))
  assert row(24)[40:]==features,(name,row(24))
 m.put('S_SETUP_REQUEST',[0]);m.call('post_ui_begin');assert 'Del: Setup' in row(24),row(24)
 return {'IDE_visibility_live_single_and_summary':cases,'ROM_separator_and_scroll':True,'Delete_immediate_and_persistent_across_pending_operations':True,'L2_matches_compiled_Setup_choices_and_RAM_separator':port=='m919','features':features.strip(),'features_right_aligned_and_cleared_on_summary':True,'ACPI_room_available':True}

def escd_messages(port):
 rows=[]
 for kind in ('regular','clear','write_failure','incomplete'):
  cards=[card(1)]
  if kind=='incomplete':cards=[card(1,b'\x15\x41\xD0\x05\x01\x01\x47'+bytes([0xFF,0,3,0,3,0,8]))]
  m=p.isa_machine(port,ProbeBus(cards),OUTPUT);m.call('settings_load');m.call('setup_defaults');m.draft()
  m.put('U_HALT',[1]);policy=bytearray(15);policy[14]=int(kind!='regular');m.put('U_PNP',policy)
  assert m.call('settings_save');m.call('settings_load');configure(m);m.call('pnp_publish');m.call('pnp_prepare_video')
  console=Console();m.runtime_interrupt=console.interrupt;m.put('P_PHASE',[4]);m.call('post_ui_begin')
  notices=[];target=0xF0000+m.listing.symbol('post_status')
  m.cpu.hook_add(p.UC_HOOK_CODE,lambda c,a,z,u:notices.append(c.reg_read(x.UC_X86_REG_AL)),None,target,target)
  m.call('pnp_configure_isa')
  if kind!='regular':assert bytes(m.cpu.mem_read(0xB8000+22*160,160))[::2].decode('cp437').strip()=='Rebuilding ESCD...'
  if kind=='write_failure':m.fail=('cmos',0x35)
  m.call('pnp_finish_entry')
  message=bytes(m.cpu.mem_read(0xB8000+22*160,160))[::2].decode('cp437').strip()
  pending=m.get('C_PNP',15)[14]
  if kind=='regular':assert not notices and pending==0
  elif kind=='clear':assert notices==[10,11,12] and pending==0 and message=='ESCD rebuilt.',(notices,pending,message)
  else:assert notices[-1]==13 and pending==1 and message=='ESCD update failed; will retry.',(notices,pending,message)
  assert not any(m.cpu.mem_read(m.base+0x338,4)),'Private module must already be released'
  rows.append({'case':kind,'notices':notices,'pending_request':pending,'message':message})
 return rows

def video_extent(port):
 m=p.isa_machine(port,ProbeBus(),OUTPUT);m.call('settings_load');configure(m)
 m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));m.call('pnp_publish')
 raw=bytearray(32768);raw[:4]=bytes.fromhex('55 AA 40 CB');raw[-1]=(-sum(raw))&255
 m.cpu.mem_write(0xC0000,bytes(raw));m.call('pnp_prepare_video')
 assert m.call('pnp_claim_query',AX=0x100,EDX=0xC0000,ECX=32768)
 assert m.call('pnp_rom_enter',AX=0xFFFF,DX=0xC000,CX=2)
 m.cpu.mem_write(0xC0000,b'\0\0\0') # A returning display no longer exposes its original header.
 assert not m.call('pnp_claim_query',AX=0x100,EDX=0xC0000,ECX=32768)
 m.call('pnp_configure')
 assert not m.call('pnp_claim_query',AX=0x100,EDX=0xC0000,ECX=32768)
 return {'original_display_extent_owned_after_header_replacement_and_ISA_configuration':True}

def resource_ready(port):
 rows=[]
 class Delayed(ProbeBus):
  def input(self,port,size):
   if port==self.read_port and self.address==5:
    self.status_reads+=1
    self.ready=self.deadline is not None and self.ticks>=self.deadline
    return int(self.ready)
   return super().input(port,size)
 for delay_us in (0,100,1000,190000,None):
  c=card(1);c.csn=1;bus=Delayed([c]);bus.deadline=0
  m=p.isa_machine(port,bus,OUTPUT)
  m.call('pnp_isa_key');m.call('pnp_isa_read_port',DX=0x20B);m.call('pnp_isa_write',AX=0x103)
  before=bus.ticks;bus.deadline=None if delay_us is None else before+(delay_us*1193182+999999)//1000000
  success=m.call('pnp_isa_resource_byte',DX=0x20B)
  elapsed=(bus.ticks-before)*1000000/1193182
  assert success==(delay_us is not None)
  if delay_us is None:assert 200000<=elapsed<250000 and not bus.resource_reads
  elif delay_us==0:assert elapsed==0 and bus.status_reads==1
  else:assert delay_us<=elapsed<delay_us+400 and bus.resource_reads==1,(delay_us,elapsed)
  rows.append({'device_ready_us':delay_us,'elapsed_us':elapsed,'polls':bus.status_reads,'success':success})
 return rows

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--port',choices=PORTS,required=True);a.add_argument('--case',choices=('probes','table','screen','summary','video_first','video_mode','video_extent','resource_ready','status','post_resources','presentation','escd_messages'),required=True);args=a.parse_args()
 result={args.port:{args.case:globals()[args.case](args.port)}}
 folder=ROOT/args.port/OUTPUT
 if folder==ROOT/args.port/'build':folder=folder/'tests/video-first'
 folder.mkdir(parents=True,exist_ok=True)
 out=folder/('live-'+args.case+'.json');out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


