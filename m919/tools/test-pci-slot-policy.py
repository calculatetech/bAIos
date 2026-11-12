"""Carry a native Setup pin choice through Save, a fresh load and routing."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('slot_pnp',ROOT/'shared/tests/test-pnp.py')
pnp=importlib.util.module_from_spec(spec);spec.loader.exec_module(pnp)
from shared.tools.isa_pnp_proof import Bus
from shared.tools.pci_proof import PCI,Endpoint


def run():
    board=pnp.settings.constants(ROOT/'m919/src/hardware/board-definition.inc')
    routes=((0,1,2,3),(3,0,1,2),(2,0,1,3))
    rows=[]
    for slot,choice in ((slot,choice) for slot in range(3) for choice in range(5)):
        bdf=0x60+slot*8
        def machine():
            devices={bdf:Endpoint(identity=0x920010B7,cls=0x020000,header=0x80,pin=4),
                     bdf+1:Endpoint(identity=0x920110B7,cls=0x020000,pin=2),
                     0x90:Endpoint(identity=0x88861060,cls=0x060100)}
            bus=Bus();bus.pci=PCI(devices);bus.pci_address=0;bus.ports={0x4D0:0,0x4D1:0}
            return pnp.isa_machine('m919',bus,'build'),devices
        m,_=machine();m.call('settings_load')
        before={name:m.get(name,size) for name,size in (('C_CHIP',24),('C_IDE',51),('C_PORTS',8),('C_PNP',15))}
        down,enter=0x5000,13
        keys=[down]*4+[9]+[down]*2+[enter]+[down]*slot+[enter]+[down]*choice+[enter,0x4400,ord('y')]
        m.ui(keys)
        expected_labels=[b'Auto',b'INTA',b'INTB',b'INTC',b'INTD']
        assert any([screen[row*80+26:row*80+36].strip() for row in range(10,15)]==expected_labels for screen in m.screen),'Pin popup order'
        fresh,devices=machine();fresh.cmos[:],fresh.nvram[:]=m.snapshot();fresh.call('settings_load')
        expected=bytearray(before['C_CHIP']);at=16+slot//2;shift=4*(slot&1)
        expected[at]=(expected[at]&~(15<<shift))|(choice<<shift)
        assert fresh.get('C_CHIP',24)==expected
        for name in ('C_IDE','C_PORTS','C_PNP'):assert fresh.get(name,len(before[name]))==before[name],name
        fresh.call('pnp_publish')
        fresh.cpu.mem_write(0x413,(fresh.base>>10).to_bytes(2,'little'))
        for owner in ('pnp_journal_begin','pnp_work_begin','pnp_seed'):assert fresh.call(owner),owner
        fresh.call('board_pci_runtime_policy')
        links=list(fresh.cpu.mem_read(fresh.base+board['HW_PCI_LINKS'],4))
        selected=routes[slot][(choice or 4)-1];other=routes[slot][1]
        assert {i for i,value in enumerate(links) if value!=255}=={selected,other},(slot,choice,links)
        assert devices[bdf].read(0x3C,1)==links[selected]
        assert devices[bdf+1].read(0x3C,1)==links[other]
        rows.append(dict(slot=slot+1,choice=expected_labels[choice].decode(),reported_pin='INTD',links=links,
                         native_keyboard_Save_reload_router=True,sorted_popup=True,other_function_and_settings_preserved=True))
    return rows


if __name__=='__main__':print(json.dumps(run(),indent=2))
