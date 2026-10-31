; All encodings below are individual documented UMC controls, not profiles.
chipset_safe_defaults:
    call chipset_defaults
    mov byte [fs:di+1],0
    mov byte [fs:di+2],1
    ret
chipset_apply_timing:
    cache_read 0x5D
    and al,0x6F
    or al,0x20               ; Normal reference state, independent of user timing.
    or al,[fs:C_CHIP+4]
    mov cl,al
    cache_write 0x5D,cl
    cache_read 0x61
    and al,0x37
    mov bl,al
    cache_read 0x08
    cmp al,4
    mov al,bl
    jne .burst
    ; am8887's final revision04 state sets04 for both FPM and EDO.
    or al,4
    test byte [fs:C_CHIP+5],1
    jz .burst
    ; EDO is documented only on revision04; older silicon remains in FPM mode.
    or al,0xC0
.burst:
    test byte [fs:C_CHIP+5],2
    jz .dram
    or al,8
.dram:
    mov cl,al
    cache_write 0x61,cl
    cache_read 0x5A
    and al,0x20
    or al,0x0D               ; Retain the reference's final POST overlay as well.
    mov cl,al
    cache_write 0x5A,cl
    xor bl,bl               ; Never arm reporting before RAM has valid parity.
    call chipset_parity_controls
    in al,0x61
    or al,4
    out 0x61,al
    cache_read 0x52
    and al,0x7F
    test byte [fs:C_CHIP+9],1
    jz .posted
    or al,0x80
.posted:
    mov cl,al
    cache_write 0x52,cl
    cache_read 0x53
    and al,0x3F
    test byte [fs:C_CHIP+9],2
    jz .write
    or al,0x80
.write:
    mov cl,al
    cache_write 0x53,cl
    call chipset_apply_tuning
    call chipset_cyrix_apply
    ret
; Each field owns only its documented bits. FF keeps the hardware setting.
chipset_apply_tuning:
    pushad
    mov si,chipset_tuning_fields
.field:
    cmp byte [cs:si],0xFF
    je .done
    movzx bx,byte [cs:si+3]
    mov al,[fs:C_CHIP+bx]
    mov cl,[cs:si+4]
    shr al,cl
    and al,[cs:si+5]
    movzx bx,al
    mov di,[cs:si+6]
    mov bh,[cs:di+bx]
    cmp bh,0xFF
    je .next
    movzx eax,byte [cs:si]
    shl eax,11
    or eax,0x80000000
    movzx ebp,byte [cs:si+1]
    and bp,0xFC
    or eax,ebp
    mov dx,0xCF8
    out dx,eax
    mov bl,[cs:si+1]
    and bl,3
    mov dx,0xCFC
    add dl,bl
    in al,dx
    mov cl,[cs:si+2]
    not cl
    and al,cl
    or al,bh
    out dx,al
.next:
    add si,8
    jmp .field
.done:
    popad
    ret
%macro tuning_field 7
    db %1,%2,%3,%4,%5,%6
    dw %7
%endmacro
chipset_tuning_fields:
    tuning_field CFG_PLATFORM_HOST_PCI_DEVICE,0x53,0x40,7,0,1,tuning_copyback
    tuning_field CFG_PLATFORM_HOST_PCI_DEVICE,0x51,0x08,7,1,3,tuning_mem_lock
    tuning_field CFG_PLATFORM_HOST_PCI_DEVICE,0x60,0x08,7,3,3,tuning_ldev
    tuning_field CFG_PLATFORM_HOST_PCI_DEVICE,0x5A,0x01,7,5,1,tuning_turbo
    tuning_field CFG_PLATFORM_HOST_PCI_DEVICE,0x5A,0x04,7,6,1,tuning_deturbo
    tuning_field CFG_PLATFORM_HOST_PCI_DEVICE,0x5A,0x02,7,7,1,tuning_boot_speed
    tuning_field CFG_PLATFORM_HOST_PCI_DEVICE,0x5A,0x20,8,6,3,tuning_pci_parity
    tuning_field CFG_PLATFORM_ISA_PCI_DEVICE,0x40,0x04,9,2,1,tuning_pci_posted
    tuning_field CFG_PLATFORM_ISA_PCI_DEVICE,0x40,0x03,10,0,3,tuning_devsel
    tuning_field CFG_PLATFORM_ISA_PCI_DEVICE,0x41,0x02,8,0,3,tuning_lock
    tuning_field CFG_PLATFORM_ISA_PCI_DEVICE,0x41,0x04,8,2,3,tuning_park
    tuning_field CFG_PLATFORM_ISA_PCI_DEVICE,0x46,0x10,8,4,3,tuning_preempt
    tuning_field CFG_PLATFORM_ISA_PCI_DEVICE,0x56,0x03,11,0,3,tuning_isa
    tuning_field CFG_PLATFORM_ISA_PCI_DEVICE,0x56,0x0C,11,2,7,tuning_keyboard
    tuning_field CFG_PLATFORM_ISA_PCI_DEVICE,0x57,0x03,11,5,3,tuning_recovery
    tuning_field CFG_PLATFORM_ISA_PCI_DEVICE,0xA4,0x03,10,2,3,tuning_pci_clock
    db 0xFF
tuning_copyback db 0,0x40
tuning_mem_lock db 0xFF,8,0
tuning_ldev db 0xFF,0,8
tuning_turbo db 1,0
tuning_deturbo db 4,0
tuning_boot_speed db 0,2
tuning_pci_parity db 0xFF,0x20,0
tuning_pci_posted db 0,4
tuning_devsel db 0xFF,2,0,1
tuning_lock db 0xFF,0,2
tuning_park db 0xFF,0,4
tuning_preempt db 0xFF,0,0x10
tuning_isa db 1,0,2
tuning_keyboard db 0xFF,0,0x0C,8,4
tuning_recovery db 3,2,1,0
tuning_pci_clock db 0xFF,2,0,1
%include "hardware/parity.inc"
%include "hardware/cyrix.inc"
