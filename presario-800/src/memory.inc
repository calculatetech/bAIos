; VL82C481 probe, following OEM F000:1156/1321/139B: size each bank alone
; at address zero, then restore the accumulated configuration. All writes
; precede comparisons. No stack access while RAM is remapped in protected mode.
; ponytail: banks 1-3 probe 4/8/16/32 MiB; 1/2 MiB SIMMs are deferred.
; Bank 0 remains onboard 4/8 MiB. Over-limit layouts keep
; earlier banks, not a new policy that disables onboard RAM to maximize size.

; These macros run stacklessly. BX retains the accepted bank configuration;
; EBX bit 31 records failure, bits 18:16 the candidate size code. CX is the
; probe-table end. EBP retains the original CR0.
%macro memory_select_bank 2
    mov al, RAMCFG0_REG
    out CHIPSET_INDEX, al
    mov al, (0x8888 | ((%2) << ((%1) * 4))) & 0xFF
    out CHIPSET_DATA, al
    mov al, RAMCFG1_REG
    out CHIPSET_INDEX, al
    mov al, (0x8888 | ((%2) << ((%1) * 4))) >> 8
    out CHIPSET_DATA, al
%endmacro

; Re-select an earlier bank at its detected size, including its second side.
%macro memory_select_detected_bank 1
    mov si, bx
    and si, 0xF << ((%1) * 4)
    or si, 0x8888
    mov al, RAMCFG0_REG
    out CHIPSET_INDEX, al
    mov ax, si
    out CHIPSET_DATA, al
    mov al, RAMCFG1_REG
    out CHIPSET_INDEX, al
    mov ax, si
    shr ax, 8
    out CHIPSET_DATA, al
    mov ax, bx
    shr ax, (%1) * 4
    and al, 7
    mov cx, memory_probe_32_end
    cmp al, 7
    je %%sized
    mov cx, memory_probe_16_end
    cmp al, 6
    je %%sized
    mov cx, memory_probe_end
    cmp al, 5
    je %%sized
    mov cx, memory_probe_single_end
%%sized:
%endmacro

%macro memory_write_signature 0
    mov si, memory_probe_points
%%write:
    cs lodsd
    mov edi, eax
    xor eax, edx
    mov [edi], eax
    cmp si, cx
    jb %%write
%endmacro

%macro memory_check_signature 0
    mov si, memory_probe_points
%%compare:
    cs lodsd
    mov edi, eax
    xor eax, edx
    cmp [edi], eax
    je %%matched
    or ebx, 0x80000000
%%matched:
    cmp si, cx
    jb %%compare
%endmacro

%macro memory_probe_bank 1
    and ebx, 0x0000FFFF
    or ebx, 0x00070000
    post_code_early 0x25 + ((%1) - 1) * 3
    ; OEM F000:11B1-1205 tests F, then E, D and C.
    memory_select_bank %1, 7
    mov cx, memory_probe_32_end
%%pattern:
    mov edx, ~(0xB0000000 | ((%1) << 24))
    memory_write_signature
    memory_check_signature
    not edx
    memory_write_signature
    memory_check_signature
    test ebx, 0x80000000
    jz %%cross_bank
    mov eax, ebx
    shr eax, 16
    and al, 7
    cmp al, 4
    je %%cross_bank
    and ebx, 0x0000FFFF
    cmp al, 7
    jne %%smaller
    or ebx, 0x00060000
    memory_select_bank %1, 6
    mov cx, memory_probe_16_end
    jmp %%pattern
%%smaller:
    cmp al, 6
    jne %%single
    or ebx, 0x00050000
    memory_select_bank %1, 5
    mov cx, memory_probe_end
    jmp %%pattern
%%single:
    or ebx, 0x00040000
    memory_select_bank %1, 4
    mov cx, memory_probe_single_end
    jmp %%pattern

%%cross_bank:
    ; A bank must not mirror an earlier bank. Restore earlier signatures
    ; even after failure so one bad candidate cannot poison the next probe.
%assign previous_bank 0
%rep %1
    test bx, 4 << (previous_bank * 4)
    jz %%skip %+ previous_bank
    memory_select_detected_bank previous_bank
    mov edx, 0xB0000000 | (previous_bank << 24)
    memory_check_signature
    memory_write_signature
%%skip %+ previous_bank:
%assign previous_bank previous_bank + 1
%endrep
    test ebx, 0x80000000
    jnz %%absent
    mov eax, ebx
    shr eax, 16
    and ax, 7
    shl ax, (%1) * 4
    or bx, ax
    ; The controller decodes at most 64 MiB. Keep onboard/earlier banks;
    ; leave only this candidate disabled if adding it exceeds that limit.
    ; Still probe later banks: a smaller one may fit the remaining space.
    mov si, bx
    xor dx, dx
    mov di, 4
%%sum:
    mov ax, si
    and ax, 7
    cmp al, 4
    jb %%next_size
    mov cl, al
    sub cl, 2
    mov ax, 1
    shl ax, cl
    add dx, ax
%%next_size:
    shr si, 4
    dec di
    jnz %%sum
    cmp dx, 64
    jbe %%accepted
    and bx, 0xFFFF ^ (7 << ((%1) * 4))
    post_code_early 0x2E
    jmp %%done
%%accepted:
    post_code_early 0x26 + ((%1) - 1) * 3
    jmp %%done
%%absent:
    post_code_early 0x27 + ((%1) - 1) * 3
%%done:
%endmacro

init_memory:
    pushad
    push ds
    push es
    out CHIPSET_CONFIG_ON, al
    ; Cold and warm POST can change interleave. Mask DMA before any RAM map
    ; change; the existing AT setup will initialize the channels later.
    xor al, al
    out DMA1_MASTER_CLEAR, al
    out DMA2_MASTER_CLEAR, al
    test si, si
    jnz .retained
    post_code 0x21
    mov al, RAMCFG0_REG
    out CHIPSET_INDEX, al
    mov al, RAMCFG0_DOUBLE
    out CHIPSET_DATA, al

    sub sp, 6
    mov di, sp
    sgdt [ss:di]
    in al, 0x92
    push ax
    and al, 0xFE
    or al, 2
    out 0x92, al
    mov al, 0x80
    out 0x70, al               ; No NMI across the protected-mode transition.
    lgdt [cs:move_gdtr]
    mov ebp, cr0
    mov eax, ebp
    or al, 1
    mov cr0, eax
    jmp 0x08:.protected
.protected:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov ebx, 0x55AA55AA
.pattern:
    mov si, memory_probe_points
    mov cx, (memory_probe_end - memory_probe_points) / 4
.write:
    cs lodsd
    mov edi, eax
    xor eax, ebx
    mov [edi], eax
    loop .write
    mov si, memory_probe_points
    mov cx, (memory_probe_end - memory_probe_points) / 4
.compare:
    cs lodsd
    mov edi, eax
    xor eax, ebx
    cmp [edi], eax
    jne .single
    loop .compare
    not ebx
    cmp ebx, 0x55AA55AA
    jne .pattern
    mov bx, 0x8800 | RAMCFG0_DOUBLE
    post_code_early 0x23
    jmp .other_banks
.single:
    mov bx, 0x8800 | RAMCFG0_VALUE
    post_code_early 0x22
.other_banks:
    ; Seed every detected side, so later banks cannot alias either half.
    ; This also rejects flat emulator mappings that ignore bank selection.
    memory_select_detected_bank 0
    mov edx, 0xB0000000
    memory_write_signature
    memory_probe_bank 1
    memory_probe_bank 2
    memory_probe_bank 3
    ; Restore onboard RAM (including the saved stack and EBDA) before any
    ; stack access or real-mode return. Bank 0 keeps its accepted geometry.
    mov al, RAMCFG0_REG
    out CHIPSET_INDEX, al
    mov al, bl
    out CHIPSET_DATA, al
    mov al, RAMCFG1_REG
    out CHIPSET_INDEX, al
    mov al, bh
    out CHIPSET_DATA, al
.leave_protected:
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov cr0, ebp
    jmp 0xF000:.real
.real:
    pop ax
    and al, 0xFE
    out 0x92, al
    mov di, sp
    o32 lgdt [ss:di]
    add sp, 6
    jmp .publish
.retained:
    post_code 0x24
.publish:
    mov al, RAMCFG0_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov dl, al
    mov al, RAMCFG1_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov dh, al
    out CHIPSET_CONFIG_OFF, al
    xor bx, bx
    mov cx, 4
.sum_banks:
    mov al, dl
    call memory_bank_mib
    add bx, ax
    shr dx, 4
    loop .sum_banks
    dec bx                     ; Convert total MiB to extended KiB without
    shl bx, 10                 ; overflowing at the 64 MiB boundary.
    mov ax, STATE_SEG
    mov es, ax
    mov [es:S_EXTENDED_KIB], bx
    pop es
    pop ds
    popad
    ret

; Each lower address has a partner 4 MiB higher. None overlaps the POST
; stack, IVT, EBDA, or ROM hole. Later shadow copies can overwrite low RAM.
align 4
memory_probe_points:
    dd 0x010000, 0x020000, 0x040000, 0x080000
    dd 0x100000, 0x180000, 0x200000, 0x300000
memory_probe_single_end:
    dd 0x410000, 0x420000, 0x440000, 0x480000
    dd 0x500000, 0x580000, 0x600000, 0x700000
memory_probe_end:
    ; Extend the paired-address test through both halves of a 16 MiB bank.
    ; OEM's code-E test includes 10 MiB (table end F000:138B).
    dd 0x810000, 0x820000, 0x840000, 0x880000
    dd 0x900000, 0x980000, 0xA00000, 0xB00000
    dd 0xC10000, 0xC20000, 0xC40000, 0xC80000
    dd 0xD00000, 0xD80000, 0xE00000, 0xF00000
memory_probe_16_end:
    ; Partners 16 MiB above every lower sample expose the second side of
    ; a 4M-device bank. OEM's code-F table includes 20 and 24 MiB.
    dd 0x1010000, 0x1020000, 0x1040000, 0x1080000
    dd 0x1100000, 0x1180000, 0x1200000, 0x1300000
    dd 0x1410000, 0x1420000, 0x1440000, 0x1480000
    dd 0x1500000, 0x1580000, 0x1600000, 0x1700000
    dd 0x1810000, 0x1820000, 0x1840000, 0x1880000
    dd 0x1900000, 0x1980000, 0x1A00000, 0x1B00000
    dd 0x1C10000, 0x1C20000, 0x1C40000, 0x1C80000
    dd 0x1D00000, 0x1D80000, 0x1E00000, 0x1F00000
memory_probe_32_end:

; This checkpoint programs absent / 4 / 8 / 16 / 32 MiB nibbles.
memory_bank_mib:
    and ax, 7
    cmp al, 4
    je .done
    cmp al, 5
    je .double
    cmp al, 6
    je .sixteen
    cmp al, 7
    je .thirty_two
    xor ax, ax
    ret
.double:
    mov ax, 8
    ret
.sixteen:
    mov ax, 16
    ret
.thirty_two:
    mov ax, 32
.done:
    ret

; AL preferred mode, AH eligible-mode mask after board policy (bits 0..5).
; Equal density/side codes are a conservative eligibility rule. RAMSET is
; written only by startup, after this frame returns and before rebuilding RAM.
memory_interleave_options:
    pushf
    cli
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    out CHIPSET_CONFIG_ON, al
    mov al, RAMCFG0_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov dl, al
    mov al, RAMCFG1_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov dh, al
    out CHIPSET_CONFIG_OFF, al
    xor bx, bx
    mov si, memory_interleave_pairs
    mov di, 1
.pair:
    cs lodsb
    mov cl, al
    mov ax, dx
    shr ax, cl
    and ax, 7
    mov bp, ax
    cs lodsb
    mov cl, al
    mov ax, dx
    shr ax, cl
    and ax, 7
    cmp bp, 4
    jb .next
    cmp ax, bp
    jne .next
    or bx, di
.next:
    shl di, 1
    cmp di, 16
    jb .pair
    mov al, bl
    and al, 9                 ; Modes 1 and 4 form mode 5.
    cmp al, 9
    jne .other_combination
    or bl, 0x10
.other_combination:
    mov al, bl
    and al, 6                 ; Modes 2 and 3 form mode 6.
    cmp al, 6
    jne .select
    or bl, 0x20
.select:
    and bl, RAM_INTERLEAVE_MODES
    mov al, 5
    test bl, 0x10
    jnz .selected
    inc al
    test bl, 0x20
    jnz .selected
    xor ax, ax
    test bl, bl
    jz .selected
    mov cl, bl
.first:
    inc al
    shr cl, 1
    jnc .first
.selected:
    mov ah, bl
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    popf
    ret
memory_interleave_pairs db 0, 4, 0, 12, 4, 8, 8, 12

; Publish both AT memory-size copies. CACHECHK reads 15h-18h directly;
; leaving those bytes stale disagrees with AH=88h and tested 30h/31h.
; NMI stays masked here, as in the OEM's POST CMOS accesses.
publish_memory_cmos:
    pushf
    cli
    pushad
    push fs
    mov ax, STATE_SEG
    mov fs, ax
    mov bx, 640                 ; Installed base RAM; INT12 excludes our EBDA.
    mov dl, 0x95
    call .word
    mov bx, [fs:S_EXTENDED_KIB]
    mov dl, 0x97
    call .word
    mov bx, [fs:S_EXTENDED_KIB]
    mov dl, 0xB0
    call .word
    call update_cmos_checksum
    pop fs
    popad
    popf
    ret
.word:
    mov cx, 2
.byte:
    mov al, dl
    out 0x70, al
    in al, 0x84
    mov al, bl
    out 0x71, al
    shr bx, 8
    inc dl
    loop .byte
    ret

; Shared AT checksum only. Setup must not republish fixed-segment RAM state.
update_cmos_checksum:
    pushf
    cli
    pushad
    ; 15h-18h are in the standard AT checksum range, 10h through 2Dh.
    xor bx, bx
    mov dl, 0x90
.sum:
    mov al, dl
    out 0x70, al
    in al, 0x84
    in al, 0x71
    xor ah, ah
    add bx, ax
    inc dl
    cmp dl, 0xAE
    jb .sum
    xchg bl, bh                ; AT stores checksum high byte at 2Eh.
    call .word
    popad
    popf
    ret
.word:
    mov cx, 2
.byte:
    mov al, dl
    out 0x70, al
    in al, 0x84
    mov al, bl
    out 0x71, al
    shr bx, 8
    inc dl
    loop .byte
    ret

report_memory:
    pushad
    push fs
    call load_bios_state
    mov si, memory_message
    call print_string
    pushf
    cli
    out CHIPSET_CONFIG_ON, al
    mov al, RAMCFG0_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov bl, al
    mov al, RAMCFG1_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov bh, al
    out CHIPSET_CONFIG_OFF, al
    popf
    mov al, bl
    call memory_hex_byte
    mov al, '/'
    call memory_character
    mov al, bh
    call memory_hex_byte
    mov si, memory_bank_message
    call print_string
    mov dx, bx
    mov cx, 4
.bank:
    mov al, dl
    call memory_bank_mib
    push dx
    call memory_decimal
    pop dx
    shr dx, 4
    dec cx
    jz .total
    mov al, '/'
    call memory_character
    jmp .bank
.total:
    mov si, memory_total_message
    call print_string
    mov ax, [fs:S_EXTENDED_KIB]
    shr ax, 10
    inc ax                     ; 63 MiB extended + 1 MiB = 64, without wrap.
    call memory_decimal
    mov si, memory_end_message
    call print_string
    call memory_interleave_options
    mov bh, ah
    pushf
    cli
    out CHIPSET_CONFIG_ON, al
    mov al, RAMSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov bl, al
    out CHIPSET_CONFIG_OFF, al
    popf
    mov si, memory_interleave_message
    call print_string
    mov al, bh
    call memory_hex_byte
    mov si, memory_mode_message
    call print_string
    mov al, bl
    shr al, 5
    add al, '0'
    call memory_character
    mov si, memory_ramset_message
    call print_string
    mov al, bl
    call memory_hex_byte
    mov si, memory_newline
    call print_string
    pop fs
    popad
    ret
memory_decimal:
    xor dx, dx
    mov bx, 10
    div bx
    test ax, ax
    jz .digit
    push dx
    call memory_decimal
    pop dx
.digit:
    mov al, dl
    add al, '0'
    jmp memory_character
memory_hex_byte:
    push ax
    shr al, 4
    call .digit
    pop ax
    and al, 15
.digit:
    add al, '0'
    cmp al, '9'
    jbe memory_character
    add al, 7
memory_character:
    push ax
    push bx
    mov ah, 0x0E
    mov bx, 7
    int 0x10
    pop bx
    pop ax
    ret
memory_message       db 'RAM CFG=', 0
memory_bank_message  db ' banks MiB=', 0
memory_total_message db ' total=', 0
memory_end_message   db ' MiB', 0
memory_interleave_message db ' INTLV avail=', 0
memory_mode_message db ' mode=', 0
memory_ramset_message db ' RAMSET=', 0
memory_newline db 13, 10, 0
