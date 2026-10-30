; UMC register owners plus verified non-M919 reference normal-state values.
; Unknown field names do not make established reference values optional.
%macro early_chipset_write 1
    mov eax,0x80000000 | (%1 << 11)
    movzx ecx,bl
    and cl,0xFC
    or eax,ecx
    mov dx,0xCF8
    out dx,eax
    movzx dx,bl
    and dx,3
    add dx,0xCFC
    mov al,bh
    out dx,al
%endmacro
%macro early_chipset_update 4
    mov eax,0x80000000 | (%1 << 11) | ((%2) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC + ((%2) & 3)
    in al,dx
    and al,~(%3) & 0xFF
    or al,%4
    out dx,al
%endmacro
chipset_initialize:
    ; HB50: L2 off. HB51: 3 read/write waits, 8-bit WT tags, no merging.
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x50,0xFF,0
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x51,0xF5,1
    ; External, protected ROM; no BIOS caching or memory hole.
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x54,0xFF,0
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x55,0xE1,0x40
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x57,0x80,0
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x52,0x80,0
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x53,0xC0,0
    ; 8810AIO initializes04, then its unconditional final POST overlay adds09.
    ; Keep parity masked and both transient modes off until their owners run.
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x5A,0xDF,0x0D
    ; Phoenix and AMI establish20; Biostar30 includes optional slow refresh10.
    ; Preserve the separate SMRAM address field and unnamed bit40.
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x5D,0xB0,0x20
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x60,1,0
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x61,0xCA,0
    early_chipset_update CFG_PLATFORM_HOST_PCI_DEVICE,0x62,2,0
    ; IBC: disable posting and AUX pin functions; protect flash, no PCI IRQs yet.
    early_chipset_update CFG_PLATFORM_ISA_PCI_DEVICE,0x40,0x14,0
    early_chipset_update CFG_PLATFORM_ISA_PCI_DEVICE,0x45,1,0
    early_chipset_update CFG_PLATFORM_ISA_PCI_DEVICE,0x46,0x0F,0
    early_chipset_update CFG_PLATFORM_ISA_PCI_DEVICE,0x47,0x40,0x40
    ; PCI/4 ISA clock and 12 BCLK recovery. F is always decoded; E is padding.
    early_chipset_update CFG_PLATFORM_ISA_PCI_DEVICE,0x56,3,1
    early_chipset_update CFG_PLATFORM_ISA_PCI_DEVICE,0x57,0xEF,7
    ; Disable the documented green timer.
    early_chipset_update CFG_PLATFORM_ISA_PCI_DEVICE,0x70,0x0F,0x0E
    mov al,0x54
    out 0x43,al
    mov al,0x12
    out 0x41,al
    in al,0x92
    and al,0xFE
    or al,2
    out 0x92,al
    post_code_early 0x20
    jmp flat_addressing
host_write:
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    ret
isa_write:
    early_chipset_write CFG_PLATFORM_ISA_PCI_DEVICE
    ret

; AL=HB51. The UMC guide associates bit1 with L1 WT/WB (tentative meaning).
; AMD19751C section10.2 identifies Am5x86 WT modelE and WB modelF.
; Change this control only when CPUID establishes that mode and vendor.
chipset_l1_protocol:
    pushfd
    pushad
    mov bp,sp
    pushfd
    pop eax
    mov ecx,eax
    xor eax,0x00200000
    push eax
    popfd
    pushfd
    pop eax
    xor eax,ecx
    test eax,0x00200000
    jz .done
    xor eax,eax
    cpuid
    cmp eax,1
    jb .done
    cmp ebx,0x68747541
    jne .done
    cmp edx,0x69746E65
    jne .done
    cmp ecx,0x444D4163
    jne .done
    mov eax,1
    cpuid
    and eax,0x0FF0
    cmp eax,0x04F0
    jne .wt
    and byte [ss:bp+28],0xFD
    jmp .done
.wt:
    cmp eax,0x04E0
    jne .done
    or byte [ss:bp+28],2
.done:
    popad
    popfd
    ret
