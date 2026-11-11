"""Focused saved POST delay, page-link hints and PCI/ISA display selection proofs."""
import os,argparse, importlib.util, json, struct, sys
from functools import cache
from pathlib import Path
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn import x86_const as x
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
settings=load('post_settings','shared/tests/test-pnp-settings.py')
pnp=load('post_pnp','shared/tests/test-pnp.py')
text=load('post_text','shared/tests/test-ui-text.py')
from shared.tools.isa_pnp_proof import Bus,Card,serial
from shared.tools.pci_proof import PCI,Endpoint
PORTS=('m919','mp386','pb430','presario-800')
OUTPUT=os.environ.get('BAIOS_BUILD_DIRECTORY','build/tests/post-options')
def fresh(port):
 m=settings.ui_model(port,OUTPUT);m.listing.symbol=cache(m.listing.symbol);return m

def persistence(port):
 m=fresh(port)
 fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
 m.cmos[:]=bytes.fromhex(fixture['cmos']);m.nvram[0x200:0x240]=bytes.fromhex(fixture['nvram_0200_023f'])
 assert m.cmos[0x3A]==5
 before=m.snapshot();m.call('settings_load')
 assert not m.writes and m.snapshot()==before and m.get('C_POST_DELAY')==b'\1'
 if port=='m919':assert m.get('C_VIDEO_ORDER')==b'\1'
 logical={k:m.get(k,len(bytes.fromhex(v))) for k,v in fixture['expected'].items()}
 base_fields=('C_TYPES','C_HDD','C_BOOT','C_SEEK','C_SLAVE','C_THEME','C_CLOCK24','C_NUMLOCK','C_SWAP','C_HALT','C_BOOT_SECOND','C_BOOT_THIRD','C_BOOT_FOURTH')
 base_values={k:m.get(k) for k in base_fields}
 assert logical=={k:bytes.fromhex(v) for k,v in fixture['expected'].items()}
 # An untouched real Setup Save migrates the base while preserving every extension.
 m.ui([0x4400,13]);assert m.reset and m.cmos[0x3A]==6;m.call('settings_load')
 assert m.get('C_POST_DELAY')==b'\1'
 assert all(m.get(k)==v for k,v in base_values.items())
 assert all(m.get(k,len(v))==v for k,v in logical.items())
 pointers=text.address(m,'u_boot_pointers');count=(text.address(m,'u_boot_labels')-pointers)//2
 fields=struct.unpack('<'+'H'*count,m.cpu.mem_read(0xF0000+pointers,2*count))
 field=fields.index(m.state['U_POST_DELAY']);assert fields.count(m.state['U_POST_DELAY'])==1
 keys=[0x5000]*2+[9]+[0x5000]*field
 m.ui(keys+[13,0x4D00,13,0x3B00,27,0x4400,13]);assert m.reset
 m.call('settings_load');assert m.get('C_POST_DELAY')==b'\2'
 assert any(b'POST Delay (Seconds)' in row and b'10' in row for row in m.screen)
 assert any(b'0' in row[10*80:11*80] and b'5' in row[11*80:12*80] and b'10' in row[12*80:13*80] for row in m.screen)
 saved=m.snapshot();m.writes.clear()
 m.ui(keys+[0x4B00,0x4B00,27,27,13]);assert not m.reset and m.snapshot()==saved and not m.writes
 m.ui(keys+[0x4300,13,27,27,13]);assert not m.reset and m.snapshot()==saved and m.get('U_POST_DELAY')==b'\1'
 if port=='m919':
  vf=fields.index(m.state['U_VIDEO_ORDER']);assert fields.count(m.state['U_VIDEO_ORDER'])==1
  m.ui([0x5000]*2+[9]+[0x5000]*vf+[13,0x4B00,13,0x4400,13]);m.call('settings_load')
  assert m.get('C_VIDEO_ORDER')==b'\0' and m.get('C_POST_DELAY')==b'\2'
  assert any(b'ISA/PCI' in row[10*80:11*80] and b'PCI/ISA' in row[11*80:12*80] for row in m.screen)
 assert all(m.get(k,len(v))==v for k,v in logical.items())
 for row in m.screen:
  for line in range(5,12):assert b'\x1A' not in row[line*80+2:line*80+20]
  if b'SELECT VALUE' in row[8*80:9*80]:
   for line in range(10,22):assert b'\x1A' not in row[line*80+26:line*80+78]
 return {'old_schema5_read_only_default5':True,'real_Save_migration_preserves_complete_logical_settings':True,
  'actual_sorted_choices_help_Save_Discard_defaults':True,'no_main_or_value_popup_arrows':True,'boot_rows':count}

class TimerBus(Bus):
 def __init__(self,keys=()):super().__init__([]);self.keys=list(keys);self.delivered=[];self.pause_wake=False
 def output(self,port,size,value):
  if port==0x43 and value==0:self.ticks+=24 #32 input clocks/sample, independent mode3 countdown.
  return super().output(port,size,value)
 def input(self,port,size):
  if port==0x64:return int(bool(self.keys))
  if port==0x60:
   value=self.keys.pop(0);self.delivered.append(value);return value
  return super().input(port,size)

def timer(port):
 rows=[]
 for index in (0,1,2):
  bus=TimerBus()
  if port=='mp386':
   class Machine(settings.Settings):
    def inp(self,c,p,z,u):
     v=bus.input(p,z);return super().inp(c,p,z,u) if v is None else v
    def out(self,c,p,z,v,u):
     if not bus.output(p,z,v):super().out(c,p,z,v,u)
   m=Machine(port,OUTPUT)
  else:m=pnp.isa_machine(port,bus,OUTPUT)
  m.listing.symbol=cache(m.listing.symbol)
  m.call('settings_load');m.call('setup_defaults');m.draft();m.put('U_POST_DELAY',[index]);assert m.call('settings_save');m.call('settings_load')
  m.cpu.mem_write(0x41A,struct.pack('<HH',0x1E,0x1E))
  before=m.snapshot();start=bus.ticks
  m.call('post_summary_pause',EFLAGS=2)
  elapsed=(bus.ticks-start)/1193182
  assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200==0
  assert index*5<=elapsed<=index*5*1.04+0.002,(port,index,elapsed)
  assert m.snapshot()==before
  rows.append({'seconds':index*5,'actual_PIT_input_seconds':elapsed,'IF_preserved':True})
 return {'saved_delay_0_5_10_and_wrap':rows}


def keyboard(port,kinds=('Delete','Pause')):
 rows=[]
 for kind,scans in (('Delete',(0xE0,0x53)),('Pause',(0xE1,0x1D,0x45,0xE1,0x9D,0xC5))):
  if kind not in kinds:continue
  bus=TimerBus(scans)
  if port=='mp386':
   class Machine(settings.Settings):
    def inp(self,c,p,z,u):
     v=bus.input(p,z);return super().inp(c,p,z,u) if v is None else v
    def out(self,c,p,z,v,u):
     if not bus.output(p,z,v):super().out(c,p,z,v,u)
    def interrupt(self,c,v,u):
     if self.runtime_interrupt(c,v):return
     return super().interrupt(c,v,u)
   m=Machine(port,OUTPUT)
  else:m=pnp.isa_machine(port,bus,OUTPUT)
  m.listing.symbol=cache(m.listing.symbol)
  def interrupt(cpu,vector):
   if vector in (9,0x15):
    pnp.Caller.inject(m,'int09' if vector==9 else 'int15',cpu.reg_read(x.UC_X86_REG_IP));return True
   return False
  m.runtime_interrupt=interrupt
  m.call('settings_load');m.call('setup_defaults');m.draft();assert m.call('settings_save');m.call('settings_load')
  m.cpu.mem_write(0x41A,struct.pack('<HH',0x1E,0x1E))
  m.keys=[27,13] if kind=='Delete' else []
  paused=[]
  if kind=='Pause':
   target=0xF0000+m.listing.symbol('.pause','int09')+1
   def wake(cpu,address,size,unused):
    assert bytes(cpu.mem_read(address,1))==b'\xF4'
    assert cpu.mem_read(0x400+m.state['KB_POST_STATE'],1)==b'\3'
    paused.append(True)
    if not bus.keys:bus.keys.append(0x39)
    # External IRQ wakes the real HLT; resume at its following CLI.
    pnp.Caller.inject(m,'int09',cpu.reg_read(x.UC_X86_REG_IP)+1)
   hook=m.cpu.hook_add(UC_HOOK_CODE,wake,None,target,target)
  before=m.snapshot()
  registers={name:(index+1)*0x1234567 for index,name in enumerate(('EAX','EBX','ECX','EDX','ESI','EDI','EBP'))}
  try:m.call('post_summary_pause',EFLAGS=0x202,**registers)
  finally:
   if kind=='Pause':m.cpu.hook_del(hook)
  assert all(m.cpu.reg_read(getattr(x,'UC_X86_REG_'+reg))==value for reg,value in registers.items())
  assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200
  assert not bus.keys and not m.keys and m.snapshot()==before
  if kind=='Delete':assert any(b'bAIos Setup' in row for row in m.screen)
  else:assert paused and bus.delivered[-1]==0x39
  assert m.cpu.mem_read(0x400+m.state['KB_POST_STATE'],1)==b'\2'
  rows.append({'input':kind,'actual_INT09_PIT_and_gate':True,'real_Setup_Discard':kind=='Delete',
   'actual_Pause_HLT_and_external_IRQ_resume':kind=='Pause','full_GP_and_IF_preserved':True})
 return {'during_saved_default_pause':rows}


def video():
 rows=[]
 for order,isa_kind,pci_present in ((1,'valid',True),(0,'valid',True),(0,'absent',True),(0,'invalid',True),(1,'valid',False)):
  chosen=Endpoint(cls=0x030000,rom_mask=0xFFFF8000,bars={0x10:0xFFF00000,0x14:0xFFFFFFF1})
  other=Endpoint(cls=0x030000,rom_mask=0xFFFF8000,bars={0x10:0xFFF00000,0x14:0xFFFFFFF1})
  endpoints={0x60:chosen,0x68:other} if pci_present else {}
  class VideoBus(Bus):
   def input(self,port,size):
    if port==0x8F0:self.witness+=1;return 0x5A
    return super().input(port,size)
  card=Card(serial(b'\x41\xD0\xFF\xFF',1),b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x79\0')
  bus=VideoBus([card]);bus.pause=False;bus.witness=0;bus.pci=PCI(endpoints);bus.pci_address=0
  m=pnp.isa_machine('m919',bus,OUTPUT);m.call('settings_load');m.call('setup_defaults');m.draft();m.put('U_VIDEO_ORDER',[order]);assert m.call('settings_save')
  def image(marker):
   raw=bytearray(32768);raw[:3]=b'\x55\xAA\x40'
   # External init is actual code; its marker and I/O witness distinguish providers.
   code=bytes.fromhex('1E50BAF008EC31C08ED8C70640000001C706420000C0C6060006')+bytes([marker])+bytes.fromhex('581FCB')
   raw[3:3+len(code)]=code;raw[0x100]=0xCF;raw[-1]=(-sum(raw))&255;return bytes(raw)
  isa=image(0xA1);pci=image(0xB2)
  if isa_kind=='invalid':isa=isa[:-1]+bytes([isa[-1]^1])
  if isa_kind=='absent':isa=b'\xFF'*32768
  # Warm retained PCI decode must not be mistaken for the independent ISA image.
  for endpoint in endpoints.values():endpoint.write(0x30,4,0xC0001);endpoint.write(4,2,3)
  def decoded(cpu,access,address,size,value,unused):
   active=[e for e in endpoints.values() if e.read(4,2)&2 and e.read(0x30,4)==0xC0001]
   raw=pci if active else isa
   cpu.mem_write(address,raw[address-0xC0000:address-0xC0000+size])
  hook=m.cpu.hook_add(UC_HOOK_MEM_READ,decoded,None,0xC0000,0xC7FFF)
  try:
   m.call('pnp_early');assert not bus.witness
   expected_pci=pci_present and (order==1 or isa_kind!='valid')
   expected=0x60 if expected_pci else 0xFFFF
   assert int.from_bytes(m.cpu.mem_read(m.base+0x1000,2),'little')==expected
   m.call('pci_initialize')
   for bdf,e in endpoints.items():
    assert bool(e.read(4,2)&3)==bool(expected_pci and bdf==0x60),(order,isa_kind,bdf,e.read(4,2))
    assert e.read(0x30,4)==(0xC0001 if expected_pci and bdf==0x60 else 0)
   m.cpu.mem_write(0x40,struct.pack('<HH',0,0xF000));assert m.call('initialize_video')
   assert bus.witness==1 and m.cpu.mem_read(0x600,1)==bytes([0xB2 if expected_pci else 0xA1])
  finally:m.cpu.hook_del(hook)
  rows.append({'order':('ISA/PCI','PCI/ISA')[order],'ISA':isa_kind,'PCI_present':pci_present,'selected':expected,
   'actual_init_marker':m.cpu.mem_read(0x600,1)[0],'nonselected_decode_off_after_BAR_allocator':True})
 return {'actual_early_PCI_init_then_video_order_and_fallback':rows}

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',choices=('all',)+PORTS,default='all');parser.add_argument('--case',choices=('settings','timer','keyboard','video','all'),required=True);args=parser.parse_args()
 ports=PORTS if args.port=='all' else (args.port,);result={}
 for port in ports:
  result[port]={}
  if args.case in ('all','settings'):result[port]['settings']=persistence(port)
  if args.case in ('all','timer'):result[port]['timer']=timer(port)
  if args.case in ('all','keyboard'):result[port]['keyboard']=keyboard(port)
  if port=='m919' and args.case in ('all','video'):result[port]['video']=video()
 print(json.dumps(result,indent=2))
