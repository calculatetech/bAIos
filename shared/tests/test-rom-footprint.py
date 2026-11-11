"""Prove common transient UI placement and report net ROM/RAM footprints."""
import argparse,hashlib,importlib.util,json,os,re,struct,subprocess,sys
from pathlib import Path
from functools import cache
from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
pnp=load('footprint_pnp','shared/tests/test-pnp.py')
settings=pnp.settings
PORTS=('m919','pb430','presario-800','mp386')
OUTPUT='build/tests/rom-footprint';pnp.OUTPUT=OUTPUT
FIXTURE=ROOT/'shared/tests/fixtures/rom-footprint-baseline.json'
REGS=('EAX','EBX','ECX','EDX','ESI','EDI','EBP','DS','ES','FS','GS','SS','SP','EFLAGS')

def prepare(port):
 if port=='presario-800':command=['pwsh','-NoProfile','-File',str(ROOT/port/'tools/build.ps1'),'-OutputDirectory',OUTPUT]
 elif port=='m919':command=[sys.executable,'-B',str(ROOT/'tools/build-rom.py'),port,'--output',OUTPUT]
 else:command=[sys.executable,'-B',str(ROOT/port/'tools/build.py'),'--output',OUTPUT]
 subprocess.run(command,cwd=ROOT,check=True,stdout=sys.stderr)

def fixture_model(port):
 m=settings.ui_model(port,OUTPUT);m.listing.symbol=cache(m.listing.symbol);return m

def profiles(port):
 return [('post_ui_begin',phase,0) for phase in (0,1,3,5)]+[('setup_draw',0,page) for page in range(6 if port=='mp386' else 7)]

def oracle_profile(m,owner,phase,page,version,baseline_version=None,baseline_date=None):
 m.call('settings_load');m.call('setup_defaults');m.draft()
 m.cpu.mem_write(0x413,struct.pack('<H',480)) # Controlled renderer input; startup checks use real accounting.
 m.put('P_PHASE',[phase]);m.put('U_PAGE',[page]);m.put('U_FOCUS',[1]);m.put('U_FIELD',[0]);m.put('U_CHIP_SCREEN',[0]);m.put('U_PNP_SCREEN',[0])
 registers={r:(n+1)*0x1234567 for n,r in enumerate(REGS[:7])}
 registers.update(DS=0xF000 if owner=='setup_draw' else 0x3456,ES=0xB800 if owner=='setup_draw' else 0x4567,GS=0x5678,EFLAGS=0x247)
 m.call(owner,**registers)
 raw=bytearray(m.cpu.mem_read(0xB8000,4000));plane=bytes(raw[::2]);matches=list(re.finditer(re.escape(version.encode()),plane))
 if baseline_date is not None:
  date=(69 if owner=='post_ui_begin' else 80+69)*2
  assert raw[date:date+16:2]==m.image.read_bytes()[-11:-3]
  raw[date:date+16:2]=baseline_date
  if owner=='post_ui_begin':normalize_post(raw,m.port,phase)
 for match in matches:
  start,end=match.span()
  if baseline_version is None:raw[start*2:end*2:2]=b'*'*(end-start)
  else:
   assert raw[start*2+1:end*2:2]==b'\x1B'*(end-start)
   width=max(end-start,len(baseline_version))
   raw[start*2:(start+width)*2]=b'*\x1B'*len(baseline_version)+b' \x1F'*(width-len(baseline_version))
 # setup_draw has caller-owned scratch outputs; all segment/stack outputs stay exact.
 preserved=REGS if owner=='post_ui_begin' else REGS[7:13]
 return {'VRAM_sha256':hashlib.sha256(raw).hexdigest(),'version_occurrences':len(matches),
  'return_state':{r:m.cpu.reg_read(getattr(x,'UC_X86_REG_'+r)) for r in preserved}}

def normalize_post(raw,port,phase):
 # Verify the intentional new cells, then restore only those cells for the historical hash.
 blank=b' \x07'*80
 features=b'APM 1.2' if port=='mp386' else b'PnP 1.0  APM 1.2'
 start=4000-(len(features)+1)*2
 assert raw[start:-2:2]==features
 raw[start:-2]=b' \x07'*len(features)
 if phase==0:
  row=(5 if port=='presario-800' else 6)*160
  assert raw[row:row+160:2].split()==[b'Memory',b'1024',b'KB']
  raw[row:row+160]=blank
 elif port=='m919':
  assert raw[4*160:5*160:2].split()==[b'L2',b'cache',b'Enabled']
  raw[4*160:5*160]=blank
 if phase==5:
  for row in range(11,15 if port=='m919' else 13):
   start=row*160
   assert raw[start:start+160]==blank
   raw[start+6:start+42]=b''.join(bytes((char,0x0B)) for char in b'Primary IDE Master')
   raw[start+48:start+64:2]=b'Disabled'
  assert raw[15*160:16*160]==blank
  raw[15*160:18*160]=raw[16*160:19*160]
  raw[18*160:19*160]=blank

def measurement(port):
 baseline=json.loads(FIXTURE.read_text())['ports'][port]
 result=pnp.image_contract(port,OUTPUT)
 result['baseline_free_system_bytes']=baseline['free_system_bytes']
 result['net_F0_gain']=result['free_system_bytes']-baseline['free_system_bytes']
 from shared.tools.rom_footprint import report
 image=ROOT/port/OUTPUT/('baios-presario800-vga60.bin' if port=='presario-800' else f'baios-{port}.bin')
 listing=image.with_name('baios-presario800-system.lst') if port=='presario-800' else image.with_suffix('.lst')
 if port=='m919':
  module=json.loads((ROOT/port/'port.json').read_text())['rom']['post_module']
  options=dict(module_offset=module['offset'],bank_bytes=module['bank_bytes'],transport=module['transport'])
 else:
  options=({'module_offset':0xC000,'bank_bytes':0x4000,'transport':'top-alias'} if port=='presario-800' else
           {'module_offset':0x8000,'bank_bytes':0x8000,'transport':'window-copy'} if port=='pb430' else {})
 result['footprint']=report(image,listing,**options)
 module=result['footprint']['private_module']
 result['temporary_module_RAM_bytes']=module['charged_temporary_RAM_bytes']
 result['private_module_growth']=module['raw_bytes']-baseline['private_module_bytes']
 assert result['free_system_bytes']==result['footprint']['resident']['free_bytes']
 result['historical_baseline_image_identical']=result['sha256']==baseline['image_sha256']
 if port=='mp386':
  assert module['transport']=='inline' and module['raw_bytes']==module['bank_bytes']==module['charged_temporary_RAM_bytes']==0
  assert all(marker not in image.read_bytes() for marker in (b'$PnP',b'BAIPNP2\0',b'BAIZX02\0')),'Excluded port exposed a PnP/module composition'
 return result

def private_api(m):
 # Actual returned BX/SI and both CF outcomes through the same generated frame
 # used by every export. Full caller state includes nonzero upper registers.
 if m.port=='mp386':return {'inline_composition':True}
 sentinels={name:(i+1)*0x1020304 for i,name in enumerate(('EAX','EBX','ECX','EDX','ESI','EDI','EBP'))}
 m.call('settings_load');m.call('setup_defaults');m.draft();m.put('U_IDE_DEVICE',[0]);m.put('U_PAGE',[1])
 record=bytearray(m.get('U_IDE',51 if m.port=='m919' else 25));record[0]=1;record[1]=48;m.put('U_IDE',record)
 for kind,valid in ((48,True),(0,False)):
  record[1]=kind;m.put('U_IDE',record)
  values=sentinels|{'ECX':0x12340002}
  assert m.call('setup_field_available',**values)==valid
  assert all(m.cpu.reg_read(getattr(x,'UC_X86_REG_'+name))==value for name,value in values.items())
 m.call('ide_ui_record',EBX=0xABCD6789,ESI=0x76543210)
 target=m.state['U_IDE']+1
 assert m.cpu.reg_read(x.UC_X86_REG_EBX)==0xABCD0000|target
 assert m.cpu.reg_read(x.UC_X86_REG_ESI)==0x76540000|target
 # Enumerate only actually emitted facades, not labels in inactive NASM arms.
 from capstone import Cs,CS_ARCH_X86,CS_MODE_16
 decoder=Cs(CS_ARCH_X86,CS_MODE_16);inventory=[];template=None
 segment=int.from_bytes(m.cpu.mem_read(m.base+0x33A,2),'little')
 for name in re.findall(r'^post_ui_export (\w+)',(ROOT/'shared/src/firmware/post-ui-api.inc').read_text(),re.M):
  row=m.listing.row(name);address=None
  for line in m.listing.lines[row+1:]:
   if re.search(r'(?<![\w.])\w+:\s*$',line) or re.search(r'(?<![\w.])\w+\s+(?:db|dw|dd|equ)\b',line):break
   found=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line)
   if found:address=int(found[1],16);break
  if address is None:continue
  facade=bytes(m.cpu.mem_read(0xF0000+address,8));assert facade[:3]==bytes.fromhex('9C53BB'),(name,facade.hex())
  entry=int.from_bytes(facade[3:5],'little');body=bytearray();call=None
  for instruction in decoder.disasm(bytes(m.cpu.mem_read((segment<<4)+entry,64)),entry):
   body.extend(instruction.bytes)
   if instruction.mnemonic=='call':call=instruction
   if instruction.mnemonic=='ret':break
  assert call and body[-1]==0xC3
  displacement=int.from_bytes(call.bytes[1:3],'little',signed=True)
  assert (call.address+3+displacement)&65535==m.listing.symbol('post_ui_'+name),(name,hex(call.address))
  start=call.address-entry+1;body[start:start+2]=b'\0\0'
  if template is None:template=bytes(body)
  assert body==template,(name,body.hex(),template.hex())
  inventory.append(name)
 assert len(inventory)>60 and len(set(inventory))==len(inventory)
 return {'actual_BX_SI_returned':target,'actual_CF_available_unavailable':True,
  'all_emitted_export_frames_and_actual_targets':inventory,'shared_frame_bytes':len(template)}


def private_ui(port):
 oracle=json.loads(FIXTURE.read_text())['ports'][port]
 m=fixture_model(port)
 if port=='presario-800':
  version=re.search(r"%define BIOS_VERSION '([^']+)'",(ROOT/port/'src/bios.asm').read_text())[1]
 else:version=json.loads((ROOT/port/'port.json').read_text())['identity']['version']
 historical=json.loads((ROOT/'shared/tests/fixtures/ui-text-p0.json').read_text())['ports'][port]
 baseline_date=bytes.fromhex(historical['post_screens']['post_ui_begin'])[69*2:77*2:2]
 entered=[];encoded=[]
 if port!='mp386':
  segment=int.from_bytes(m.cpu.mem_read(m.base+0x33A,2),'little');assert segment and segment!=0xF000
  for name in ('setup_draw','post_ui_begin'):
   at=(segment<<4)+m.listing.symbol('post_ui_'+name)
   def actual(cpu,address,size,unused,name=name):
    assert cpu.reg_read(x.UC_X86_REG_CS)==segment
    entered.append(name)
   m.cpu.hook_add(UC_HOOK_CODE,actual,None,at,at)
 text_at=0xF0000+m.listing.symbol('setup_text')
 def renderer(cpu,address,size,unused):
  ds=cpu.reg_read(x.UC_X86_REG_DS);si=cpu.reg_read(x.UC_X86_REG_SI)
  if ds==0xF000 and cpu.mem_read((ds<<4)+si,1)==b'\x01':encoded.append(si)
 m.cpu.hook_add(UC_HOOK_CODE,renderer,None,text_at,text_at)
 compared=[]
 for owner,phase,page in profiles(port):
  key=f'{owner}:{phase}:{page}';actual=oracle_profile(m,owner,phase,page,version,oracle['version'],baseline_date)
  assert actual==oracle['profiles'][key],(port,key,actual,oracle['profiles'][key])
  compared.append(key)
 assert encoded
 if port!='mp386':assert set(entered)=={'setup_draw','post_ui_begin'}
 # Real resident renderer must continue treating foreign leading01/control/CP437 literally.
 literal=b'\x01Raw\x02\x80\xDB';m.cpu.mem_write(0x20100,literal+b'\0')
 m.call('setup_text',DS=0x2000,SI=0x100,ES=0xB800,DI=0xF00,BX=0x0700)
 assert bytes(m.cpu.mem_read(0xB8F00,len(literal)*2))[::2]==literal
 disk_context={}
 if port in ('pb430','presario-800'):
  m.put('P_PHASE',[4])
  slave=(m.base>>4)+0x20
  selector=m.state['STATE_BASE']+int(re.search(r'^%define S_ATA_DEVICE\s+STATE_BASE\s*\+\s*(\d+)',
   (ROOT/'shared/src/pc/state.inc').read_text(),re.M)[1])
  m.cpu.mem_write((slave<<4)+selector,b'\x10')
  for field in ('C_HDD','S_CONTROLLER'):
   m.cpu.mem_write((slave<<4)+m.state[field],b'\x01')
  m.cpu.mem_write(0xB8000+12*160,b'\x20\x07'*80)
  m.call('post_ui_disk',FS=slave,DS=0x3456,ES=0x4567)
  row=bytes(m.cpu.mem_read(0xB8000+12*160,160))[::2]
  assert row[3:20]==b'Primary IDE Slave',(port,row)
  assert m.cpu.reg_read(x.UC_X86_REG_FS)==slave
  disk_context={'selected_slave_FS_preserved':slave,'actual_slave_row':row.decode('cp437')}
 return {'baseline_exact_VRAM_and_original_return_state':compared,'private_CS_entries':len(entered),
  'selected_disk_context':disk_context,
  'real_encoded_F000_renderer_calls':len(encoded),'foreign_literal_control_CP437':True,'export_ABI':private_api(m)}

def startup(port,external_video=False,phases=(False,True)):
 if port=='mp386':
  return {'inline_image_unchanged':measurement(port),'ordinary_no_PnP':pnp.mp_negative(OUTPUT)}
 from shared.tools.isa_pnp_proof import Card,serial
 resources=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\x01\x01\x47'+struct.pack('<BHHBB',1,0x500,0x500,0,8)+b'\x79\0'
 cards=[Card(serial(b'\x41\xD0\xFF\xFF',1),resources)]
 def seed(m):m.put('U_POST_DELAY',[0])
 rows=[];private=[];hooked=set()
 name='baios-presario800-system.rom' if port=='presario-800' else f'baios-{port}.bin'
 source=settings.Listing(ROOT/port/OUTPUT/Path(name).with_suffix('.lst'))
 core_offsets={owner:source.symbol('post_ui_'+owner) for owner in ('post_ui_begin','post_header','post_debug_summary')}
 if port=='presario-800':
  video_at=0xF0000+next(int(m[1],16) for line in source.lines if 'call pnp_rom_enter' in line and (m:=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line)))
 else:video_at=0xF0000+source.symbol('initialize_video')
 def observe(model,cpu,address,listing,bus):
  if address!=video_at:return
  base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
  segment=int.from_bytes(cpu.mem_read(base+0x33A,2),'little')
  if not segment or (id(cpu),segment) in hooked:return
  hooked.add((id(cpu),segment))
  for owner in ('post_ui_begin','post_header','post_debug_summary'):
   target=(segment<<4)+core_offsets[owner]
   def entered(uc,ip,size,unused,owner=owner,segment=segment):
    assert uc.reg_read(x.UC_X86_REG_CS)==segment
    current=int.from_bytes(uc.mem_read(0x40E,2),'little')<<4
    assert int.from_bytes(uc.mem_read(current+0x33A,2),'little')==segment
    private.append(owner)
   cpu.hook_add(UC_HOOK_CODE,entered,None,target,target)
 def completed(port,model,cpu,listing,bus):
  base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
  assert cpu.mem_read(base+0x338,4)==bytes(4)
  assert all(c.registers[0][0x30] for c in cards)
  result=pnp.runtime_boot_current(port,model,cpu,listing,bus,1)
  rows.append(result);return result
 image=pnp.runtime_provider(port,0,'boot',witness_port=0xE9)
 result=pnp.runtime_startup_snapshot(port,phases=phases,cards=cards,seed_edit=seed,observer=observe,external_video=external_video,
  rom_images=((0xC800,image),),boot_order=(4,0,0,0),post_action=completed,expect_active=True,
  snapshot_name='footprint-startup')
 evidence=result.startup_evidence
 assert len(rows)==len(phases) and len(evidence['finish_observations'])==len(phases)
 assert {'post_ui_begin','post_header','post_debug_summary'}<=set(private),private
 assert all(row['runtime_published'] and row['released_control'] for row in evidence['finish_observations'])
 result={'actual_cold_warm_to_loader':rows,'actual_private_body_entries':private,'startup':evidence}
 if port=='pb430' and not external_video:result['external_video_cold_to_loader']=startup(port,True,(False,))
 return result

def setup_continuation(port,save_gate=None,priority_order=None,warm_rebuilds=0):
 if port=='mp386':
  # The common inline composition is byte-identical. The ordinary owner still
  # executes its real Setup Save/reload contract in the established exclusion check.
  return pnp.mp_negative(OUTPUT)
 if save_gate is None:
  result={gate:setup_continuation(port,gate,warm_rebuilds=2 if gate=='early' else 0) for gate in ('early','final')}
  return result
 name='baios-presario800-system.rom' if port=='presario-800' else f'baios-{port}.bin'
 listing=settings.Listing(ROOT/port/OUTPUT/Path(name).with_suffix('.lst'));listing.symbol=cache(listing.symbol)
 points={label:0xF0000+listing.symbol(label) for label in ('pnp_publish','post_early_setup','setup_post_gate','setup_main','int16','warm_reset','settings_save','init_fpu')}
 state=settings.constants(ROOT/'shared/src/pc/state.inc');state.update(settings.constants(ROOT/'shared/src/setup/layout.inc'))
 input_offset=listing.symbol('.input','post_ui_setup_main')
 phase=[0];context=[None];entered=[];gates=[];resets=[];saved=[];keys=[];hooked=set();boot=[]
 def observe(model,cpu,address,source,bus):
  if address!=points['pnp_publish'] or id(cpu) in hooked:return
  hooked.add(id(cpu));bus.continue_setup_reset=True
  if not hasattr(bus,'setup_reset_pulses'):bus.setup_reset_pulses=[]
  def at(uc,address,size,unused):
   base=int.from_bytes(uc.mem_read(0x40E,2),'little')<<4
   if address==points['pnp_publish']:
    if not any(uc.mem_read(base+0x330,4)):phase[0]+=1
    print(port,save_gate,'publication phase',phase[0],flush=True)
   elif address in (points['post_early_setup'],points['setup_post_gate'],points['init_fpu']):
    gate='early' if address==points['post_early_setup'] else 'final'
    if address!=points['init_fpu']:context[0]=gate
    # Both gates in the first POST are exercised unless the earlier Save
    # necessarily resets first. The following POST exercises the other Discard.
    wanted=(phase[0]==1 and (gate==save_gate or save_gate=='final')) or (phase[0]==2 and save_gate=='early' and gate=='final')
    if wanted and (phase[0],gate) not in gates and address!=points['setup_post_gate']:
     queue=model.queue if port=='m919' else model.pending
     queue.extend((0xE0,0x53));gates.append((phase[0],gate))
   elif address==points['setup_main']:
    action='save' if phase[0]==1 and context[0]==save_gate else 'discard'
    entered.append((phase[0],context[0],action));print(port,save_gate,'actual Setup',entered[-1],flush=True)
    # Change a real field, open Defaults then cancel it, and complete the
    # requested exit through the original confirmation/input owners.
    script=[0x3E,0x43,1]+([0x44,28] if action=='save' else [1,28])
    if port=='m919':keys[:]=script
    else:model.script=script
    if priority_order is not None and action=='save':
     segment=int.from_bytes(uc.mem_read(base+0x33A,2),'little')
     edited=[]
     def requested(cpu,address,size,unused):
      if edited:return
      for field,value in zip(('U_BOOT','U_BOOT_SECOND','U_BOOT_THIRD','U_BOOT_FOURTH'),priority_order):
       cpu.mem_write(base+state[field],bytes((value,)))
       if port=='m919':model.write(base+state[field],1,value)
      edited.append(True)
     target=(segment<<4)+input_offset
     uc.hook_add(UC_HOOK_CODE,requested,None,target,target)
   elif address==points['int16'] and port=='m919' and uc.reg_read(x.UC_X86_REG_AH)==1:
    if keys and not model.queue:model.queue.append(keys.pop(0))
   elif address==points['settings_save'] and entered:
    saved.append((phase[0],context[0]))
   elif address==points['warm_reset']:resets.append((phase[0],context[0]))
  for target in points.values():cpu.hook_add(UC_HOOK_CODE,at,None,target,target)

 def completed(port,model,cpu,listing,bus):
  assert entered and saved and resets and resets[0]==(1,save_gate),(entered,saved,resets,gates,phase)
  assert all(not item for item in (keys,getattr(model,'script',[]))),('Unconsumed physical keys',keys,getattr(model,'script',[]))
  base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
  assert cpu.mem_read(base+0x338,4)==bytes(4)
  first=priority_order is not None and priority_order[0]==2
  if priority_order is not None:
   assert tuple(cpu.mem_read(base+state[field],1)[0] for field in ('C_BOOT','C_BOOT_SECOND','C_BOOT_THIRD','C_BOOT_FOURTH'))==priority_order
  connected=int.from_bytes(cpu.mem_read(0x902,2),'little')
  result=pnp.runtime_boot_current(port,model,cpu,listing,bus,0x80 if first else 1,0x80 if first else 0x81)
  assert int.from_bytes(cpu.mem_read(0x902,2),'little')-connected==int(not first),'Native priority must not connect an IPL provider'
  boot.append(result);return result
 def seed(m):m.put('U_POST_DELAY',[0])
 image=pnp.runtime_provider(port,0,'boot',witness_port=0xE9)
 native=pnp.runtime_assemble(port,'footprint-native-priority',"""bits 16
org 7C00h
xor ax,ax
mov ds,ax
mov word [6F0h],80h
mov al,80h
out 0E9h,al
hlt
times 510-($-$$) db 0
dw 0AA55h
""") if priority_order is not None else None
 result=pnp.runtime_startup_snapshot(port,phases=(False,)+(True,)*warm_rebuilds,seed_edit=seed,observer=observe,
  rom_images=((0xC800,image),),boot_order=(4,0,0,0),post_action=completed,
  snapshot_name='footprint-setup-'+save_gate+('-priority-'+str(priority_order[0]) if priority_order else ''),native_sector=native)
 assert {item[1] for item in entered}=={'early','final'},entered
 assert len(saved)==1 and len(boot)==1+warm_rebuilds,(saved,resets,boot)
 budgets=result.startup_evidence['actual_before_module_available_KiB']
 assert len(set(budgets))==1,('Warm rebuild leaked the private charge',budgets)
 assert any(item[2]=='discard' for item in entered)
 evidence={'actual_setup_entries':entered,'physical_Delete_gates':gates,'actual_whole_Save':saved,'saved_priority':priority_order,
  'actual_resident_reset':resets,'following_complete_POST_to_loader':boot,'startup':result.startup_evidence}
 (ROOT/port/OUTPUT/('footprint-setup-'+save_gate+'-result.json')).write_text(json.dumps(evidence,indent=2)+'\n')
 return evidence

def lifetime(port):
 if port=='mp386':return {'inline_no_private_module':measurement(port)['footprint']['private_module']['transport']=='inline'}
 rows=[]
 for reserve in (False,True):
  listing=settings.Listing(ROOT/port/OUTPUT/('baios-presario800-system.lst' if port=='presario-800' else f'baios-{port}.lst'))
  points={n:0xF0000+listing.symbol(n) for n in ('pnp_publish','post_early_setup','setup_main','int16')}
  end=listing.row('.defaults',listing.row('post_ui_setup_main'))
  discard_return=next(int(match[1],16) for line in reversed(listing.lines[:end]) if 'ret' in line and (match:=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+C3\s',line)))
  keys=[];installed=set();entered=[];discarded=[];ui_writes=[];active=[False];index=[0];requested=[False]
  def observe(model,cpu,address,source,bus):
   if address!=points['pnp_publish'] or id(cpu) in installed:return
   installed.add(id(cpu));output=bus.output
   def watched(p,size,value):
    if p==0x70:index[0]=value&127
    if active[0] and p==0x71:ui_writes.append((index[0],value))
    return output(p,size,value)
   bus.output=watched
   def event(uc,address,size,unused):
    base=int.from_bytes(uc.mem_read(0x40E,2),'little')<<4
    if address==points['post_early_setup'] and not requested[0]:
     (model.queue if port=='m919' else model.pending).extend((0xE0,0x53));requested[0]=True
    elif address==points['setup_main']:
     assert not entered;entered.append(address);active[0]=True
     segment=int.from_bytes(uc.mem_read(base+0x33A,2),'little')
     length=int.from_bytes(uc.mem_read((segment<<4)+(0x1608 if port=='m919' else 8),2),'little')
     start=(segment<<4)+(0x1600 if port=='m919' else 0)
     before=bytes(uc.mem_read(start,length))
     def returned(cpu,address,size,unused):
      assert bytes(cpu.mem_read(start,length))==before and not ui_writes
      assert cpu.mem_read(base+settings.constants(ROOT/'shared/src/pc/state.inc')['C_PNP']+14,1)==b'\x01'
      active[0]=False;discarded.append(address)
     target=(segment<<4)+discard_return
     uc.hook_add(UC_HOOK_CODE,returned,None,target,target)
     if port=='m919':keys[:]=[0x3E,1,28]
     else:model.script=[0x3E,1,28]
    elif address==points['int16'] and port=='m919' and uc.reg_read(x.UC_X86_REG_AH)==1:
     if keys and not model.queue:model.queue.append(keys.pop(0))
   for target in points.values():cpu.hook_add(UC_HOOK_CODE,event,None,target,target)
  body=pnp.runtime_assemble(port,'footprint-returning-reservation-'+str(reserve),"""bits 16
org 100h
pushad
push ds
push es
xor ax,ax
mov ds,ax
mov bx,[413h]
mov [6D0h],bx
mov dx,bx
"""+('sub bx,8\n' if reserve else '')+"""mov [6D2h],bx
mov [413h],bx
sub dx,bx
jz done
mov ax,bx
shl ax,6
mov es,ax
xor di,di
block:
mov ax,6D6Dh
mov cx,512
rep stosw
mov ax,es
add ax,40h
mov es,ax
xor di,di
dec dx
jnz block
done:
pop es
pop ds
popad
xor ax,ax
retf
""")
  image=bytearray(pnp.runtime_rom(0,status=0));image[0x100:0x100+len(body)]=body;image[-1]=0;image[-1]=(-sum(image))&255
  def seed(m):
   m.put('U_POST_DELAY',[0]);policy=bytearray(15);policy[3:7]=struct.pack('<HH',0x350,8);policy[14]=1;m.put('U_PNP',policy)
  def complete(port,model,cpu,listing,bus):
   assert entered and len(discarded)==1 and not ui_writes and not keys
   high,low=struct.unpack('<HH',cpu.mem_read(0x6D0,4));assert high-low==(8 if reserve else 0)
   if reserve:assert cpu.mem_read(low*1024,(high-low)*1024)==b'\x6D'*((high-low)*1024)
   base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
   assert int.from_bytes(cpu.mem_read(0x413,2),'little')==base>>10
   if reserve:assert base+cpu.mem_read(base,1)[0]*1024<=low*1024
   assert cpu.mem_read(base+0x338,4)==bytes(4)
   result=pnp.runtime_boot_current(port,model,cpu,listing,bus,2)
   if reserve:assert cpu.mem_read(low*1024,(high-low)*1024)==b'\x6D'*((high-low)*1024)
   return {'external_owner_KiB':[low,high],'actual_boot':result,'Discard_no_CMOS_writes':True}
  result=pnp.runtime_startup_snapshot(port,observer=observe,seed_edit=seed,
   rom_images=((0xC800,bytes(image)),(0xC900,pnp.runtime_provider(port,1,'boot',witness_port=0xE9))),
   boot_order=(4,0,0,0),post_action=complete,snapshot_name='footprint-lifetime-'+str(reserve))
  assert not result.startup_evidence['actual_incomplete_notice_entries']
  rows.append({'returning_ROM_reserves_extra_memory':reserve,'startup':result.startup_evidence})
 return rows


def popups(port):
 if port=='mp386':return {'inline_no_private_module':measurement(port)['footprint']['private_module']['transport']=='inline'}
 cases=[('short',1,6 if port=='presario-800' else 0)]
 if port=='presario-800':cases.append(('paged',4,8))
 rows=[]
 for kind,screen,field in cases:
  m=fixture_model(port);m.call('settings_load');m.call('setup_defaults');m.draft()
  if port=='presario-800':
   chip=bytearray(m.get('U_CHIP',24));chip[10]=(chip[10]&63)|128;m.put('U_CHIP',chip)
  assert m.call('settings_save');m.call('settings_load');m.draft()
  before=m.snapshot();chip=m.get('C_CHIP',24);m.writes.clear()
  m.put('U_PAGE',[5]);m.put('U_CHIP_SCREEN',[screen]);m.put('U_FIELD',[field])
  m.call('chipset_ui_descriptor');si=m.cpu.reg_read(x.UC_X86_REG_SI)
  label,offset,shift,mask,count,values,h1,h2,reserved=struct.unpack('<HBBBHHHHB',m.cpu.mem_read(0xF0000+si,14))
  assert (count<=10)==(kind=='short') and m.call('chipset_ui_editable',CX=field)
  old_draft=m.get('U_CHIP',24)
  m.call('setup_change',AX=0x4D00) # This original editor has no CF success contract.
  changed=bytearray(old_draft);selected=((old_draft[offset]>>shift)&mask)+1;selected%=count
  changed[offset]=(old_draft[offset]&~(mask<<shift))|(selected<<shift)
  assert m.get('U_CHIP',24)==changed,'Moved Left/Right must reach the resident chipset change owner'
  m.put('U_CHIP',old_draft)
  segment=int.from_bytes(m.cpu.mem_read(m.base+0x33A,2),'little');entries=[]
  target=(segment<<4)+m.listing.symbol('.draw' if kind=='short' else '.paged','post_ui_setup_choices' if kind=='short' else 'post_ui_chipset_ui_choices')
  hook=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,z,v:entries.append(a),None,target,target)
  down,enter,escape=0x5000,13,27
  navigation=[down]*4+[enter]+[down]*(screen-1)+[enter]+[down]*field
  # Help returns into the actual popup. Cancel drops a pending change; reopening
  # and applying changes exactly the descriptor's existing draft field.
  m.keys=navigation+[enter,0x3B00,escape,down,escape,enter,down,enter]+[escape]*3+[enter]
  sentinels={name:(i+1)*0x1020304 for i,name in enumerate(('EAX','EBX','ECX','EDX','ESI','EDI','EBP'))}
  try:m.call('setup_main',**sentinels,GS=0x5678)
  finally:m.cpu.hook_del(hook)
  assert not m.keys and entries and m.snapshot()==before and not m.writes
  assert all(m.cpu.reg_read(getattr(x,'UC_X86_REG_'+name))==value for name,value in sentinels.items())
  assert m.cpu.reg_read(x.UC_X86_REG_SP)==0x7002 and m.cpu.reg_read(x.UC_X86_REG_GS)==0x5678
  expected=bytearray(chip);value=((chip[offset]>>shift)&mask)+1;value%=count
  expected[offset]=(chip[offset]&~(mask<<shift))|(value<<shift)
  assert m.get('U_CHIP',24)==expected,(port,kind,m.get('U_CHIP',24).hex(),expected.hex())
  title=b'CAS Width' if port=='presario-800' and kind=='short' else b'SELECT VALUE'
  assert any(title in page for page in m.screen)
  rows.append({'path':kind,'choices':count,'actual_private_popup_entries':len(entries),
   'Help_redraw_Cancel_Apply_exact_draft_delta':True,'caller_registers_segments_stack':True,
   'no_persistent_writes':True,'saved_hardware_policy_unchanged':True})
 return rows


def capacity(port,baseline=None):
 if port=='mp386':return {'inline_image_unchanged':measurement(port)}
 def seed(m):m.put('U_POST_DELAY',[0])
 if baseline is None:baseline=pnp.runtime_startup_snapshot(port,seed_edit=seed,snapshot_name='footprint-capacity-baseline')
 result=pnp.runtime_capacity(port,baseline)
 result['actual_module_accounting']=measurement(port)['footprint']['private_module']
 return result


def native_codec(code,stream,length,expected=None,input_offset=0x100):
 from unicorn import Uc,UC_ARCH_X86,UC_MODE_16,UC_HOOK_MEM_WRITE
 cpu=Uc(UC_ARCH_X86,UC_MODE_16);cpu.mem_map(0,0x100000)
 cpu.mem_write(0xF0000,code);cpu.mem_write(0x20000+input_offset,stream)
 cpu.mem_write(0x50000-16,b'B'*16+b'\xCC'*length+b'A'*16)
 cpu.mem_write(0x7000,b'\xFF\xFF');stack=[]
 def write(uc,access,address,size,value,unused):
  assert address+size<=0xF0000 or address>=0x100000,'Codec wrote ROM'
  if 0x6000<=address<0x7000:stack.append(address)
  elif not (0x50000<=address and address+size<=0x50000+length):raise AssertionError(('Codec write outside destination',address,size))
 hook=cpu.hook_add(UC_HOOK_MEM_WRITE,write)
 for name,value in dict(CS=0xF000,DS=0x2000,SI=input_offset,BX=len(stream),ES=0x5000,DI=0,CX=length,SS=0,SP=0x7000,BP=0xABCD).items():cpu.reg_write(getattr(x,'UC_X86_REG_'+name),value)
 try:cpu.emu_start(0xF0000,0xFFFFF,count=10000000)
 finally:cpu.hook_del(hook)
 assert cpu.reg_read(x.UC_X86_REG_IP)==0xFFFF
 assert all(cpu.reg_read(getattr(x,'UC_X86_REG_'+name))==value for name,value in dict(BP=0xABCD,DS=0x2000,ES=0x5000,SP=0x7002).items())
 assert cpu.mem_read(0x4FFF0,16)==b'B'*16 and cpu.mem_read(0x50000+length,16)==b'A'*16
 good=not cpu.reg_read(x.UC_X86_REG_EFLAGS)&1
 if expected is not None:assert good and bytes(cpu.mem_read(0x50000,length))==expected
 assert 0x7000-min(stack)<=12
 return {'success':good,'decoder_bytes':len(code),'internal_stack_bytes':0x7000-min(stack)}


def zx0_wire(literal=b'A',high=256,low=None):
 """Independent bit serializer for the documented v2 Elias/offset grammar."""
 data=bytearray();mask=[0];control=[0]
 def bit(value):
  if not mask[0]:control[0]=len(data);data.append(0);mask[0]=128
  if value:data[control[0]]|=mask[0]
  mask[0]>>=1
 def elias(value,inverted=False):
  for digit in bin(value)[3:]:bit(0);bit(int(digit)^int(inverted))
  bit(1)
 elias(len(literal));data.extend(literal);bit(1);elias(high,True)
 if low is not None:data.append(low)
 return bytes(data)


def bank_geometry(work):
 from shared.tools import post_module as codec
 from unittest.mock import patch
 raw=bytearray(0x4000);raw[:12]=codec.RAW+struct.pack('<HH',len(raw),12);raw[12:15]=bytes.fromhex('FFD3CB')
 bank,info=codec.serialize(bytes(raw),work,0x8000)
 assert len(bank)==0x8000 and info['storage']=='raw' and codec.inspect_bank(bank)[0]==raw
 missing=work/'absent-tools'
 with patch.object(codec,'ROOT',missing):
  try:codec.encode(bytes(raw),work)
  except RuntimeError as error:assert 'python -B tools/install-zx0.py' in str(error)
  else:raise AssertionError('Missing required encoder was silently accepted')
 return {'caller_supplied_32KiB_bank_raw_16KiB_module':True,'missing_encoder_actionable_without_download':True}


def roundtrip(port):
 if port=='mp386':return {'inline_no_private_module':measurement(port)['footprint']['private_module']['transport']=='inline'}
 if port!='presario-800':
  m=fixture_model(port);physical=m.image.read_bytes();offset=0x1600 if port=='m919' else 0x8000
  length=int.from_bytes(physical[offset+8:offset+10],'little')
  segment=int.from_bytes(m.cpu.mem_read(m.base+0x33A,2),'little')
  target=(segment<<4)+(offset if port=='m919' else 0)
  assert bytes(m.cpu.mem_read(target,length))==physical[offset:offset+length]
  return {'raw_transport_every_byte_equal':length,'export_ABI':private_api(m)}
 from shared.tools import post_module as codec
 work=ROOT/port/OUTPUT/'codec';work.mkdir(parents=True,exist_ok=True)
 geometry=bank_geometry(work)
 asm=work/'native.asm';binary=work/'native.bin'
 asm.write_text('bits 16\norg 0\n%include "firmware/zx0.inc"\n')
 import shutil
 nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
 subprocess.run([nasm,'-I',str(ROOT/'shared/src')+'/','-f','bin','-o',str(binary),str(asm)],check=True)
 code=binary.read_bytes()
 rows=[]
 literal=zx0_wire();rows.append(native_codec(code,literal,1,b'A'))
 rows.append(native_codec(code,literal,1,b'A',0x10000-len(literal)))
 for raw in (b'Z'*200,bytes(range(256))*80,b'abcde'*9000,bytes((i*37+i//3)&255 for i in range(32000))):
  stream=codec.encode(raw,work);assert codec.decode_zx0(stream,len(raw))==raw
  rows.append(native_codec(code,stream,len(raw),raw))
 invalid=[]
 stream=codec.encode(b'Z'*200,work)
 for name,data,length,offset in [('truncated',stream[:-1],200,0x100),('trailing',stream+b'X',200,0x100),
  ('output-short',stream,199,0x100),('output-long',stream,201,0x100),('Elias-overflow',bytes(20),100,0x100),
  ('source-wrap',stream,200,0xFFFE),('lookback-before-start',zx0_wire(high=2,low=255),3,0x100),
  ('offset-high257',zx0_wire(high=257,low=255),3,0x100)]:
  result=native_codec(code,data,length,input_offset=offset);assert not result['success'],name;invalid.append(name)
 if port=='presario-800':
  bank=(ROOT/port/OUTPUT/'baios-presario800-vga60.bin').read_bytes()[0xC000:0x10000]
  raw,info=codec.inspect_bank(bank)
  if info['storage']=='zx0-v2':
   stream=bank[codec.HEADER:info['stored_bytes']]
   rows.append(native_codec(code,stream,len(raw),raw))
  m=fixture_model(port);segment=int.from_bytes(m.cpu.mem_read(m.base+0x33A,2),'little')
  assert bytes(m.cpu.mem_read(segment<<4,len(raw)))==raw
  thresholds=loader_thresholds()
 else:thresholds=[]
 return {'native_vectors':rows,'bounded_rejections':invalid,'actual_loader_thresholds':thresholds,'bank_geometry':geometry,'actual_storage':info['storage'],'actual_raw_bytes':len(raw)}


def loader_thresholds():
 from shared.tools import post_module as codec
 import shutil
 nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
 rows=[]
 for length,late in ((0x3FFE,0x71),(0x4000,0x72),(0x4000,0x73)):
  m=fixture_model('presario-800');m.call('pnp_journal_release')
  raw=bytearray(length);raw[:12]=b'BAIPNP2\0'+struct.pack('<HH',length,12)
  raw[12:19]=bytes.fromhex('FFD3CBB8FECAF9');raw[19]=0xC3;raw[-1]=late
  work=ROOT/'presario-800'/OUTPUT/'codec';bank,info=codec.serialize(bytes(raw),work,0x4000)
  assert info['storage']==('raw' if length==0x3FFE else 'zx0-v2')
  # Compile the unchanged actual loader against a controlled raw-module extent.
  # AH87, memory accounting, reset state and all hardware use current firmware.
  from shared.tools.rom_footprint import report
  physical=m.image.with_name('baios-presario800-vga60.bin')
  free=report(physical,m.image.with_suffix('.lst'))['resident']['free_intervals'][0]
  origin=free['offset'];source=work/'loader.asm';binary=work/'loader.bin'
  bindings={name:m.listing.symbol(name) for name in ('pnp_journal_allocate','pnp_journal_begin','pnp_journal_release','load_bios_state')}
  source.write_text('bits 16\norg '+str(origin)+'\n%define PNP_MODULE_POINTER 0x338\n'+
   ''.join(name+' equ '+str(value)+'\n' for name,value in bindings.items())+
   'pnp_module_start equ 0\npnp_module_end equ '+str(length)+'\npnp_module_entry equ 12\n'+
   '%macro presario_shared 1\n%include %1\n%endmacro\n%include "hardware/pnp-module.inc"\n')
  subprocess.run([nasm,'-I',str(ROOT/'presario-800/src')+'/','-I',str(ROOT/'shared/src')+'/',
   '-f','bin','-o',str(binary),str(source)],check=True)
  code=binary.read_bytes();assert len(code)<free['bytes']
  m.cpu.mem_write(0xF0000+origin,code);m.cpu.mem_write(0xFFFEC000,bank)
  # The first three declarations are callback bodies before the actual installer.
  entry=origin+12
  assert code[12:15]==bytes.fromhex('9CFA66'),code[:25].hex()
  symbol=m.listing.symbol;m.listing.symbol=lambda name,*scope:entry if name=='pnp_module_install' else symbol(name,*scope)
  try:assert m.call('pnp_module_install')
  finally:m.listing.symbol=symbol
  segment=int.from_bytes(m.cpu.mem_read(m.base+0x33A,2),'little')
  assert bytes(m.cpu.mem_read(segment<<4,length))==raw
  assert not m.call('pnp_post_invoke',BX=15) and m.cpu.reg_read(x.UC_X86_REG_AX)==0xCAFE
  assert not m.writes
  rows.append({'raw_bytes':length,'late_byte':late,'storage':info['storage'],'final_bank_sha256':info['bank_sha256'],
    'actual_AH87_and_loader_every_raw_byte_equal':True,'actual_dispatch_BX_CF':True})
 return rows


if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--port',choices=('all',)+PORTS,default='all');a.add_argument('--case',choices=('measurement','private-ui','startup','setup-continuation','roundtrip','capacity','popups','lifetime','all'),default='measurement');args=a.parse_args()
 ports=PORTS if args.port=='all' else (args.port,)
 if args.port=='all':
  for port in ports:subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--port',port,'--case',args.case],cwd=ROOT,check=True)
 else:
  prepare(args.port);cases=('measurement','private-ui','startup','setup-continuation','roundtrip','capacity','popups','lifetime') if args.case=='all' else (args.case,)
  results={case:globals()[case.replace('-','_')](args.port) for case in cases}
  target=ROOT/args.port/OUTPUT/('footprint-'+args.case+'.json');target.write_text(json.dumps(results,indent=2)+'\n');print(json.dumps({args.port:results},indent=2))
