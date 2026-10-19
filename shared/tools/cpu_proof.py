"""Primary-table CPU identity and complete caller-state proof for composed ROMs."""
import struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INTR, UC_HOOK_INSN
from unicorn import x86_const as x
from shared.tools.ram_proof import Listing

# Expected identities are transcribed from AP485, AMD19720/20734/23913,
# Cyrix Detection Guide1997 and pinned Linux vendor tables, not firmware rows.
PRIMARY = {
    b'GenuineIntel':[(0x400,'486DX'),(0x410,'486DX'),(0x420,'486SX'),(0x430,'486DX2/487/OD'),
        (0x440,'486SL'),(0x450,'486SX2'),(0x470,'486DX2'),(0x480,'486DX4'),(0x490,'486DX4'),
        (0x1400,'486 OverDrive'),(0x1430,'486 OverDrive'),(0x1480,'486DX4 OD'),(0x1490,'486 OverDrive'),(0x510,'Pentium'),(0x520,'Pentium'),
        (0x1510,'Pentium OverDrive'),(0x1520,'Pentium OverDrive'),(0x1530,'Pentium P24T'),
        (0x540,'Pentium MMX'),(0x1540,'Pentium MMX OD')],
    b'AuthenticAMD':[(0x430,'AMD 486DX2'),(0x470,'AMD 486DX2'),(0x480,'AMD DX4/5x86'),
        (0x490,'AMD DX4/5x86'),(0x4E0,'AMD 5x86'),(0x4F0,'AMD 5x86'),
        (0x500,'AMD K5'),(0x510,'AMD K5'),(0x520,'AMD K5'),(0x530,'AMD K5'),
        (0x560,'AMD K6'),(0x570,'AMD K6'),(0x580,'AMD K6-2'),(0x590,'AMD K6-III'),(0x5D0,'AMD K6-2+/III+')],
    b'CyrixInstead':[(0x440,'Cyrix MediaGX'),(0x520,'Cyrix 6x86/L'),(0x540,'Cyrix GXm')],
    b'UMC UMC UMC\0':[(0x410,'UMC U5D'),(0x420,'UMC U5S')],
    b'CentaurHauls':[(0x540,'WinChip C6'),(0x580,'WinChip 2'),(0x586,'WinChip 2'),
        (0x587,'WinChip 2A'),(0x589,'WinChip 2A'),(0x58A,'WinChip 2B'),(0x58F,'WinChip 2B'),(0x590,'WinChip 3')],
    b'NexGenDriven':[(0x510,'NexGen Nx586')],
    b'RiseRiseRise':[(0x500,'Rise iDragon'),(0x520,'Rise iDragon'),(0x580,'Rise iDragon II'),(0x590,'Rise iDragon II')],
}


def check(rom,layout,state):
    raw=rom.read_bytes();listing=Listing(rom.with_suffix('.lst'));code=layout['code_segment']<<4
    decoder=Cs(CS_ARCH_X86,CS_MODE_16);instructions={};rows=[]
    owners={code+listing.symbol(name):name for name in
            ('post_ui_begin','setup_draw','post_debug_summary','post_processor_name','cpu_detect_name','setup_text')}
    def one(vendor,signature,expected,flags=0x246,id_bit=True,ac_bit=True,cyrix=False,max_leaf=1):
        u=Uc(UC_ARCH_X86,UC_MODE_16);u.mem_map(0,0x200000);u.mem_write(layout['base'],raw)
        base=0x9E000;u.mem_write(0x40E,struct.pack('<H',base>>4));u.mem_write(base+state['S_CPU_SIGNATURE'],b'\xF0\x04')
        registers={x.UC_X86_REG_EAX:0x12345678,x.UC_X86_REG_EBX:0x87654321,x.UC_X86_REG_ECX:0xABCDEF12,
            x.UC_X86_REG_EDX:0x76543210,x.UC_X86_REG_ESI:0x24681357,x.UC_X86_REG_EDI:0x13572468,
            x.UC_X86_REG_EBP:0x19283746,x.UC_X86_REG_ESP:0xCAFE6FFE,x.UC_X86_REG_CS:layout['code_segment'],
            x.UC_X86_REG_DS:0x200,x.UC_X86_REG_ES:0x300,x.UC_X86_REG_FS:base>>4,x.UC_X86_REG_GS:0x500,
            x.UC_X86_REG_SS:0,x.UC_X86_REG_EFLAGS:flags}
        queries=[];ports=[];pending=[None];division=[False];visits=[]
        def step(uc,address,size,user):
            if address in owners:visits.append(owners[address])
            if pending[0] is not None:
                current=uc.reg_read(x.UC_X86_REG_EFLAGS);mask=(0 if id_bit else 0x200000)|(0 if ac_bit else 0x40000)
                uc.reg_write(x.UC_X86_REG_EFLAGS,(current&~mask)|(pending[0]&mask));pending[0]=None
            if division[0]:
                f=uc.reg_read(x.UC_X86_REG_EFLAGS)
                uc.reg_write(x.UC_X86_REG_EFLAGS,(f&~0xD5)|(0 if cyrix else 4));division[0]=False
            if address not in instructions:instructions[address]=next(decoder.disasm(bytes(uc.mem_read(address,size)),address)).mnemonic
            op=instructions[address]
            if op=='popfd':pending[0]=uc.reg_read(x.UC_X86_REG_EFLAGS)
            if op=='div':division[0]=True
            if op=='cpuid':
                leaf=uc.reg_read(x.UC_X86_REG_EAX);queries.append(leaf);assert id_bit,'CPUID without writable ID'
                if leaf==0:
                    ebx,edx,ecx=struct.unpack('<III',vendor);values=(max_leaf,ebx,ecx,edx)
                else:
                    assert leaf==1 and max_leaf>=1,(leaf,max_leaf);values=(signature,0x99887766,0x55443322,0)
                for reg,value in zip((x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX),values):uc.reg_write(reg,value)
                uc.reg_write(x.UC_X86_REG_IP,(address-code+size)&0xFFFF)
        u.hook_add(UC_HOOK_CODE,step)
        u.hook_add(UC_HOOK_INTR,lambda uc,n,user:None if n==0x10 else (_ for _ in ()).throw(AssertionError(n)))
        u.hook_add(UC_HOOK_INSN,lambda uc,p,s,v,user:ports.append((p,s,v)),None,1,0,x.UC_X86_INS_OUT)
        u.hook_add(UC_HOOK_INSN,lambda uc,p,s,user:0,None,1,0,x.UC_X86_INS_IN)
        for reg,value in registers.items():u.reg_write(reg,value)
        u.mem_write(0x6FFE,struct.pack('<H',0xFF00))
        u.emu_start(code+listing.symbol('cpu_detect_name'),code+0xFF00,count=2000)
        assert u.reg_read(x.UC_X86_REG_IP)==0xFF00
        for reg,value in registers.items():
            wanted=value+2 if reg==x.UC_X86_REG_ESP else value
            actual=u.reg_read(reg)
            if reg==x.UC_X86_REG_ESI:assert actual>>16==value>>16
            else:assert actual==wanted,(reg,hex(actual),hex(wanted))
        si=u.reg_read(x.UC_X86_REG_SI);name=bytes(u.mem_read(code+si,32)).split(b'\0')[0].decode()
        assert name==expected,(vendor,hex(signature),name,expected)
        assert not ports,ports
        detect_queries=list(queries)
        surfaces={}
        for owner,row,column,attribute in (('post_ui_begin',2,24,7),('setup_draw',1,3,0x1B),('post_debug_summary',2,20,7)):
            for reg,value in ((x.UC_X86_REG_CS,layout['code_segment']),(x.UC_X86_REG_DS,layout['code_segment']),
                              (x.UC_X86_REG_ES,0xB800),(x.UC_X86_REG_FS,base>>4),(x.UC_X86_REG_SP,0x6FFE)):
                u.reg_write(reg,value)
            u.mem_write(0x6FFE,struct.pack('<H',0xFF00))
            start=len(visits)
            u.emu_start(code+listing.symbol(owner),code+0xFF00,count=100000)
            assert u.reg_read(x.UC_X86_REG_IP)==0xFF00,owner
            chain=visits[start:]
            processor=chain.index('post_processor_name');detector=chain.index('cpu_detect_name')
            assert chain[0]==owner and 0<processor<detector and 'setup_text' in chain[detector+1:],(owner,chain)
            cells=bytes(u.mem_read(0xB8000+row*160+column*2,len(expected)*2))
            assert cells[::2]==expected.encode() and cells[1::2]==bytes((attribute,))*len(expected),(owner,name,cells)
            surfaces[owner]={'row':row,'column':column,'attribute':attribute,'cells':cells.hex(),
                             'chain':[owner,'post_processor_name','cpu_detect_name','setup_text']}
        rows.append({'vendor':vendor.decode('ascii'),'signature':f'{signature:04X}','name':name,'flags':f'{flags:08X}',
                     'cpuid_leaves':detect_queries,'id':id_bit,'ac':ac_bit,'div_positive':cyrix,'max_leaf':max_leaf,
                     'detector_state_preserved':True,'rendered_cells':surfaces['post_ui_begin']['cells'],
                     'render_consumers':surfaces,'no_configuration_io':True})
    for vendor,expected in PRIMARY.items():
        for sig,name in expected:
            one(vendor,sig,name)
            if not vendor==b'CentaurHauls' or sig&0xFF0!=0x580:one(vendor,sig|15,name,flags=0x2408D7)
        one(vendor,0x460,'Unknown');one(vendor,0x650,'Unknown')
        one(vendor,expected[0][0],'Unknown',max_leaf=0)
        for block in range(3):
            altered=bytearray(vendor);altered[block*4+3]^=1
            one(bytes(altered),expected[0][0],'Unknown')
    for flags in (0x246,0x8D7):
        one(b'AuthenticAMD',0x4F0,'386',flags,id_bit=False,ac_bit=False,cyrix=True)
        one(b'AuthenticAMD',0x4F0,'486+',flags,id_bit=False,cyrix=False)
        one(b'AuthenticAMD',0x4F0,'Cyrix 486+ class',flags,id_bit=False,cyrix=True)
    one(b'UMC UMC UMC ',0x410,'Unknown')
    one(b'NexGenDriven',0x500,'Unknown');one(b'CentaurHauls',0x5A0,'Unknown')
    return rows
