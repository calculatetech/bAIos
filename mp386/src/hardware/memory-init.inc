; OEM07C0..092B,0EF0..1027,1D19..1E97,106B..12FC,2414..2452.
; This adapter owns discovery/probing/maps without writing OEM0240..02FF records.
; Restricted to the supported old controllers. Preserve native geometry/probe
; transactions; forced cold starts without the OEM reset gate use captured profiles.
; Six upperGPR halves retain raw bankcounts until qualifiedRAM exists.
; UpperBP=count, lowerSP=ROMreturn, BP=native continuation; upperSP=resetidentity.
%define MP_MEMORY_RECORDS 0x0600
%macro mp_mcu_write 0
    xchg ax,dx
    out 0x26,ax
    xchg ax,dx
    out 0x24,ax
%endmacro
%macro mp_mcu_read 0
    mov ax,dx
    out 0x26,ax
    in ax,0x24
%endmacro
%macro mp_mcu_native_write 0
    mov bp,%%done
    jmp mp_memory_ti_write
%%done:
%endmacro
%macro mp_mcu_native_read 0
    mov bp,%%done
    jmp mp_memory_ti_read
%%done:
%endmacro
%macro mp_mcu_native_check 0
    mov bp,%%done
    jmp mp_memory_ti_check_begin
%%done:
    jc mp_memory_failed
%endmacro
%macro mp_mcu_count 1
    ror ebp,16
    mov %1,bp
    ror ebp,16
%endmacro
%macro mp_save_bank 2
%ifidni %1,eax
    ror eax,16
    mov ax,cx
    ror eax,16
%else
    mov ax,cx
    ror %1,16
    mov %2,ax
    ror %1,16
%endif
%endmacro
; Keep the six upper-half counts intact until the normal layout owns low RAM.
%macro mp_equal_bank_flag 5
    ror %1,16
    ror %3,16
    cmp %2,%4
    jne %%separate
    test %2,%2
    jz %%separate
    ror %3,16
    ror %1,16
    or bx,%5
    jmp %%done
%%separate:
    ror %3,16
    ror %1,16
%%done:
%endmacro
; OEM1DB3..1E97: fixedCPU0/CFFC probe; mapDATA increments4.
; All pages are seeded first; firstpage5555 stays as the alias sentinel.
%macro mp_probe_bank 4
    mp_mcu_count ax
    cmp ax,%1
    jbe %%absent
    mov dx,0x8000+(%1*0x1000)
    mov si,%2
    mov ax,si
    mov bp,%%mapped
    jmp mp_memory_ti_write
%%mapped:
    mov bl,1
    mov bp,%%first_ok
    jmp mp_probe_oem_begin
%%first_ok:
    jmp near %%first_counted   ; Native failure return skips exactly three bytes.
%%first_failed:
    xor cx,cx
    jmp %%finished
%%first_counted:
    xor bl,bl
    mov cx,1
%%next:
    cmp cx,512
    jae %%finished
    mov ax,si
    add ax,4
    or ah,0x80
    mov bp,%%page_mapped
    jmp mp_memory_ti_write
%%page_mapped:
    mov si,ax                 ; Upper EAX already owns bank0's count.
    mov bp,%%page_ok
    jmp mp_probe_oem_begin
%%page_ok:
    jmp near %%count_page
%%page_failed:
    jmp %%finished
%%count_page:
    inc cx
    and si,0x7FFF
    jmp %%next
%%finished:
    xor ax,ax
    mov bp,%%closed
    jmp mp_memory_ti_write
%%closed:
    mp_save_bank %3,%4
%%absent:
    mov bp,sp
%endmacro

; OEM1E45..1E97, including every branch between the physical memory accesses.
mp_probe_oem_begin:
    xor ax,ax
    mov ds,ax
    xor di,di
    test bl,1
    jnz .pattern
    mov ax,[di]
    cmp ax,0x5555
    jne .pattern
    jmp short $+2
    mov ax,0
    mov [di],ax
    jmp short .failed
    nop
.pattern:
    mov ax,0x5555
    mov [di],ax
    jmp short $+2
    mov ax,[di]
    cmp ax,0x5555
    jne .failed
    test bl,1
    jnz .second
    jmp short $+2
    mov ax,0
    mov [di],ax
.second:
    mov ax,0xCFFC
    mov di,ax
    mov ax,0xAAAA
    mov [di],ax
    jmp short $+2
    mov ax,[di]
    cmp ax,0xAAAA
    jne .failed
    xor ax,ax
    mov [di],ax
    jmp bp
.failed:
    add bp,3
    jmp bp
mp_probe_oem_end:

tiger_cold:
    mov bp,sp
    and ebp,0xFFFF
    mov sp,.atu_return
    jmp mitsubishi_atu_initialize
.atu_return: dw .discover_begin
.discover_begin:
    mov sp,bp
    mov dx,0x0800
    mp_mcu_read
    and ah,3
    cmp ah,2
    jne mp_memory_failed
    xor bx,bx
    xor si,si
.discover:
    mov dx,si
    mp_mcu_read
    mov cx,si
    and ah,7
    cmp ah,ch
    jne .not_present
    cmp si,0x0300
    je mp_memory_failed
    cmp bl,ch
    jne mp_memory_failed
    inc bl
.not_present:
    add si,0x0100
    cmp si,0x0400
    jb .discover
    test bl,bl
    jz mp_memory_failed
    ror ebp,16
    mov bp,bx
    ror ebp,16
    xor si,si
; OEM07C0..08B4 prepares every controller before08B7..092B clears any maps.
mp_memory_prepare_begin:
    xor si,si
mp_memory_reset_controller:
    mov dx,si
    mp_mcu_native_read
    mov cx,si
    and ah,7
    cmp ah,ch
    jne mp_memory_failed
    xor ax,ax
    mp_mcu_native_write
    mov dl,6
    xor ax,ax
    mp_mcu_native_check
    inc dl
    xor ax,ax
    mp_mcu_native_check
    in al,0x5E
    test al,5
    jnz .geometry
    ; OEM can retain configuration here; forced bAIos cold discovery cannot.
    mov dl,4
    mov ax,0x36E4
    test si,si
    jnz .profile
    mov ax,0x10E4
.profile:
    mp_mcu_native_write
    inc dl
    mp_mcu_native_write
    jmp .prepared
.geometry:
    mov dl,3
    mov ax,0x4101
    mp_mcu_native_check
    mov dl,2
    mov ax,0x8100
    mov bp,.mode_ready
    jmp mp_memory_ti_write
.mode_ready:
    mov dx,si
    shl dx,4
    or dh,0x80
    mov cx,dx
    mov ax,0x8000
    mov bp,.geometry_mapped
    jmp mp_memory_ti_write
.geometry_mapped:
    xor ax,ax
    mov ds,ax
    mov dx,si
    mov dl,4
    mov ax,0x36E4
    mov bp,.first_profile
    jmp mp_memory_ti_write
.first_profile:
    inc dl
    mov bp,.profiles_ready
    jmp mp_memory_ti_write
.profiles_ready:
    mov ax,0x0FF0
    mov di,ax
    mov ax,0x1234
    mov bx,ax
    mov [di],ax
    mov ax,0x1FF0
    mov di,ax
    mov ax,[di]
    cmp ax,bx
    jne .geometry_done
    mov ax,0x10E4
    mov bp,.small_second
    jmp mp_memory_ti_write
.small_second:
    dec dl
    mov bp,.geometry_done
    jmp mp_memory_ti_write
.geometry_done:
    mov dx,cx
    xor ax,ax
    mov bp,.geometry_cleared
    jmp mp_memory_ti_write
.geometry_cleared:
    mov dx,si
.prepared:
    mov dl,3
    mov ax,0x4001
    mp_mcu_native_write
    mov dl,0x0A
    mov ax,0x00FF
    mp_mcu_native_write
    add si,0x0100
    mov ax,si
    shr ax,8
    mp_mcu_count cx
    cmp ax,cx
    jb mp_memory_reset_controller
    mov dx,si
    mp_mcu_native_read
    and ah,7
    cmp ah,dh
    je mp_memory_failed
mp_memory_prepare_end:
    mov bp,sp
mp_memory_map_clear_begin:
    xor si,si
.controller:
    mov dx,si
    mov dl,2
    mov ax,0x8100
    mp_mcu_native_write
    mov dx,si
    shl dx,4
    or dh,0x80
    mov cx,0x40
.clear_low:
    xor ax,ax
    mp_mcu_native_write
    inc dx
    loop .clear_low
    mov dx,si
    mov dl,2
    mov ax,0x8160
    mp_mcu_native_write
    mov dx,si
    shl dx,4
    or dh,0x80
    mov cx,0x200
.clear_high:
    xor ax,ax
    mp_mcu_native_write
    add dx,4
    loop .clear_high
    add si,0x0100
    mov ax,si
    shr ax,8
    mp_mcu_count cx
    cmp ax,cx
    jb .controller
mp_memory_map_clear_end:
mp_memory_environment_begin:
    ; OEM0B88..0BE7 hardware environment. OEM FC01/FC10 display state is private.
    mov al,0x80
    out 0x70,al
    mov al,4
    out 0x08,al
    out 0xD0,al
    mov dx,0x3B8
    mov al,1
    out dx,al
    jmp short $+2
    mov dx,0x3D8
    xor al,al
    out dx,al
    jmp short $+2
    mov dx,0x3DA
    in al,dx
    jmp short $+2
    mov dx,0x3C0
    xor al,al
    out dx,al
    jmp short $+2
    mov dx,0x3DA
    in al,dx
    jmp short $+2
    mov dx,0x3B4
    mov al,0xB9
    out dx,al
    jmp short $+2
    inc dx
    mov al,0x48
    out dx,al
    jmp short $+2
    mov dx,0x3D4
    mov al,0xB9
    out dx,al
    jmp short $+2
    inc dx
    mov al,0x48
    out dx,al
    jmp short $+2
    mov al,0xB0
    out 0x70,al
    xor al,al
    out 0x71,al
    mov al,0xB1
    out 0x70,al
    xor al,al
    out 0x71,al
    mov al,0x0C
    out 0x61,al
mp_memory_environment_end:
mitsubishi_board_reset_kind_begin:
    mitsubishi_board_reset_kind
mitsubishi_board_reset_kind_end:
    ; OEM0C88..0CC9: retain the complete ROM-read interval before PIT setup.
    mov ax,cs
    mov es,ax
    xor ax,ax
    xor bp,bp
    mov bx,2
.rom_sum:
    sub al,[es:bp]
    sub ah,[es:bp+1]
    sub bp,bx
    jnz .rom_sum
    add al,ah
    test al,al
    jnz mp_memory_failed
mp_memory_refresh_begin:
    mov al,0x70
    out 0x43,al
    mov al,0xFF
    out 0x41,al
    xor al,al
    out 0x41,al
    mov bx,0xFF00
.refresh_wait:
    dec bx
    jz mp_memory_failed
    mov al,0x40
    out 0x43,al
    in al,0x41
    cmp al,0xFF
    setne ah
    in al,0x41
    test al,al
    jnz mp_memory_failed
    dec ah
    jnz .refresh_wait
    mov al,0x54
    out 0x43,al
    mov al,0x12
    out 0x41,al
mp_memory_refresh_end:
mitsubishi_board_defaults_begin:
    mitsubishi_board_controls
mitsubishi_board_defaults_end:
    mov bp,sp
    xor ax,ax
    mov ds,ax
    xor si,si
; Complete OEM0F2C..0F72 seed sweep, not only the pages eventually counted.
mp_memory_seed_begin:
    mp_mcu_count bx
    xor di,di
    mov dx,0x8000
.seed_controller:
    mov cx,0x200
    mov ax,0x8000
.seed:
    mov bp,.seed_first
    jmp mp_memory_ti_write
.seed_first:
    shl eax,16
    xor ax,ax
    mov [di],ax
    shr eax,16
    or ah,0x40
    mov bp,.seed_second
    jmp mp_memory_ti_write
.seed_second:
    shl eax,16
    xor ax,ax
    mov [di],ax
    shr eax,16
    and ah,0xBF
    add ax,4
    dec cx
    jnz .seed
    xor ax,ax
    mov bp,.seed_closed
    jmp mp_memory_ti_write
.seed_closed:
    add dh,0x10
    dec bl
    jnz .seed_controller
    mov bp,sp
    and eax,0xFFFF
    and ebx,0xFFFF
    and ecx,0xFFFF
    and edx,0xFFFF
    and esi,0xFFFF
    and edi,0xFFFF
mp_memory_probe_begin:
mp_memory_bank0_begin:
    mp_probe_bank 0,0x8000,eax,ax
mp_memory_bank0_end:
mp_memory_bank1_begin:
    mp_probe_bank 0,0xC000,ebx,bx
mp_memory_bank1_end:
mp_memory_bank2_begin:
    mp_probe_bank 1,0x8000,ecx,cx
mp_memory_bank2_end:
mp_memory_bank3_begin:
    mp_probe_bank 1,0xC000,edx,dx
mp_memory_bank3_end:
mp_memory_bank4_begin:
    mp_probe_bank 2,0x8000,esi,si
mp_memory_bank4_end:
mp_memory_bank5_begin:
    mp_probe_bank 2,0xC000,edi,di
mp_memory_bank5_end:
mp_memory_probe_end:
mp_memory_normal_begin:
    ; Quadtel8BB6/8C57 and ICL1C9D/1EDB couple contiguous banks with CTRL0100.
    xor bx,bx
    mp_equal_bank_flag eax,ax,ebx,bx,1
    mp_equal_bank_flag ecx,cx,edx,dx,2
    mp_equal_bank_flag esi,si,edi,di,4
    xor si,si
.normal:
    mov dx,si
    mov dl,2
    mov ax,0x8100
    mp_mcu_write
    mov dl,3
    mov ax,0x4001
    test bx,1
    jz .write_control
    or ah,1
.write_control:
    mp_mcu_write
    shr bx,1
    add si,0x0100
    mov ax,si
    shr ax,8
    mp_mcu_count cx
    cmp ax,cx
    jb .normal
mp_memory_normal_end:
; OEM1313..137B sized base aperture; measuredport49bit7 needs512KiB.
    ror eax,16
    mov cx,ax
    ror eax,16
    cmp cx,8
    jb mp_memory_failed
    mov dx,0x8000
    mov bx,0x8000
    mov cx,0x20
.base:
    mov ax,bx
    mp_mcu_write
    inc bx
    inc dx
    loop .base
    mov di,MP_MEMORY_SCRATCH
    mov cx,0x100
.qualify:
    mov word [di],0x55AA
    cmp word [di],0x55AA
    jne mp_memory_failed
    mov word [di],0xAA55
    cmp word [di],0xAA55
    jne mp_memory_failed
    add di,2
    loop .qualify
mp_memory_scratch_ready:
    ror eax,16
    mov [MP_MEMORY_SCRATCH],ax
    ror eax,16
    ror ebx,16
    mov [MP_MEMORY_SCRATCH+2],bx
    ror ebx,16
    ror ecx,16
    mov [MP_MEMORY_SCRATCH+4],cx
    ror ecx,16
    ror edx,16
    mov [MP_MEMORY_SCRATCH+6],dx
    ror edx,16
    ror esi,16
    mov [MP_MEMORY_SCRATCH+8],si
    ror esi,16
    ror edi,16
    mov [MP_MEMORY_SCRATCH+10],di
    ror edi,16
    mp_mcu_count ax
    mov [MP_MEMORY_SCRATCH+12],ax
    mov [MP_MEMORY_SCRATCH+18],bp
; QualifiedlowRAM replaces OEMprivate storage; only mappergenerated inputs exist.
    mov di,MP_MEMORY_RECORDS
    mov cx,0x80
    xor ax,ax
    mov es,ax
    rep stosw
    xor si,si
    xor bx,bx
    mov cx,6
.inventory:
    mov ax,[MP_MEMORY_SCRATCH+si]
    cmp ax,512
    ja mp_memory_failed
    add bx,ax
    jc mp_memory_failed
    add si,2
    loop .inventory
    cmp bx,512
    ja mp_memory_failed
    cmp bx,16
    jbe mp_memory_failed
    mov [MP_MEMORY_SCRATCH+14],bx
    mov [MP_MEMORY_RECORDS+0x40],bx
    sub bx,16
    mov [MP_MEMORY_RECORDS+0x4A],bx
    mov word [MP_MEMORY_RECORDS+0x4E],40
    mov ax,[MP_MEMORY_SCRATCH+12]
    cmp ax,1
    jb mp_memory_failed
    cmp ax,3
    ja mp_memory_failed
    mov [MP_MEMORY_RECORDS+0xDD],al
    xor si,si
    xor di,di
.records:
    mov ax,[MP_MEMORY_SCRATCH+si]
    add ax,[MP_MEMORY_SCRATCH+si+2]
    mov [MP_MEMORY_RECORDS+0x42+di],ax
    ; Keep the zero bases used by the first physically working bank-map policy.
    mov word [MP_MEMORY_RECORDS+0x9D+di],0x8100
    mov dx,0x4001
    mov ax,[MP_MEMORY_SCRATCH+si]
    test ax,ax
    jz .control_record
    cmp ax,[MP_MEMORY_SCRATCH+si+2]
    jne .control_record
    or dh,1
.control_record:
    mov [MP_MEMORY_RECORDS+0xA5+di],dx
    add si,4
    add di,2
    cmp di,6
    jb .records
    ; Locate physical1MiB even when MCU0 ends exactly at that boundary.
    mov bx,16
    xor di,di
.high_source:
    mov ax,[MP_MEMORY_RECORDS+0x42+di]
    cmp bx,ax
    jb .source_ready
    sub bx,ax
    add di,2
    cmp di,6
    jb .high_source
    jmp mp_memory_failed
.source_ready:
    shl bx,2
    shl di,11
    or bx,di
    mov [MP_MEMORY_RECORDS+0xAD],bx
    ; Reserve F backing wholly inside the unused640KiB..1MiB physical hole.
    cmp word [MP_MEMORY_RECORDS+0x42],16
    jb .no_shadow
    mov byte [MP_MEMORY_RECORDS+0x4F],4
    mov byte [MP_MEMORY_RECORDS+0x81],1
    mov word [MP_MEMORY_RECORDS+0xB3],0x0028
.no_shadow:
    ; Keep qualifiedscratch reachable while the unchangedmapper selects8160.
    ; OnlyROM instructions execute during the brief aperture setup/removal gaps.
mp_memory_scratch_aperture_begin:
    mov dx,2
    mov ax,0x8160
    mp_mcu_write
    mov dx,0x8000
    mov ax,0x8000
    mp_mcu_write
    mov dx,2
    mov ax,0x8100
    mp_mcu_write
mp_memory_scratch_aperture_end:
    jmp oem_map_106B
; Exact OEM106B..12FC mapper and2414 helper. Only storage helpers are adapted.
; OEM1030..106A checksum/RTCvalidity owner is omitted: records are newlygenerated.
mp_memory_read_record:
    xchg bx,dx
    mov al,[bx+MP_MEMORY_RECORDS-0x0200]
    xchg bx,dx
    jmp bp
mp_memory_ti_write:
    cli
    mp_mcu_write
    jmp bp
mp_memory_ti_read:
    cli
    mp_mcu_read
    jmp bp
; Native OEM1C55..1C69 write/readback, including its transaction spacing.
mp_memory_ti_check_begin:
    cli
    mp_mcu_write
    mov bx,ax
    mov ax,dx
    out 0x26,ax
    in ax,0x24
    xor ax,bx
    jz .matched
    stc
.matched:
    jmp bp
mp_memory_ti_check_end:
oem_map_106B:
    mov dx, 0x2dd
oem_map_106E:
    mov bp,oem_map_1074
oem_map_1071:
    jmp mp_memory_read_record
oem_map_1074:
    mov cl, al
oem_map_1076:
    xor ah, ah
oem_map_1078:
    mov bx, 0
oem_map_107B:
    mov dx, 0x299
oem_map_107E:
    mov bp,oem_map_1084
oem_map_1081:
    jmp mp_memory_read_record
oem_map_1084:
    xchg dx, bx
oem_map_1086:
    mov bp,oem_map_108C
oem_map_1089:
    jmp mp_memory_ti_write
oem_map_108C:
    inc dh
oem_map_108E:
    xchg dx, bx
oem_map_1090:
    inc dx
oem_map_1091:
    dec cl
oem_map_1093:
    jne oem_map_107E
oem_map_1095:
    mov dx, 0x2dd
oem_map_1098:
    mov bp,oem_map_109E
oem_map_109B:
    jmp mp_memory_read_record
oem_map_109E:
    mov cl, al
oem_map_10A0:
    mov bx, 0
oem_map_10A3:
    mov dx, 0x2a6
oem_map_10A6:
    mov bp,oem_map_10AC
oem_map_10A9:
    jmp mp_memory_read_record
oem_map_10AC:
    mov ah, al
oem_map_10AE:
    dec dx
oem_map_10AF:
    mov bp,oem_map_10B5
oem_map_10B2:
    jmp mp_memory_read_record
oem_map_10B5:
    shl eax, 0x10
oem_map_10B9:
    xchg dx, bx
oem_map_10BB:
    mov bp,oem_map_10C1
oem_map_10BE:
    jmp mp_memory_ti_read
oem_map_10C1:
    mov ch, ah
oem_map_10C3:
    shr eax, 0x10
oem_map_10C7:
    mov dl, 3
oem_map_10C9:
    test ch, 0xf0
oem_map_10CC:
    jne oem_map_10D0
oem_map_10CE:
    and al, 0xf
oem_map_10D0:
    mov bp,oem_map_10D6
oem_map_10D3:
    jmp mp_memory_ti_write
oem_map_10D6:
    inc dh
oem_map_10D8:
    mov dl, 0
oem_map_10DA:
    xchg dx, bx
oem_map_10DC:
    add dx, 3
oem_map_10DF:
    dec cl
oem_map_10E1:
    jne oem_map_10A6
oem_map_10E3:
    mov dx, 0x24b
oem_map_10E6:
    mov bp,oem_map_10EC
oem_map_10E9:
    jmp mp_memory_read_record
oem_map_10EC:
    mov ch, al
oem_map_10EE:
    dec dx
oem_map_10EF:
    mov bp,oem_map_10F5
oem_map_10F2:
    jmp mp_memory_read_record
oem_map_10F5:
    mov cl, al
oem_map_10F7:
    mov bx, cx
oem_map_10F9:
    and cx, cx
oem_map_10FB:
    jne oem_map_1100
oem_map_10FD:
    jmp oem_map_11B0
oem_map_1100:
    mov dx, 0x2dd
oem_map_1103:
    mov bp,oem_map_1109
oem_map_1106:
    jmp mp_memory_read_record
oem_map_1109:
    mov cl, al
oem_map_110B:
    mov dx, 2
oem_map_110E:
    mov ax, 0x8160
oem_map_1111:
    mov bp,oem_map_1117
oem_map_1114:
    jmp mp_memory_ti_write
oem_map_1117:
    inc dh
oem_map_1119:
    dec cl
oem_map_111B:
    jne oem_map_110E
oem_map_111D:
    mov cx, bx
oem_map_111F:
    mov dx, 0x2ae
oem_map_1122:
    mov bp,oem_map_1128
oem_map_1125:
    jmp mp_memory_read_record
oem_map_1128:
    mov bh, al
oem_map_112A:
    dec dx
oem_map_112B:
    mov bp,oem_map_1131
oem_map_112E:
    jmp mp_memory_read_record
oem_map_1131:
    mov bl, al
oem_map_1133:
    or bh, 0x80
oem_map_1136:
    mov dh, bh
oem_map_1138:
    mov sp,oem_map_113E
oem_map_113B:
    jmp oem_map_2414
oem_map_113E:
    mov dx, 0x252
oem_map_1141:
    mov bp,oem_map_1147
oem_map_1144:
    jmp mp_memory_read_record
oem_map_1147:
    mov dl, al
oem_map_1149:
    mov dh, bh
oem_map_114B:
    and dh, 0x70
oem_map_114E:
    shr dh, 2
oem_map_1151:
    shl dx, 2
oem_map_1154:
    and dx, 0x73fc
oem_map_1158:
    add dx, 0x40
oem_map_115B:
    or dh, 0x80
oem_map_115E:
    mov ax, bx
oem_map_1160:
    and ah, 0x87
oem_map_1163:
    shr ebx, 0xe
oem_map_1167:
    and bx, 0xffc
oem_map_116B:
    sub bx, 4
oem_map_116E:
    and dh, 0xf7
oem_map_1171:
    mov bp,oem_map_1177
oem_map_1174:
    jmp mp_memory_ti_write
oem_map_1177:
    and ah, 7
oem_map_117A:
    and dh, 0x77
oem_map_117D:
    cmp ax, bx
oem_map_117F:
    jne oem_map_11A1
oem_map_1181:
    xor ax, ax
oem_map_1183:
    add dh, 0x10
oem_map_1186:
    test dh, 0x40
oem_map_1189:
    jne oem_map_11B0
oem_map_118B:
    mov sp,oem_map_1191
oem_map_118E:
    jmp oem_map_2414
oem_map_1191:
    shr ebx, 0xe
oem_map_1195:
    and bx, 0xffc
oem_map_1199:
    je oem_map_1183
oem_map_119B:
    sub bx, 4
oem_map_119E:
    jmp oem_map_11A4
oem_map_11A0:
    nop
oem_map_11A1:
    add ax, 4
oem_map_11A4:
    add dx, 4
oem_map_11A7:
    or ah, 0x80
oem_map_11AA:
    or dh, 0x80
oem_map_11AD:
    dec cx
oem_map_11AE:
    jne oem_map_116E
oem_map_11B0:
%ifdef MP386_MEMORY_TRACE
%include "map-capture.inc"
%endif
    mov dx, 0x2dd
oem_map_11B3:
    mov bp,oem_map_11B9
oem_map_11B6:
    jmp mp_memory_read_record
oem_map_11B9:
    mov cl, al
oem_map_11BB:
    mov dx, 2
oem_map_11BE:
    mov ax, 0x8100
oem_map_11C1:
    mov bp,oem_map_11C7
oem_map_11C4:
    jmp mp_memory_ti_write
oem_map_11C7:
    inc dh
oem_map_11C9:
    dec cl
oem_map_11CB:
    jne oem_map_11BE
oem_map_11CD:
    mov dx, 0x2b2
oem_map_11D0:
    mov bp,oem_map_11D6
oem_map_11D3:
    jmp mp_memory_read_record
oem_map_11D6:
    mov bh, al
oem_map_11D8:
    dec dx
oem_map_11D9:
    mov bp,oem_map_11DF
oem_map_11DC:
    jmp mp_memory_read_record
oem_map_11DF:
    mov bl, al
oem_map_11E1:
    or bh, 0x80
oem_map_11E4:
    mov dx, 0x24e
oem_map_11E7:
    mov bp,oem_map_11ED
oem_map_11EA:
    jmp mp_memory_read_record
oem_map_11ED:
    mov cl, al
oem_map_11EF:
    and al, al
oem_map_11F1:
    je oem_map_1253
oem_map_11F3:
    mov dh, bh
oem_map_11F5:
    mov sp,oem_map_11FB
oem_map_11F8:
    jmp oem_map_2414
oem_map_11FB:
    mov dx, 0x253
oem_map_11FE:
    mov bp,oem_map_1204
oem_map_1201:
    jmp mp_memory_read_record
oem_map_1204:
    mov dl, al
oem_map_1206:
    mov dh, bh
oem_map_1208:
    and dh, 0xf0
oem_map_120B:
    mov ax, bx
oem_map_120D:
    and ah, 0x87
oem_map_1210:
    shr ebx, 0xe
oem_map_1214:
    and bx, 0xffc
oem_map_1218:
    dec bx
oem_map_1219:
    mov bp,oem_map_121F
oem_map_121C:
    jmp mp_memory_ti_write
oem_map_121F:
    and ah, 7
oem_map_1222:
    and dh, 0x70
oem_map_1225:
    cmp ax, bx
oem_map_1227:
    jne oem_map_1247
oem_map_1229:
    xor ax, ax
oem_map_122B:
    add dh, 0x10
oem_map_122E:
    test dh, 0x40
oem_map_1231:
    jne oem_map_1253
oem_map_1233:
    mov sp,oem_map_1239
oem_map_1236:
    jmp oem_map_2414
oem_map_1239:
    shr ebx, 0xe
oem_map_123D:
    and bx, 0xffc
oem_map_1241:
    je oem_map_122B
oem_map_1243:
    dec bx
oem_map_1244:
    jmp oem_map_1248
oem_map_1246:
    nop
oem_map_1247:
    inc ax
oem_map_1248:
    inc dx
oem_map_1249:
    or ah, 0x80
oem_map_124C:
    or dh, 0x80
oem_map_124F:
    dec cl
oem_map_1251:
    jne oem_map_1219
oem_map_1253:
    mov dx, 0x2b4
oem_map_1256:
    mov bp,oem_map_125C
oem_map_1259:
    jmp mp_memory_read_record
oem_map_125C:
    mov bh, al
oem_map_125E:
    dec dx
oem_map_125F:
    mov bp,oem_map_1265
oem_map_1262:
    jmp mp_memory_read_record
oem_map_1265:
    mov bl, al
oem_map_1267:
    or bh, 0x80
oem_map_126A:
    mov dx, 0x24f
oem_map_126D:
    mov bp,oem_map_1273
oem_map_1270:
    jmp mp_memory_read_record
oem_map_1273:
    mov cl, al
oem_map_1275:
    and al, al
oem_map_1277:
    je oem_map_12C9
oem_map_1279:
    mov dh, bh
oem_map_127B:
    mov sp,oem_map_1281
oem_map_127E:
    jmp oem_map_2414
oem_map_1281:
    mov dl, 0x3c
oem_map_1283:
    mov dh, bh
oem_map_1285:
    and dh, 0xf0
oem_map_1288:
    mov ax, bx
oem_map_128A:
    and ah, 0x8f
oem_map_128D:
    shr ebx, 0xe
oem_map_1291:
    and bx, 0x7ffc
oem_map_1295:
    dec bx
oem_map_1296:
    mov bp,oem_map_129C
oem_map_1299:
    jmp mp_memory_ti_write
oem_map_129C:
    and ah, 0x7f
oem_map_129F:
    and dh, 0x7f
oem_map_12A2:
    cmp ax, bx
oem_map_12A4:
    jne oem_map_12BD
oem_map_12A6:
    xor ax, ax
oem_map_12A8:
    add dh, 0x10
oem_map_12AB:
    mov sp,oem_map_12B1
oem_map_12AE:
    jmp oem_map_2414
oem_map_12B1:
    shr ebx, 0xe
oem_map_12B5:
    and bx, 0x7ffc
oem_map_12B9:
    dec bx
oem_map_12BA:
    jmp oem_map_12BE
oem_map_12BC:
    nop
oem_map_12BD:
    inc ax
oem_map_12BE:
    inc dx
oem_map_12BF:
    or ah, 0x80
oem_map_12C2:
    or dh, 0x80
oem_map_12C5:
    dec cl
oem_map_12C7:
    jne oem_map_1296
oem_map_12C9:
    mov dx, 0x2dd
oem_map_12CC:
    mov bp,oem_map_12D2
oem_map_12CF:
    jmp mp_memory_read_record
oem_map_12D2:
    mov cl, al
oem_map_12D4:
    mov bx, 2
oem_map_12D7:
    mov dx, 0x29e
oem_map_12DA:
    mov bp,oem_map_12E0
oem_map_12DD:
    jmp mp_memory_read_record
oem_map_12E0:
    mov ah, al
oem_map_12E2:
    dec dx
oem_map_12E3:
    mov bp,oem_map_12E9
oem_map_12E6:
    jmp mp_memory_read_record
oem_map_12E9:
    xchg dx, bx
oem_map_12EB:
    mov bp,oem_map_12F1
oem_map_12EE:
    jmp mp_memory_ti_write
oem_map_12F1:
    inc dh
oem_map_12F3:
    xchg dx, bx
oem_map_12F5:
    add dx, 3
oem_map_12F8:
    dec cl
oem_map_12FA:
    jne oem_map_12DA
oem_map_12FC:
    jmp mp_memory_mapped
oem_map_2414:
    shl eax, 0x10
oem_map_2418:
    shl ecx, 0x10
oem_map_241C:
    mov ch, dh
oem_map_241E:
    shl edx, 0x10
oem_map_2422:
    mov dx, 0x242
oem_map_2425:
    shr cx, 0xb
oem_map_2428:
    and cx, 0xe
oem_map_242B:
    add dx, cx
oem_map_242D:
    mov bp,oem_map_2433
oem_map_2430:
    jmp mp_memory_read_record
oem_map_2433:
    mov cl, al
oem_map_2435:
    inc dx
oem_map_2436:
    mov bp,oem_map_243C
oem_map_2439:
    jmp mp_memory_read_record
oem_map_243C:
    mov ch, al
oem_map_243E:
    xchg bx, cx
oem_map_2440:
    shl ebx, 0x10
oem_map_2444:
    xchg bx, cx
oem_map_2446:
    shr edx, 0x10
oem_map_244A:
    shr ecx, 0x10
oem_map_244E:
    shr eax, 0x10
oem_map_2452:
    jmp sp

mp_memory_mapped:
mp_memory_scratch_teardown_begin:
    mov dx,2
    mov ax,0x8160
    mp_mcu_write
    mov dx,0x8000
    xor ax,ax
    mp_mcu_write
    mov dx,2
    mov ax,0x8100
    mp_mcu_write
mp_memory_scratch_teardown_end:
    mov bp,[MP_MEMORY_SCRATCH+18]
    mov sp,.cleanup_return
    jmp mp_memory_shadow_cleanup
.cleanup_return: dw .done
.done:
    xor ebx,ebx
    mov bx,[MP_MEMORY_SCRATCH+14]
    shl ebx,22
    xor esi,esi
    xor bx,bx
    xor di,di
.bank_mask:
    cmp word [MP_MEMORY_SCRATCH+di],0
    je .next_bank
    bts si,bx
.next_bank:
    add di,2
    inc bx
    cmp bx,6
    jb .bank_mask
    shl esi,16
    mov sp,bp
    ret

; OEM09AC/0A73 readMCU0 once and replicate its masked6/7 fields.
; Adaptation: generated maps never shadowoptionROMs; all30..37 entries areclear,
; avoiding the original conditional30/31 retain exception for a preexistingROMmap.
mp_memory_shadow_cleanup:
    mov dx,7
    mp_mcu_read
    and ax,0x00FF
    mov bx,ax
    xor si,si
.clear_controller:
    mov dx,si
    mov dl,7
    mov ax,bx
    mp_mcu_write
    mov dx,si
    mov dl,2
    mov ax,0x8100
    mp_mcu_write
    mov dx,si
    shl dx,4
    or dh,0x80
    mov dl,0x30
    mov cx,8
.clear_rom_maps:
    xor ax,ax
    mp_mcu_write
    inc dx
    loop .clear_rom_maps
    add si,0x0100
    mov ax,si
    shr ax,8
    cmp ax,[MP_MEMORY_SCRATCH+12]
    jb .clear_controller
    mov dx,6
    mp_mcu_read
    and ax,0x000F
    mov bx,ax
    xor si,si
.clear_six:
    mov dx,si
    mov dl,6
    mov ax,bx
    mp_mcu_write
    add si,0x0100
    mov ax,si
    shr ax,8
    cmp ax,[MP_MEMORY_SCRATCH+12]
    jb .clear_six
    ret

tiger_warm:
    mov bp,sp
    mov sp,.atu_return
    jmp mitsubishi_atu_initialize
.atu_return: dw .copy_inventory
.copy_inventory:
    xor ax,ax
    mov ds,ax
    mov ax,es
    cmp ax,STATE_SEG
    jne .cleanup
    xor di,di
.copy:
    mov ax,[es:HW_BANK_COUNTS+di]
    mov [MP_MEMORY_SCRATCH+di],ax
    add di,2
    cmp di,12
    jb .copy
    mov ax,[es:HW_MCU_COUNT]
    mov [MP_MEMORY_SCRATCH+12],ax
.cleanup:
    mov sp,.cleaned
    jmp mp_memory_shadow_cleanup
.cleaned: dw .done
.done:
    mov sp,bp
    ret
mp_memory_failed:
    jmp hard_halt
