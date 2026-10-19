; Guarded identity only. Primary signature tables and ambiguities: shared/README.md.
; Return CS:SI name, preserving every other register and the caller's EFLAGS.
cpu_detect_name:
    pushfd
    pushad
    mov si,cpu_name_unknown
    pushfd
    pop eax
    mov ecx,eax
    xor eax,0x00200000
    push eax
    popfd
    pushfd
    pop eax
    push ecx
    popfd
    xor eax,ecx
    test eax,0x00200000
    jz .legacy
    xor eax,eax
    cpuid
    cmp eax,1
    jb .done
    mov di,cpu_vendors
.vendor:
    cmp ebx,[cs:di]
    jne .next_vendor
    cmp edx,[cs:di+4]
    jne .next_vendor
    cmp ecx,[cs:di+8]
    je .signature
.next_vendor:
    add di,14
    cmp di,cpu_vendors_end
    jb .vendor
    jmp .done
.signature:
    mov di,[cs:di+12]
    mov eax,1
    cpuid
    mov dx,ax
    and dx,0x0FF0
    cmp di,cpu_intel
    jne .centaur
    mov cx,ax
    and cx,0x3000
    cmp cx,0x1000
    jne .table
    mov si,cpu_name_dx4od
    cmp dx,0x0480            ; AP485 Table4 explicitly identifies this OverDrive.
    je .done
    mov si,cpu_name_486od
    cmp dh,4
    je .done
    cmp dx,0x0530
    je .p24t
    cmp dx,0x0540
    je .mmxod
    cmp dx,0x0510
    je .pentiumod
    cmp dx,0x0520
    jne .table
.pentiumod:
    mov si,cpu_name_pentiumod
    jmp .done
.p24t:
    mov si,cpu_name_p24t
    jmp .done
.mmxod:
    mov si,cpu_name_mmxod
    jmp .done
.centaur:
    cmp di,cpu_centaur
    jne .table
    cmp dx,0x0580
    jne .table
    and al,15
    mov si,cpu_name_winchip2
    cmp al,6
    jbe .done
    mov si,cpu_name_winchip2a
    cmp al,9
    jbe .done
    mov si,cpu_name_winchip2b
    jmp .done
.table:
    mov si,cpu_name_unknown
.row:
    cmp word [cs:di],0
    je .done
    cmp dx,[cs:di]
    je .match
    add di,4
    jmp .row
.match:
    mov si,[cs:di+2]
    jmp .done
.legacy:
    mov si,cpu_name_386
    mov eax,ecx
    xor eax,0x00040000
    push eax
    popfd
    pushfd
    pop eax
    push ecx
    popfd
    xor eax,ecx
    test eax,0x00040000
    jz .done
    mov si,cpu_name_486
    xor ax,ax
    sahf
    mov ax,5
    mov bx,2
    div bl
    lahf
    cmp ah,2
    jne .done
    ; Early SLC/DLC send FE/FF off-chip: DIV does not prove DIR availability.
    mov si,cpu_name_cyrix_legacy
.done:
    mov bp,sp
    mov [ss:bp+4],si
    popad
    popfd
    ret

cpu_vendors:
    dd 0x756E6547,0x49656E69,0x6C65746E
    dw cpu_intel
    dd 0x68747541,0x69746E65,0x444D4163
    dw cpu_amd
    dd 0x69727943,0x736E4978,0x64616574
    dw cpu_cyrix
    dd 0x20434D55,0x20434D55,0x00434D55
    dw cpu_umc
    dd 0x746E6543,0x48727561,0x736C7561
    dw cpu_centaur
    dd 0x4778654E,0x72446E65,0x6E657669
    dw cpu_nexgen
    dd 0x65736952,0x65736952,0x65736952
    dw cpu_rise
cpu_vendors_end:
cpu_intel:
    dw 0x0400,cpu_name_dx,0x0410,cpu_name_dx,0x0420,cpu_name_sx
    dw 0x0430,cpu_name_dx2_487,0x0440,cpu_name_sl,0x0450,cpu_name_sx2
    dw 0x0470,cpu_name_dx2,0x0480,cpu_name_dx4,0x0490,cpu_name_dx4
    dw 0x0510,cpu_name_pentium,0x0520,cpu_name_pentium,0x0540,cpu_name_mmx
    dw 0,0
cpu_amd:
    dw 0x0430,cpu_name_amdx2,0x0470,cpu_name_amdx2
    dw 0x0480,cpu_name_amdx4_5x86,0x0490,cpu_name_amdx4_5x86
    dw 0x04E0,cpu_name_am5x86,0x04F0,cpu_name_am5x86
    dw 0x0500,cpu_name_k5,0x0510,cpu_name_k5,0x0520,cpu_name_k5,0x0530,cpu_name_k5
    dw 0x0560,cpu_name_k6,0x0570,cpu_name_k6,0x0580,cpu_name_k62
    dw 0x0590,cpu_name_k63,0x05D0,cpu_name_k6plus
    dw 0,0
cpu_cyrix:
    dw 0x0440,cpu_name_mediagx,0x0520,cpu_name_6x86,0x0540,cpu_name_gxm
    dw 0,0
cpu_umc:
    dw 0x0410,cpu_name_u5d,0x0420,cpu_name_u5s,0,0
cpu_centaur:
    dw 0x0540,cpu_name_winchip,0x0590,cpu_name_winchip3,0,0
cpu_nexgen:
    dw 0x0510,cpu_name_nx586,0,0
cpu_rise:
    dw 0x0500,cpu_name_idragon,0x0520,cpu_name_idragon
    dw 0x0580,cpu_name_idragon2,0x0590,cpu_name_idragon2,0,0

cpu_name_unknown db 'Unknown',0
cpu_name_386 db '386',0
cpu_name_486 db '486+',0
cpu_name_dx db '486DX',0
cpu_name_sx db '486SX',0
cpu_name_dx2_487 db '486DX2/487/OD',0
cpu_name_sl db '486SL',0
cpu_name_sx2 db '486SX2',0
cpu_name_dx2 db '486DX2',0
cpu_name_dx4 db '486DX4',0
cpu_name_486od db '486 OverDrive',0
cpu_name_dx4od db '486DX4 OD',0
cpu_name_pentium db 'Pentium',0
cpu_name_pentiumod db 'Pentium OverDrive',0
cpu_name_p24t db 'Pentium P24T',0
cpu_name_mmx db 'Pentium MMX',0
cpu_name_mmxod db 'Pentium MMX OD',0
cpu_name_amdx2 db 'AMD 486DX2',0
cpu_name_amdx4_5x86 db 'AMD DX4/5x86',0
cpu_name_am5x86 db 'AMD 5x86',0
cpu_name_k5 db 'AMD K5',0
cpu_name_k6 db 'AMD K6',0
cpu_name_k62 db 'AMD K6-2',0
cpu_name_k63 db 'AMD K6-III',0
cpu_name_k6plus db 'AMD K6-2+/III+',0
cpu_name_cyrix_legacy db 'Cyrix 486+ class',0
cpu_name_mediagx db 'Cyrix MediaGX',0
cpu_name_6x86 db 'Cyrix 6x86/L',0
cpu_name_gxm db 'Cyrix GXm',0
cpu_name_u5d db 'UMC U5D',0
cpu_name_u5s db 'UMC U5S',0
cpu_name_winchip db 'WinChip C6',0
cpu_name_winchip2 db 'WinChip 2',0
cpu_name_winchip2a db 'WinChip 2A',0
cpu_name_winchip2b db 'WinChip 2B',0
cpu_name_winchip3 db 'WinChip 3',0
cpu_name_nx586 db 'NexGen Nx586',0
cpu_name_idragon db 'Rise iDragon',0
cpu_name_idragon2 db 'Rise iDragon II',0
