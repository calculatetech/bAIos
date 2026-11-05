; Pack/unpack mask-selected bits, low bit first. The packed buffer starts zero.
; FS:SI=unpacked bytes, CS:BX=masks, CX=unpacked length, SS:DI=packed bytes.
settings_pack:
    pushad
    movzx esi,si
    movzx edi,di
    call settings_pack32
    popad
    ret
; Selector-safe buffer core. FS:ESI logical bytes, SS:EDI packed bytes.
settings_pack32:
    pushad
    mov dl,1
.byte:
    mov al,[fs:esi]
    mov ah,[cs:bx]
    mov dh,1
.bit:
    test ah,dh
    jz .next_bit
    test al,dh
    jz .advance
    or [ss:edi],dl
.advance:
    shl dl,1
    jnz .next_bit
    inc edi
    mov dl,1
.next_bit:
    shl dh,1
    jnz .bit
    inc esi
    inc bx
    loop .byte
    popad
    ret

settings_unpack:
    pushad
    movzx esi,si
    movzx edi,di
    call settings_unpack32
    popad
    ret
settings_unpack32:
    pushad
    mov dl,1
.byte:
    mov byte [fs:esi],0
    mov ah,[cs:bx]
    mov dh,1
.bit:
    test ah,dh
    jz .next_bit
    test [ss:edi],dl
    jz .advance
    or [fs:esi],dh
.advance:
    shl dl,1
    jnz .next_bit
    inc edi
    mov dl,1
.next_bit:
    shl dh,1
    jnz .bit
    inc esi
    inc bx
    loop .byte
    popad
    ret

; NV6 is the only extended-settings writer. Header33..35, recovery69;
; payload40..7F except69, then11/13/2D. No RTC capacity is assumed.
NV6_IDE_BITS equ 1+77*BOARD_ATA_DEVICE_COUNT+(BOARD_ATA_DEVICE_COUNT/4)*2
NV6_PORT equ (NV6_IDE_BITS+7)/8
%if BOARD_ATA_DEVICE_COUNT = 4
NV6_CHIP_BITS equ 93
%define NV6_CHIP_MASK chipset_masks
%else
NV6_CHIP_BITS equ 192
%define NV6_CHIP_MASK nv6_full_masks
%endif
NV6_CHIP equ NV6_PORT+2
NV6_PNP equ NV6_CHIP+(NV6_CHIP_BITS+7)/8
NV6_USED equ NV6_PNP+13
times -(NV6_USED > 66) db 0 ; Assembly fails if the proven payload is exceeded.

; ZF identifies this format; a damaged NV6 never falls through to legacy owners.
settings_nv6_present:
    push bx
    mov al,0x33
    call rtc_read
    mov bl,al
    mov al,0x34
    call rtc_read
    mov bh,al
    cmp bx,0x064E
    pop bx
    ret
settings_nv6_bad:
    stc
    ret

; BX=logical payload ordinal -> AL=existing adapter index. Recovery is skipped.
settings_nv6_index:
    mov ax,bx
    add al,0x40
    cmp al,0x69
    jb .done
    inc al
    cmp bl,63
    jb .done
    mov al,[cs:nv6_at_indices+bx-63]
.done:
    ret
nv6_at_indices db 0x11,0x13,0x2D

; SS:DI=66-byte payload. No writes, including on old or invalid records.
settings_nv6_read:
    push edi
    movzx edi,di
    call settings_nv6_read32
    pop edi
    ret
settings_nv6_read32:
    pushad
    call settings_nv6_present
    jne .bad
    xor ebx,ebx
    mov dl,'N'+6
.byte:
    call settings_nv6_index
    call rtc_read
    mov [ss:edi+ebx],al
    add dl,al
    inc bx
    cmp bx,66
    jb .byte
    mov al,0x35
    call rtc_read
    add dl,al
    jnz .bad
    ; Reject padding in each independently patchable slice and the unused tail.
    test byte [ss:edi+NV6_PORT-1],(0xFF << (NV6_IDE_BITS % 8)) & 0xFF
    jnz .bad
    test byte [ss:edi+NV6_CHIP-1],0xC0
    jnz .bad
%if BOARD_ATA_DEVICE_COUNT = 4
    test byte [ss:edi+NV6_PNP-1],0xE0
    jnz .bad
%endif
    test byte [ss:edi+NV6_USED-1],0xC0
    jnz .bad
    mov bx,NV6_USED
.tail:
    cmp bx,66
    jae .good
    cmp byte [ss:edi+ebx],0
    jne .bad
    inc bx
    jmp .tail
.good:
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

; SS:DI=complete payload. Invalidate before writing; verify before publication.
; Full Save publishes separately, after the base record also verifies.
settings_nv6_write:
    pushad
    movzx edi,di
    xor ebp,ebp
    inc bp
    call settings_nv6_write32
    popad
    ret
; EBP=0 uses no EBDA state; EBP=1 retains the Setup verification trace.
settings_nv6_write32:
    pushad
    mov ax,0x0033
    call rtc_write
    mov ax,0x0033
    call settings_verify_buffer_byte
    jne .bad
    mov ax,0x0634
    call rtc_write
    mov ax,0x0634
    call settings_verify_buffer_byte
    jne .bad
    xor ebx,ebx
    mov dl,'N'+6
.byte:
    call settings_nv6_index
    mov ah,[ss:edi+ebx]
    add dl,ah
    call rtc_write
    call settings_nv6_index
    mov ah,[ss:edi+ebx]
    call settings_verify_buffer_byte
    jne .bad
    inc bx
    cmp bx,66
    jb .byte
    neg dl
    mov al,0x35
    mov ah,dl
    call rtc_write
    mov al,0x35
    call settings_verify_buffer_byte
    jne .bad
    call update_cmos_checksum ; Payload includes three ordinary AT bytes.
    popad
    clc
    ret
.bad:
    call update_cmos_checksum
    popad
    stc
    ret
settings_nv6_publish:
    push ebp
    mov ebp,1
    call settings_nv6_publish32
    pop ebp
    ret
settings_nv6_publish32:
    mov ax,0x4E33
    call rtc_write
    mov ax,0x4E33
    call settings_verify_buffer_byte
    jne settings_nv6_bad
    clc
    ret

; One complete publication owner for Setup and public next-boot mutation.
; SS:EDI=66-byte payload followed by canonical base8. EBP=Setup trace flag.
; No EBDA or caller draft is accessed when EBP=0. Buffers use full offsets.
settings_commit32:
    pushad
    call settings_recovery_read
    movzx esi,al
    mov ax,0x0038
    call rtc_write
    mov ax,0xD269
    call rtc_write
    mov ax,0xD269
    call settings_verify_buffer_byte
    jne .bad
    call settings_nv6_write32
    jc .bad
    xor ebx,ebx
.base:
    call settings_base_index
    mov ah,[ss:edi+ebx+66]
    call rtc_write
    call settings_base_index
    mov ah,[ss:edi+ebx+66]
    call settings_verify_buffer_byte
    jne .bad
    inc bx
    cmp bx,8
    jb .base
    call update_cmos_checksum
    mov ax,0x4238
    call rtc_write
    mov ax,0x4238
    call settings_verify_buffer_byte
    jne .bad
    call settings_nv6_publish32
    jc .bad
    test ebp,ebp
    jz .retain_recovery
%ifdef BOARD_SETTINGS_SAVED
    call BOARD_SETTINGS_SAVED
    jc .bad
%endif
    mov ax,0x0069
    jmp .recovery
.retain_recovery:
    mov ax,si
    mov ah,al
    mov al,0x69
.recovery:
    push ax
    call rtc_write
    pop ax
    call settings_verify_buffer_byte
    jne .bad
    popad
    clc
    ret
.bad:
    call update_cmos_checksum
    popad
    stc
    ret
settings_base_index:
    mov ax,bx
    add al,0x38
    test bx,bx
    jnz .done
    mov al,0x10
.done:
    ret

; Component descriptor: payload offset, byte length, logical length, mask address.
nv6_descriptors:
    dw 0,NV6_PORT,IDE_SETTINGS_SIZE,nv6_ide_masks
    dw NV6_PORT,2,8,ports_packed_masks
    dw NV6_CHIP,(NV6_CHIP_BITS+7)/8,CHIP_SIZE,NV6_CHIP_MASK
    dw NV6_PNP,13,PNP_SIZE,nv6_pnp_masks
nv6_ide_masks:
    db 1
%rep BOARD_ATA_DEVICE_COUNT
    db 0x3F,3,15,1
    times 8 db 0xFF
%endrep
%if BOARD_ATA_DEVICE_COUNT = 4
    db 1,1
%endif
%if BOARD_ATA_DEVICE_COUNT = 2
nv6_full_masks: times CHIP_SIZE db 0xFF
%endif
nv6_pnp_masks: times 12 db 0xFF
    db 15,1,1

settings_nv6_ide_load:
    mov si,C_IDE
    xor dx,dx
    jmp settings_nv6_component_load
settings_nv6_ports_load:
    mov si,C_PORTS
    mov dx,8
    jmp settings_nv6_component_load
settings_nv6_chip_load:
    mov si,C_CHIP
    mov dx,16
    jmp settings_nv6_component_load
settings_nv6_pnp_load:
    mov si,C_PNP
    mov dx,24
settings_nv6_component_load:
    pushad
    sub sp,66
    mov bp,sp
    mov di,bp
    call settings_nv6_read
    jc .done
    mov bx,dx
    add di,[cs:nv6_descriptors+bx]
    mov cx,[cs:nv6_descriptors+bx+4]
    mov bx,[cs:nv6_descriptors+bx+6]
    call settings_unpack
    clc
.done:
    lea sp,[bp+66]
    popad
    ret

settings_nv6_ide_save:
    xor dx,dx
    jmp settings_nv6_component_save
settings_nv6_ports_save:
    mov dx,8
    jmp settings_nv6_component_save
settings_nv6_chip_save:
    mov dx,16
settings_nv6_component_save:
    pushad
    sub sp,66
    mov bp,sp
    mov di,bp
    call settings_nv6_read
    jc .done
    call settings_nv6_pack_component
    mov di,bp
    call settings_nv6_write
    jc .done
    call settings_nv6_publish
.done:
    lea sp,[bp+66]
    popad
    ret

; BP=payload, DX=descriptor byte offset, FS:SI=one validated logical owner.
settings_nv6_pack_component:
    pushad
    mov bx,dx
    mov di,bp
    add di,[cs:nv6_descriptors+bx]
    mov cx,[cs:nv6_descriptors+bx+2]
    push di
.zero:
    mov byte [ss:di],0
    inc di
    loop .zero
    pop di
    mov cx,[cs:nv6_descriptors+bx+4]
    mov bx,[cs:nv6_descriptors+bx+6]
    call settings_pack
    popad
    ret

; SS:DI receives the complete validated Setup payload, without publication.
settings_nv6_build_all:
    pushad
    mov si,U_IDE
    call ide_settings_valid
    jc .bad
%ifdef BOARD_PORTS_SAVE_FILTER
    call BOARD_PORTS_SAVE_FILTER
%endif
%ifndef BOARD_PORTS_PAIRS
    mov byte [fs:U_PORTS+2],1
%endif
    mov byte [fs:U_PORTS+7],1
    mov si,U_PORTS
    call ports_valid
    jc .bad
    mov si,U_CHIP
%ifdef PB430_PORT
    call chipset_profile_apply
%endif
    call chipset_valid
    jc .bad
    mov si,U_PNP
    call pnp_settings_valid
    jc .bad
    mov bp,di
    mov cx,66
.zero:
    mov byte [ss:di],0
    inc di
    loop .zero
    xor dx,dx
    mov si,U_IDE
    call settings_nv6_pack_component
    mov dx,8
    mov si,U_PORTS
    call settings_nv6_pack_component
    mov dx,16
    mov si,U_CHIP
    call settings_nv6_pack_component
    mov dx,24
    mov si,U_PNP
    call settings_nv6_pack_component
    mov di,bp
    clc
    popad
    ret
.bad:
    popad
    stc
    ret

pnp_defaults:
    pushad
    mov cx,PNP_SIZE
.byte:
    mov byte [fs:di],0
    inc di
    loop .byte
    popad
    ret

; A zero length disables a window but retains its base for later editing.
; Nonempty windows may overlap; allocation reserves their union.
pnp_settings_valid:
    pushad
    test byte [fs:si+PNP_MEMORY+1],0xF0
    jnz .bad
    cmp byte [fs:si+PNP_POLICY],1
    ja .bad
    cmp byte [fs:si+PNP_CLEAR],1
    ja .bad
    add si,PNP_IO
    mov cx,2
.window:
    movzx eax,word [fs:si]
    movzx edx,word [fs:si+2]
    add eax,edx
    cmp eax,0x10000
    ja .bad
    add si,4
    loop .window
    popad
    clc
    ret
.bad:
    popad
    stc
    ret
