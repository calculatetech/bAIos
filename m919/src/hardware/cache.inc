; UMC HB50/51 geometry and policy; HB5A.40 exposes SRAM for the shared test.
%include "pc/cache-test.inc"
%macro cache_write 2
    mov eax,0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11) | ((%1) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC + ((%1) & 3)
    mov al,%2
    out dx,al
%endmacro
%macro cache_read 1
    mov eax,0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11) | ((%1) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC + ((%1) & 3)
    in al,dx
%endmacro
; 8810AIO 9D49/9DA0 end each access by clearing CF8's enable bit.
; AL is the result; callers pass write data in CL or BH, never AL/AH.
%macro cache_reference_read 1
    cache_read %1
    mov ah,%1
    xchg al,ah
    ror eax,16
    and ax,0x7FFF
    ror eax,16
    mov dx,0xCF8
    out dx,eax
    mov al,ah
%endmacro
%macro cache_reference_write 2
    mov eax,0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11) | ((%1) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC + ((%1) & 3)
    mov al,%2
    out dx,al
    mov ah,al
    mov al,%1
    ror eax,16
    and ax,0x7FFF
    ror eax,16
    mov dx,0xCF8
    out dx,eax
%endmacro
; Phoenix 8810AIO F000:9B6A: ascending dwords, excluding the VGA/ROM hole.
; Inline the jump-based helper so the first two fills cannot touch the stack.
%macro cache_reference_fill 0
    cache_reference_read 0x50
    and al,7
    xor ebp,ebp
    cmp al,5
    jb %%low
    mov ebp,2
    je %%low
    mov ebp,4
%%low:
    xor esi,esi
    mov ecx,0x28000
    es a32 rep lodsd
    mov ecx,ebp
    test ecx,ecx
    jz %%done
    mov esi,0x100000
    shl ecx,18
    es a32 rep lodsd
%%done:
%endmacro
; Parity seeding needs flat data, without changing the code mapping.
%macro cache_data_enter 0
    push gs
    sub sp,6
    mov si,sp
    sgdt [ss:si]
    lgdt [cs:ram_gdtr]
    in al,0x92
    push ax
    and al,0xFE
    or al,2
    out 0x92,al
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp 0x08:%%protected
%%protected:
    mov ax,0x10
    mov gs,ax
    mov eax,cr0
    and al,0xFE
    mov cr0,eax
    jmp CFG_ROM_CODE_SEGMENT:%%real
%%real:
%endmacro
%macro cache_data_leave 0
    pop ax
    and al,0xFE
    out 0x92,al
    mov si,sp
    o32 lgdt [ss:si]
    add sp,6
    pop gs
%endmacro
cache_initialize:
    mov byte [fs:HW_CACHE_CODE],0
    mov byte [fs:HW_CACHE_MAP],0
    mov dword [fs:HW_CACHE_BYTES],0
    mov byte [fs:HW_CACHE_FLAGS],0
    mov byte [fs:HW_CACHE_STAGE],0
    ret
cache_qualify:
    pushad
    ; Candidate encodings are documented possibilities, never detected facts.
    mov byte [fs:HW_CACHE_CODE],5
    mov byte [fs:HW_CACHE_MAP],5
    mov dword [fs:HW_CACHE_BYTES],0x100000
    mov byte [fs:HW_CACHE_STAGE],1
.probe:
    xor edi,edi
    call cache_run
    test byte [fs:HW_CACHE_FLAGS],2
    jz .ordinary
    test byte [fs:HW_CACHE_FLAGS],8
    jz .done
    test byte [fs:HW_CACHE_MAP],8
    jnz .second
    or byte [fs:HW_CACHE_MAP],8
    jmp .probe
.second:
    dec byte [fs:HW_CACHE_CODE]
    mov al,[fs:HW_CACHE_CODE]
    mov [fs:HW_CACHE_MAP],al
    shr dword [fs:HW_CACHE_BYTES],1
    test al,al
    jnz .probe
    mov dword [fs:HW_CACHE_BYTES],0
    jmp .done
.ordinary:
    ; Raw SRAM geometry alone does not qualify tags or normal cache traffic.
    test byte [fs:C_CHIP+3],0x40
    jz .test
    call cache_reference_span_supported
    jnc .test
    mov ecx,eax
    add ecx,1024
    shl ecx,10
    mov eax,[fs:S_EXTENDED_KIB32]
    add eax,1024
    shl eax,10
    mov byte [fs:HW_CACHE_STAGE],3
    xor edi,edi
    jmp .state_failed
.test:
    mov byte [fs:HW_CACHE_STAGE],2
    mov bl,[fs:HW_CACHE_CODE]
    mov bh,[fs:HW_CACHE_MAP]
    mov edx,[fs:HW_CACHE_BYTES]
    mov edi,2
    call cache_run
    ; WB copy-back must not erase the detected geometry in live firmware RAM.
    mov edi,HW_CACHE_CODE
    movzx ecx,bl
    movzx eax,byte [fs:di]
    cmp eax,ecx
    jne .state_failed
    inc di
    movzx ecx,bh
    movzx eax,byte [fs:di]
    cmp eax,ecx
    jne .state_failed
    mov di,HW_CACHE_BYTES
    mov ecx,edx
    mov eax,[fs:di]
    cmp eax,ecx
    je .done
.state_failed:
    test edi,edi
    jz .failure
    add edi,CFG_PLATFORM_STATE_SEG << 4
.failure:
    mov byte [fs:HW_CACHE_FLAGS],2
    mov [fs:HW_CACHE_FAILURE_ADDRESS],edi
    mov [fs:HW_CACHE_FAILURE_EXPECTED],ecx
    mov [fs:HW_CACHE_FAILURE_OBSERVED],eax
.done:
    popad
    ret
cache_save_failure:
    mov eax,[fs:HW_CACHE_FAILURE_ADDRESS]
    mov [fs:di],eax
    mov eax,[fs:HW_CACHE_FAILURE_EXPECTED]
    mov [fs:di+4],eax
    mov eax,[fs:HW_CACHE_FAILURE_OBSERVED]
    mov [fs:di+8],eax
    ret
cache_enable:
    and byte [fs:HW_CACHE_FLAGS],0xFB
    cmp byte [fs:C_CHIP+2],0
    jne .done
    test byte [fs:HW_CACHE_FLAGS],1
    jz .done
    call cache_reference_span_supported
    jc .done
.activate:
    mov edi,1
    call cache_run
.done:
    ret

; CF=insufficient RAM, EAX=required extended KiB. No truncated tag fill.
cache_reference_span_supported:
    xor eax,eax
    cmp byte [fs:HW_CACHE_CODE],5
    jb .enough
    mov eax,2048
    je .span
    mov eax,4096
.span:
    cmp [fs:S_EXTENDED_KIB32],eax
    ret
.enough:
    clc
    ret

; EDI=0 direct SRAM, 1 activate, 2 ordinary check. Code stays at FFFF0000+IP.
cache_run:
    pushf
    cli
    cld
    pushad
    push ds
    push es
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    mov al,0x80
    out 0x70,al
    cache_read 0x5A
    push ax
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    cache_read 0x55
    push ax
    and al,0x7F
    mov cl,al
    cache_write 0x55,cl
    cache_read 0x51
    and al,0x0E
    or al,[fs:C_CHIP]
    or al,1
    call chipset_l1_protocol
    mov bl,al
    mov bh,[fs:HW_CACHE_MAP]
    or bh,[fs:C_CHIP+3]
    and bh,0xBF
    or bh,0x80
    mov esi,[fs:HW_CACHE_BYTES]
    shr esi,16
    test edi,edi
    jz .tuple
    ; The reference initializes and retains the 7-tag-plus-dirty format.
    and bl,0xFE
    test byte [fs:C_CHIP+3],0x40
    jz .tuple
    or bh,0x40
.tuple:
    movzx ebx,bx
    imul ebx,0x10001
    push gs
    sub sp,6
    mov si,sp
    sgdt [ss:si]
    lgdt [cs:ram_gdtr]
    ; SI was the descriptor scratch pointer; recover the bounded test count.
    mov esi,[fs:HW_CACHE_BYTES]
    shr esi,16
    cmp edi,1
    jne .direct_mode
    or esi,0x80000000
    jmp .count
.direct_mode:
    test edi,edi
    jnz .count
    or esi,0x40000000
.count:
    cmp edi,2
    jne .a20
    mov eax,[fs:S_EXTENDED_KIB32]
    add eax,1024
    shr eax,6
    shl eax,16
    or edi,eax
.a20:
    in al,0x92
    push ax
    and al,0xFE
    or al,2
    out 0x92,al
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp 0x08:.protected
.protected:
    mov ax,0x10
    mov ds,ax
    mov es,ax
    mov gs,ax
    jmp 0x18:.high
.high:
    cache_write 0x51,bl
    test esi,esi
    js .reference_activate
    test esi,0x40000000
    jnz .direct
    test bh,0x40
    jnz .reference_activate
.direct:
    cache_write 0x50,bh
    ; The manual identifies INVD as the external invalidation signal.
    invd
    test esi,0x40000000
    jnz .sram
    jmp .ordinary
.reference_activate:
    ; 8810AIO 9AC5-9B47: CPU normalization, WT fill, enable, fill,
    ; final policy, fill. All inputs were captured before this stack-free window.
    mov al,0x8D
    out 0x70,al
    mov eax,cr0
    or eax,0x40000000
    mov cr0,eax
    wbinvd
    mov eax,cr0
    and eax,0x9FFFFFFF
    mov cr0,eax
    wbinvd
    cache_reference_read 0x50
    and al,0xBF
    mov cl,al
    cache_reference_write 0x50,cl
    cache_reference_fill
    cache_reference_read 0x50
    or al,0x80
    mov cl,al
    cache_reference_write 0x50,cl
    cache_reference_fill
    test bh,0x40
    jz .reference_final
    cache_reference_read 0x50
    or al,0x40
    mov cl,al
    cache_reference_write 0x50,cl
.reference_final:
    cache_reference_fill
    cmp di,1
    je .reference_enabled
    ; Qualification needs the same clean tags before any WB writes. Disable
    ; L1 afterward so it cannot hide an external SRAM or copy-back failure.
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    movzx ecx,bh
    and ecx,7
    mov esi,0x8000
    shl esi,cl
    shr esi,16
    jmp .ordinary
.reference_enabled:
    ; The caller owns shadow/cacheability and the selected final L1 policy.
    ; Do not invalidate the freshly initialized L2 before returning to it.
    mov ebp,2
    shr ebx,16
    jmp .leave_high
.sram:
    ; Tentative geometry only; full data qualification uses ordinary WT.
    ; No stack, firmware data or I/O in the forced-hit window.
    cache_read 0x5A
    or al,0x40
    mov cl,al
    cache_write 0x5A,cl
    mov edx,esi
    cache_sram_addresses .geometry_failed,0x100000
    xor ebp,ebp
    jmp .finish
.ordinary:
    ; Check the selected policy using free extended POST RAM.
    mov ebp,edi             ; Upper half carries the detected RAM end.
    mov ecx,esi
    shl ecx,12
    mov edi,0x100000
.fill:
    mov eax,[es:edi]
    add edi,16
    loop .fill
    mov edx,esi
    cache_sram_patterns .failed,0x100000
    shl esi,16
    cache_tag_patterns .tag_failed
    shr esi,16
    test ebx,0x40000000
    jz .passed
    ; A WB data pass alone can hide broken copy-back. Check RAM with L2 off.
    mov edi,0x100000
    mov dword [es:edi],0x6B19D4A2
    mov ecx,esi
    shl ecx,16
    lea edi,[ecx+0x100000-4]
    mov dword [es:edi],0x94E62B5D
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    ; Change only L2 enable; retain the tested WB geometry and tag format.
    cache_read 0x50
    and al,0x7F
    out dx,al
    mov edi,0x100000
    mov ecx,0x6B19D4A2
    mov eax,[es:edi]
    cmp eax,ecx
    jne .copy_failed
    mov ecx,esi
    shl ecx,16
    lea edi,[ecx+0x100000-4]
    mov ecx,0x94E62B5D
    mov eax,[es:edi]
    cmp eax,ecx
    jne .copy_failed
.passed:
    xor ebp,ebp
    jmp .finish
.copy_failed:
    mov esi,eax
    mov ebp,1
    jmp .finish
.failed:
    movzx esi,ax
    movzx ecx,bx
    mov ebp,1
    jmp .finish
.tag_failed:
    sub edi,4
    mov ecx,eax
    mov esi,[es:edi]
    mov ebp,4
    jmp .finish
.geometry_failed:
    movzx esi,ax
    movzx ecx,bx
    mov ebp,3
    jmp .finish
.finish:
    ; End forced hits before touching the stack or private state again.
    cache_read 0x5A
    and al,0xBF
    out dx,al
    shr ebx,16
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    cmp ebp,2
    je .leave_high
    and bh,0x7F
    cache_write 0x50,bh
.leave_high:
    jmp 0x08:.low
.low:
    mov eax,cr0
    and al,0xFE
    mov cr0,eax
    jmp CFG_ROM_CODE_SEGMENT:.real
.real:
    cmp ebp,2
    je .enabled
    test ebp,ebp
    jnz .bad
    mov byte [fs:HW_CACHE_FLAGS],1
    jmp .result
.bad:
    mov byte [fs:HW_CACHE_FLAGS],2
    cmp ebp,4
    jne .geometry_status
    mov byte [fs:HW_CACHE_STAGE],4
.geometry_status:
    cmp ebp,3
    jne .failure_tuple
    or byte [fs:HW_CACHE_FLAGS],8
.failure_tuple:
    mov [fs:HW_CACHE_FAILURE_ADDRESS],edi
    mov [fs:HW_CACHE_FAILURE_EXPECTED],ecx
    mov [fs:HW_CACHE_FAILURE_OBSERVED],esi
    jmp .result
.enabled:
    or byte [fs:HW_CACHE_FLAGS],4
.result:
    cache_data_leave
    pop cx
    cache_write 0x55,cl
    pop cx
    cache_write 0x5A,cl
    xor al,al
    out 0x70,al
    pop ax
    out 0x61,al
    pop es
    pop ds
    popad
    popf
    ret
cache_recovery:
    call post_error_tone
    mov di,C_CHIP
    call chipset_safe_defaults
    call chipset_apply
    call settings_recovery_publish
    mov ax,0x5A36
    call rtc_write
    call post_message_cursor
    mov si,cache_first_line
    cmp byte [fs:HW_CACHE_STAGE],2
    jne .span_notice
    mov si,cache_second_line
    jmp .notice
.span_notice:
    cmp byte [fs:HW_CACHE_STAGE],4
    jne .span_status
    mov si,cache_tag_line
    jmp .notice
.span_status:
    cmp byte [fs:HW_CACHE_STAGE],3
    jne .notice
    mov si,cache_span_line
.notice:
    call print_string
    mov di,HW_CACHE_TRIAL_FIRST
    call cache_save_failure
    mov si,HW_CACHE_TRIAL_FIRST
    call cache_print_failure
    mov si,cache_check_retry
    call print_string
    call post_notice_wait
    call chipset_recovery_ack
    jmp controlled_defaults_restart
cache_print_failure:
    mov cx,3
.field:
    mov eax,[fs:si]
    pushad
    mov edx,eax
    mov cx,8
.digit:
    rol edx,4
    mov al,dl
    and al,15
    add al,'0'
    cmp al,'9'
    jbe .write
    add al,'A'-'9'-1
.write:
    mov ah,0x0E
    mov bx,7
    pushad
    int 0x10
    popad
    loop .digit
    mov ax,0x0E20
    int 0x10
    popad
    add si,4
    loop .field
    ret
cache_first_line db 'L2 geometry address / expected / read: ',0
cache_second_line db 'L2 normal address / expected / read: ',0
cache_tag_line db 'L2 tags address / expected / read: ',0
cache_span_line db 'L2 init RAM base / required end / available end: ',0
cache_check_retry db ' Press a key.',0
