; Discovery uses forced-hit bytes with L1 off; ordinary tests use L1 on.
; No RAM stack/state is touched while an unqualified cache map is active.
%macro cache_probe_settle 0
    ; AMI uses two next-instruction JCXZ delays for PCI and SRAM writes.
    jcxz %%next
%%next:
    jcxz %%done
%%done:
%endmacro
%macro cache_write 2
    mov eax,0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11) | ((%1) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    cache_probe_settle
    mov dx,0xCFC + ((%1) & 3)
    mov al,%2
    out dx,al
%endmacro
%macro cache_read 1
    mov eax,0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11) | ((%1) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    cache_probe_settle
    mov dx,0xCFC + ((%1) & 3)
    in al,dx
%endmacro
%macro cache_force_off 0
    and bl,0xBF
    cache_write 0x5A,bl
    invd
    cache_write 0x50,bh
%endmacro
%macro cache_force_on 0
    cache_write 0x50,bh
    or bl,0x40
    cache_write 0x5A,bl
%endmacro
%macro cache_diagnostic_read 0
    xor esi,esi
    mov ecx,0x8000
    cld
    gs a32 rep lodsw
%endmacro
%macro cache_ami_diagnostic 0
    ; AMI FB32..FC18: complete readback gate; 5A.80/5B meaning is unproved.
    cache_write 0x50,bh
    cache_write 0x51,1
    mov eax,cr0
    and eax,0x9FFFFFFF
    mov cr0,eax
    wbinvd
    cache_diagnostic_read
    cache_read 0x5A
    or al,0x80
    mov bl,al
    cache_write 0x5A,bl
    cache_diagnostic_read
    cache_diagnostic_read
    cache_write 0x5B,0x55
    cache_diagnostic_read
    cache_diagnostic_read
    cache_read 0x5B
    cache_diagnostic_read
    cache_diagnostic_read
    cache_write 0x5B,0x55
    cache_diagnostic_read
    cache_diagnostic_read
    cache_read 0x5B
    movzx edi,al
    cache_read 0x5A
    and al,0x7F
    mov bl,al
    cache_write 0x5A,bl
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    wbinvd
    cmp edi,0x55
    jne .absent_forced
%endmacro
%macro cache_normal_drain 0
    mov cl,bh
    and cl,7
    mov eax,0x8000
    shl eax,cl
    mov ecx,eax
    shr ecx,2
    mov esi,0x100000
    gs a32 rep lodsd
%endmacro
%macro cache_prepare_wt 0
    test bh,0x40
    jz %%done
    mov cl,bh
    and cl,0x3F
    cache_write 0x50,cl
    cache_read 0x51
    mov cl,al
    or cl,1
    cache_write 0x51,cl
%%done:
%endmacro
%macro cache_select_wb 0
    test bh,0x40
    jz %%done
    ; AMI switches mode only after WT priming has established clean tags.
    cache_read 0x51
    mov cl,al
    and cl,0xFE
    cache_write 0x51,cl
    cache_write 0x50,bh
    cache_normal_drain
%%done:
%endmacro
%macro cache_ordinary_on 0
    ; AMI enables L1 and drains the capacity before and after WT enable.
    cache_prepare_wt
    mov eax,cr0
    and eax,0x9FFFFFFF
    mov cr0,eax
    wbinvd
    cache_normal_drain
    or bh,0x80
    mov cl,bh
    and cl,0xBF
    cache_write 0x50,cl
    cache_normal_drain
    test bh,0x40
    jz %%done
    wbinvd
    cache_select_wb
%%done:
%endmacro
%macro cache_pattern 1
    mov edi,0x100000
%ifidni %1,address
    mov eax,edi
%elifidni %1,inverse
    mov eax,edi
    not eax
%else
    mov eax,%1
%endif
%%fill:
%assign cache_fill_lane 0
%rep 4
    mov [gs:edi+cache_fill_lane],eax
%ifidni %1,address
    add eax,4
%elifidni %1,inverse
    sub eax,4
%endif
%assign cache_fill_lane cache_fill_lane+4
%endrep
    add edi,16
    cmp edi,ebp
    jb %%fill
    or bl,0x80
    mov edi,ebp
%%compare:
%rep 4
    sub edi,4
%ifidni %1,address
    mov eax,edi
%elifidni %1,inverse
    mov eax,edi
    not eax
%else
    mov eax,%1
%endif
    mov esi,[gs:edi]
    cmp esi,eax
    jne .pattern_failed
%endrep
    cmp edi,0x100000
    ja %%compare
    and bl,0x7F
    cache_normal_drain
    mov edi,ebp
%%recompare:
%rep 4
    sub edi,4
%ifidni %1,address
    mov eax,edi
%elifidni %1,inverse
    mov eax,edi
    not eax
%else
    mov eax,%1
%endif
    mov esi,[gs:edi]
    cmp esi,eax
    jne .pattern_failed
%endrep
    cmp edi,0x100000
    ja %%recompare
%endmacro
%macro cache_data_enter 0
    ; A real-mode POP GS after VGA loses startup's hidden flat descriptor.
    push gs
    sub sp,6
    mov si,sp
    sgdt [ss:si]
    lgdt [cs:ram_gdtr]
    ; AMI establishes A20 for cache tests; use the donor RAM gate hold.
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
    pushf
    cli
    pushad
    push ds
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    cache_write 0x50,0
    cache_read 0x5A
    and al,0xBF
    mov bl,al
    mov bh,6
    mov byte [fs:HW_CACHE_CODE],0
    mov byte [fs:HW_CACHE_FLAGS],0
    ; A stored-only/absent force-hit implementation must not damage DRAM.
    xor si,si
.save_samples:
    mov edi,[cs:cache_samples+si]
    mov eax,[gs:edi]
    mov [fs:HW_CACHE_SAMPLES+si],eax
    add si,4
    cmp si,32
    jb .save_samples
    cache_ami_diagnostic
    cache_force_on
    mov byte [gs:0],0x55
    cache_probe_settle
    cmp byte [gs:0],0x55
    jne .absent_forced
    mov byte [gs:0],0xAA
    cache_probe_settle
    cmp byte [gs:0],0xAA
    jne .absent_forced
    ; AMI FCB4..FD03: byte markers, then select the discovered capacity.
    mov edi,0x200000
    mov ecx,6
.capacity:
    mov [gs:edi],cl
    cache_probe_settle
    shr edi,1
    dec ecx
    jnz .capacity
    movzx esi,byte [gs:0]
    cmp esi,1
    jb .absent_forced
    cmp esi,5
    ja .absent_forced
    mov ecx,esi
    mov bh,cl
    cache_write 0x50,bh
    ; AMI FD24..FD52 probes byte banks only under the discovered size.
    mov byte [gs:0],0x55
    cache_probe_settle
    mov byte [gs:4],0xAA
    cache_probe_settle
    cmp byte [gs:0],0x55
    je .bank_ready
    cmp byte [gs:0],0xAA
    jne .absent_forced
    or bh,8
    cache_write 0x50,bh
.bank_ready:
    jmp .discovery_cleanup
.absent_forced:
    xor esi,esi
    xor bh,bh
.discovery_cleanup:
    cache_force_off
    xor di,di
.restore_samples:
    mov ecx,[cs:cache_samples+di]
    mov eax,[fs:HW_CACHE_SAMPLES+di]
    mov [gs:ecx],eax
    add di,4
    cmp di,32
    jb .restore_samples
    mov eax,esi
    mov [fs:HW_CACHE_CODE],al
    mov [fs:HW_CACHE_MAP],bh
    test esi,esi
    jz .done
    mov ecx,esi
    dec ecx
    mov ebp,0x10000
    shl ebp,cl
    mov [fs:HW_CACHE_BYTES],ebp
.done:
    pop ax
    out 0x61,al
    pop ds
    popad
    popf
    ret

cache_qualify:
    cmp byte [fs:HW_CACHE_CODE],0
    je .absent
    pushf
    cli
    pushad
    push ds
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    ; Late POST has shadowed ROM; execute the unqualified map externally.
    cache_read 0x55
    push ax
    and al,0x7F
    mov cl,al
    cache_write 0x55,cl
    cache_data_enter
    mov bh,[fs:HW_CACHE_MAP]
    or bh,[fs:C_CHIP+3]
    cache_read 0x5A
    and al,0xBF
    mov bl,al
    mov byte [fs:HW_CACHE_FAILURE_STAGE],0
    mov dword [fs:HW_CACHE_FAILURE_ADDRESS],0
    mov dword [fs:HW_CACHE_FAILURE_EXPECTED],0
    mov dword [fs:HW_CACHE_FAILURE_OBSERVED],0
    mov ebp,[fs:HW_CACHE_BYTES]
    add ebp,0x100000
    mov eax,[fs:S_EXTENDED_KIB32]
    add eax,1024
    shl eax,10
    cmp eax,ebp
    jb .scratch_unavailable
    ; Free extended POST RAM holds the full-span AMI address-pattern test.
    cache_ordinary_on
.patterns:
    mov bl,1
    cache_pattern 0x55AA55AA
    mov bl,2
    cache_pattern 0xAA55AA55
    mov bl,3
    cache_pattern address
    mov bl,4
    cache_pattern inverse
    xor bl,bl
    jmp .pattern_off
.pattern_failed:
    mov ecx,eax
    ; Keep the failing hardware tuple in registers until the cache is disabled.
    cache_read 0x50
    in eax,dx
    shl eax,16
    and ebx,0xFFFF
    or ebx,eax
.pattern_off:
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    and bh,0x7F
    cache_write 0x50,bh
    test bl,bl
    jz .clear_start
    mov [fs:HW_CACHE_FAILURE_EXPECTED],ecx
    mov [fs:HW_CACHE_FAILURE_OBSERVED],esi
    mov eax,ebx
    shr eax,16
    mov [fs:HW_CACHE_FAILURE_REGISTERS],ax
    mov eax,[gs:edi]
    mov [fs:HW_CACHE_FAILURE_RAM],eax
    mov eax,ebx
    and al,0x7F
    mov [fs:HW_CACHE_FAILURE_STAGE],al
    mov [fs:HW_CACHE_FAILURE_ADDRESS],edi
.clear_start:
    ; Discard patterns in free POST workspace, outside all live firmware RAM.
    xor eax,eax
    mov edi,0x100000
.clear:
    mov [gs:edi],eax
    mov [gs:edi+4],eax
    mov [gs:edi+8],eax
    mov [gs:edi+12],eax
    add edi,16
    cmp edi,ebp
    jb .clear
    test bl,bl
    jnz .coherence_failed
    ; Ordinary WT tests exercise every available tag-address line. Scratch
    ; data is backed up and restored with the map disabled on every path.
    mov ebp,[fs:HW_CACHE_BYTES]
.coherence:
    lea edi,[ebp+0x8000]
    mov eax,[gs:dword 0x8000]
    mov [fs:HW_CACHE_SAMPLES],eax
    mov eax,[gs:edi]
    mov [fs:HW_CACHE_SAMPLES+4],eax
    cache_ordinary_on
    mov dword [gs:dword 0x8000],0x55AA55AA
    mov dword [gs:edi],0xAA55AA55
    cache_normal_drain
    mov eax,[gs:dword 0x8000]
    cmp eax,0x55AA55AA
    jne .coherence_low_bad
    mov dword [gs:dword 0x8000],0xAA55AA55
    cache_normal_drain
    mov eax,[gs:edi]
    cmp eax,0xAA55AA55
    jne .coherence_bad
    mov eax,[gs:dword 0x8000]
    cmp eax,0xAA55AA55
    jne .coherence_low_bad
    mov dword [gs:edi],0x55AA55AA
    cache_normal_drain
    mov eax,[gs:dword 0x8000]
    cmp eax,0xAA55AA55
    jne .coherence_low_bad
    mov eax,[gs:edi]
    cmp eax,0x55AA55AA
    jne .coherence_bad
    xor esi,esi
    jmp .coherence_cleanup
.coherence_low_bad:
    mov ecx,0x8000
    jmp .coherence_mark
.coherence_bad:
    mov ecx,edi
.coherence_mark:
    mov esi,5
.coherence_cleanup:
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    and bh,0x7F
    cache_write 0x50,bh
    invd
    test esi,esi
    jnz .coherence_restore
.dram_check:
    cmp dword [gs:dword 0x8000],0xAA55AA55
    jne .dram_low_bad
    cmp dword [gs:edi],0x55AA55AA
    je .coherence_restore
    jmp .dram_bad
.dram_low_bad:
    mov ecx,0x8000
    jmp .dram_mark
.dram_bad:
    mov ecx,edi
.dram_mark:
    mov esi,6
.coherence_restore:
    test esi,esi
    jz .restore_witnesses
    mov [fs:HW_CACHE_FAILURE_ADDRESS],ecx
    mov eax,esi
    mov [fs:HW_CACHE_FAILURE_STAGE],al
.restore_witnesses:
    mov eax,[fs:HW_CACHE_SAMPLES]
    mov [gs:dword 0x8000],eax
    mov eax,[fs:HW_CACHE_SAMPLES+4]
    mov [gs:edi],eax
    test esi,esi
    jnz .coherence_failed
    shl ebp,1
    mov eax,[fs:S_EXTENDED_KIB32]
    add eax,1024
    shl eax,10
    sub eax,0x8004
    cmp ebp,eax
    jb .coherence
    mov byte [fs:HW_CACHE_FLAGS],1
    jmp .done
.scratch_unavailable:
    mov byte [fs:HW_CACHE_FAILURE_STAGE],7
.coherence_failed:
    mov byte [fs:HW_CACHE_FLAGS],2
.done:
    cache_data_leave
    pop cx
    cache_write 0x55,cl
    pop ax
    out 0x61,al
    pop ds
    popad
    popf
.absent:
    ret

cache_supported_extent:
    push si
    mov si,C_CHIP
    call cache_record_supported_extent
    pop si
    ret
cache_record_supported_extent:
    pushad
    ; AMI pairs WT with eight tag bits, WB with seven plus a dirty bit.
    mov eax,[fs:HW_CACHE_BYTES]
    mov cl,8
    test byte [fs:si+3],0x40
    jz .tag_limit
    dec cl
.tag_limit:
    shl eax,cl
    mov ecx,[fs:S_EXTENDED_KIB32]
    add ecx,1024
    shl ecx,10
    cmp ecx,eax
    popad
    ja .bad
    clc
    ret
.bad:
    stc
    ret
cache_enable:
    cmp byte [fs:C_CHIP+2],0
    jne .off
    test byte [fs:HW_CACHE_FLAGS],2
    jnz cache_recovery
    test byte [fs:HW_CACHE_FLAGS],1
    jz .off
    call cache_supported_extent
    jc .off
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    cache_data_enter
    mov esi,[fs:HW_CACHE_BYTES]
    add esi,0x100000
    mov bh,[fs:HW_CACHE_MAP]
    and bh,0x3F
    or bh,[fs:C_CHIP+3]
    cache_prepare_wt
    ; AMI 29A2..29CE: CPU on, flush, capacity drain, WT on, drain again.
    mov eax,cr0
    and eax,0x9FFFFFFF
    mov cr0,eax
    wbinvd
    mov edi,0x100000
.prime_before:
    mov eax,[gs:edi]
    add edi,4
    cmp edi,esi
    jb .prime_before
    or bh,0x80
    mov cl,bh
    and cl,0xBF
    cache_write 0x50,cl
    mov edi,0x100000
.prime_after:
    mov eax,[gs:edi]
    add edi,4
    cmp edi,esi
    jb .prime_after
    wbinvd
    cache_select_wb
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    cache_data_leave
    pop ax
    out 0x61,al
    or byte [fs:HW_CACHE_FLAGS],4
.off:
    ret

cache_recovery:
    ; D2 reloads the safe policy with L2 off, so this retry cannot requalify L2.
    call post_error_tone
    mov di,C_CHIP
    call chipset_safe_defaults
    call chipset_apply
    mov ax,0xD269
    call rtc_write
    mov ax,0x5A36
    call rtc_write
    call post_message_cursor
    mov si,cache_check_retry
    call print_string
    push ds
    push es
    push cs
    pop ds
    mov ax,0xB800
    mov es,ax
    ui_text 22,3,cache_failure_title,7
    movzx bx,byte [fs:HW_CACHE_FAILURE_STAGE]
    shl bx,1
    mov si,[cs:cache_failure_names+bx]
    mov di,22*160+15*2
    mov bh,7
    call setup_text
    ui_text 22,34,cache_failure_at,7
    mov eax,[fs:HW_CACHE_FAILURE_ADDRESS]
    mov cl,8
    mov bh,7
    mov di,22*160+37*2
    call setup_hex_number
    cmp byte [fs:HW_CACHE_FAILURE_STAGE],4
    ja .failure_done
    cmp byte [fs:HW_CACHE_FAILURE_STAGE],0
    je .failure_done
    mov di,21*160
    mov ax,0x0720
    mov cx,80
    rep stosw
    ui_text 21,3,cache_failure_expected,7
    mov eax,[fs:HW_CACHE_FAILURE_EXPECTED]
    mov cl,8
    mov bh,7
    mov di,21*160+12*2
    call setup_hex_number
    ui_text 21,24,cache_failure_read,7
    mov eax,[fs:HW_CACHE_FAILURE_OBSERVED]
    mov cl,8
    mov bh,7
    mov di,21*160+29*2
    call setup_hex_number
    ui_text 21,40,cache_failure_ram,7
    mov eax,[fs:HW_CACHE_FAILURE_RAM]
    mov cl,8
    mov di,21*160+44*2
    call setup_hex_number
    ui_text 21,54,cache_failure_reg50,7
    movzx eax,byte [fs:HW_CACHE_FAILURE_REGISTERS]
    mov cl,2
    mov di,21*160+57*2
    call setup_hex_number
    ui_text 21,61,cache_failure_reg51,7
    movzx eax,byte [fs:HW_CACHE_FAILURE_REGISTERS+1]
    mov cl,2
    mov di,21*160+64*2
    call setup_hex_number
    ui_text 21,68,cache_failure_map,7
    movzx eax,byte [fs:HW_CACHE_MAP]
    mov cl,2
    mov di,21*160+72*2
    call setup_hex_number
    mov di,22*160+49*2
    mov ax,0x0720
    mov cx,30
    rep stosw
    ui_text 22,49,cache_failure_bank,7
    xor eax,eax
    test byte [fs:HW_CACHE_MAP],8
    jz .bank_number
    mov eax,[fs:HW_CACHE_FAILURE_ADDRESS]
    shr eax,2
    and eax,1
.bank_number:
    mov cl,1
    mov di,22*160+54*2
    call setup_hex_number
    mov eax,[fs:HW_CACHE_FAILURE_EXPECTED]
    xor eax,[fs:HW_CACHE_FAILURE_OBSERVED]
    xor bp,bp
    mov bx,1
    mov cx,4
.byte_mask:
    test al,al
    jz .next_byte
    or bp,bx
.next_byte:
    shr eax,8
    shl bx,1
    loop .byte_mask
    test bp,bp
    jz .failure_done
    mov ax,bp
    dec ax
    test ax,bp
    jnz .multiple_bytes
    bsf bx,bp
    ui_text 22,55,cache_failure_byte,7
    mov al,bl
    mov cl,1
    mov di,22*160+61*2
    call setup_hex_number
    movzx bx,bl
    shl bx,1
    mov si,[cs:cache_failure_data_bits+bx]
    mov di,22*160+64*2
    mov bh,7
    call setup_text
    jmp .socket_names
.multiple_bytes:
    ui_text 22,55,cache_failure_multiple_bytes,7
    xor dx,dx
    mov di,22*160+62*2
.byte_number:
    bt bp,dx
    jnc .skip_byte
    mov ax,dx
    mov cl,1
    call setup_hex_number
    add di,4
.skip_byte:
    inc dx
    cmp dx,4
    jb .byte_number
.socket_names:
    xor bx,bx
    test byte [fs:HW_CACHE_MAP],8
    jz .socket_number
    mov eax,[fs:HW_CACHE_FAILURE_ADDRESS]
    shr eax,2
    and eax,1
    mov bx,ax
.socket_number:
    shl bx,1
    mov si,[cs:cache_failure_socket_names+bx]
    mov di,22*160+71*2
    mov bh,7
    call setup_text
.failure_done:
    pop es
    xor ax,ax
    mov ds,ax
    mov byte [fs:S_SETUP_REQUEST],0
    call post_notice_wait
    pop ds
    call chipset_recovery_ack
    jmp controlled_defaults_restart

cache_failure_bank db 'Bank ',0
cache_failure_ram db 'RAM ',0
cache_failure_reg50 db '50=',0
cache_failure_reg51 db '51=',0
cache_failure_map db 'Map=',0
cache_failure_byte db ' byte ',0
cache_failure_multiple_bytes db ' bytes ',0
cache_failure_socket_names dw cache_failure_bank0_sockets,cache_failure_bank1_sockets
cache_failure_bank0_sockets db HW_CACHE_BANK0_SOCKETS,0
cache_failure_bank1_sockets db HW_CACHE_BANK1_SOCKETS,0
cache_failure_data_bits dw cache_failure_d0,cache_failure_d8,cache_failure_d16,cache_failure_d24
cache_failure_d0 db 'D0-7',0
cache_failure_d8 db 'D8-15',0
cache_failure_d16 db 'D16-23',0
cache_failure_d24 db 'D24-31',0
cache_failure_title db 'L2 failure: ',0
cache_failure_expected db 'Expected ',0
cache_failure_read db 'Read ',0
cache_failure_at db 'at ',0
cache_failure_names dw cache_failure_unknown,cache_failure_55,cache_failure_aa,cache_failure_address,cache_failure_inverse,cache_failure_tag,cache_failure_wt,cache_failure_workspace
cache_failure_unknown db 'Unknown stage',0
cache_failure_55 db '55AA data pattern',0
cache_failure_aa db 'AA55 data pattern',0
cache_failure_address db 'Address pattern',0
cache_failure_inverse db 'Inverse address',0
cache_failure_tag db 'Coherence check',0
cache_failure_wt db 'RAM data',0
cache_failure_workspace db 'Workspace size',0
cache_check_retry db 13,10,'Safe settings loaded; L2 disabled. Press a key to restart.',13,10,0
cache_samples dd 0,4,0x10000,0x20000,0x40000,0x80000,0x100000,0x200000
