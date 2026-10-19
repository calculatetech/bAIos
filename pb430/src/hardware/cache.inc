; PB4308F33..9110: presence is distinct from the ambiguous last size candidate.
cache_initialize:
    pushf
    cli
    pushad
    push ds
    push es
    cmp byte [fs:HW_CACHE_WARM],1
    jne .cold
    cmp byte [fs:HW_CACHE_VALID],CACHE_STATE_VALID
    jne .cold
    post_code 0x1C
    jmp .return
.cold:
    mov byte [fs:HW_CACHE_WARM],0
    ; OEM8F07..8F31 prerequisites before the SRAM probe.
    mov al,0x0A
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    or al,4
    mov ah,al
    mov al,0x0A
    call acc_write
    mov al,0x18
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    or al,0x20
    mov ah,al
    mov al,0x18
    call acc_write
    mov ax,0x2000
    mov ds,ax
    mov ax,0x6000
    mov es,ax
    push dword [0]
    push dword [4]
    push dword [0x8000]
    push dword [es:0]
    mov ax,0x4000
    mov es,ax
    push dword [es:0]
    mov ax,0x3000
    mov es,ax
    push dword [es:0]
    post_code 0x12
    ; OEM8F3A..8F4A: disable and invalidate L1, then select CMOS70.
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    invd
    mov al,0x70
    out 0x70,al
    xor bx,bx
    xor dx,dx
    mov al,4
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xC0
    ; OEM8F54..9110 uses no stack or state RAM while SRAM is selected.
    mov al,0x33
    acc_commit_early 4
    mov al,0x1A
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xE7
    or al,0x10
    acc_commit_early 0x1A
    mov word [0],0x55AA
    mov word [2],0x0F0F
    cmp word [0],0x55AA
    jne .absent
    mov al,0xBD
    out 0x70,al ; OEM8FC8 masks NMI before its private presence/size updates.
    mov bl,1
    mov al,0x92
    acc_commit_early 1
    mov ax,0x6000
    mov es,ax
    mov word [0],0x5A5A
    mov word [es:0],0x5678
    mov word [4],0x1234
    cmp word [0],0x5A5A
    je .size512
    mov ax,0x4000
    mov es,ax
    mov word [0],0x55AA
    mov word [es:0],0xAA55
    mov word [4],0x1234
    cmp word [0],0x55AA
    je .size256
    mov ax,0x3000
    mov es,ax
    mov word [0],0x33BB
    mov word [es:0],0xBB33
    mov word [4],0x1234
    cmp word [0],0x33BB
    je .size128
    ; OEM909D..90D0: retain its last real alias witness. Both results
    ; ultimately overwrite the OEM code with0, so neither qualifies a size.
    mov word [0],0x5AA5
    mov word [0x8000],0xA55A
    mov word [4],0x1234
    cmp word [0],0x5AA5
    jne .ambiguous
    mov dh,1
.ambiguous:
    jmp .restore
.size512:
    mov bh,2
    jmp .qualified
.size256:
    mov bh,3
    jmp .qualified
.size128:
    mov bh,1
.qualified:
    mov dl,1
    jmp .restore
.absent:
    ; OEM8F9B restores the byte at8CE6 before the common94 write.
    xor al,al
    acc_commit_early 4
    mov al,0xBD
    out 0x70,al
.restore:
    mov al,0x70
    out 0x70,al
    mov al,0x94
    acc_commit_early 4
    mov al,0x1A
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xE7
    acc_commit_early 0x1A
    mov [fs:HW_CACHE_PRESENT],bl
    mov [fs:HW_CACHE_CODE],bh
    mov [fs:HW_CACHE_QUALIFIED],dl
    mov [fs:HW_CACHE_LAST],dh
    mov ax,0x3000
    mov es,ax
    pop dword [es:0]
    mov ax,0x4000
    mov es,ax
    pop dword [es:0]
    mov ax,0x6000
    mov es,ax
    pop dword [es:0]
    pop dword [0x8000]
    pop dword [4]
    pop dword [0]
    mov byte [fs:HW_CACHE_VALID],CACHE_STATE_VALID
    ; Report only after the stock probe mode and saved RAM are restored.
    test bl,bl
    jz .return
    test dl,dl
    jz .report_unknown
    post_code_early 0x1F
    jmp .return
.report_unknown:
    post_code_early 0x16
.return:
    pop es
    pop ds
    popad
    popf
    ret

chipset_late_cache:
    call load_bios_state
    pushf
    pop word [fs:HW_CACHE_ENTRY_FLAGS]
    cli
    push ax
    push ds
    xor ax,ax
    mov ds,ax
    ; The shared timer touches high BIOS RAM while OEM1A selects tag setup.
    push dword [0x20]
    mov word [0x20],cache_stock_timer
    mov [0x22],cs
    mov [fs:HW_CACHE_SS],ss
    mov [fs:HW_CACHE_SP],sp
    ; OEM4C45..4C53: use the target's physical stack for the whole transition.
    mov ax,0x30
    mov ss,ax
    mov sp,0x100
    call .stock_parent
    pushf
    pop word [fs:HW_CACHE_FLAGS]
    cli
    mov ax,[fs:HW_CACHE_ENTRY_FLAGS]
    and ax,0x200
    or [fs:HW_CACHE_FLAGS],ax
    mov ax,[fs:HW_CACHE_SS]
    mov ss,ax
    mov sp,[fs:HW_CACHE_SP]
    xor ax,ax
    mov ds,ax
    pop dword [0x20]
    pop ds
    pop ax
    push word [fs:HW_CACHE_FLAGS]
    popf
    ret
.stock_parent:
    ; OEM97C7/97C8 supplies another saved AX and return address.
    push ax
    call cache_late_stock_frame
    ; OEM97CB..97CE follows the cache body with NMI selection and C7/20.
    mov al,0xB4
    pushf
    call cache_stock_cmos_read
    popf
    call cache_stock_controller_high
    pop ax
    ret

cache_late_stock_frame:
    push ax
    pb_stage 0x53
    push bx
    push cx
    push ds
    push si
    push bp
    call load_bios_state
    post_code 0x61
    call cache_ranges
    mov al,0x34
    pushf
    call cache_stock_cmos_read
    popf
    post_code 0x62
    cmp byte [fs:C_CHIP+1],0
    je cache_late_done
    post_code 0x63
    call cache_stock_cpu_enable
    mov ax,0 ; OEM972D selects DS=0000 before the late cache frame is used.
    mov ds,ax
    mov al,0x3D
    pushf
    call cache_stock_cmos_read
    popf
    cmp byte [fs:C_CHIP+2],0
    je cache_late_done
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    jne cache_late_done
    post_code 0x64
; OEM9748..978D is inline in the six-word owner, without another CALL frame.
; Added I/O changes the transient sequence; keep diagnostics outside this block.
cache_stock_enable:
    mov al,0x1A
    call acc_read
    and al,0xE7
    or al,8
    mov ah,0x1A
    xchg ah,al
    call cache_stock_write
    mov al,0x70
    call cache_stock_cmos_read
    sti
    mov al,4
    call acc_read
    or al,1
    mov ah,4
    xchg ah,al
    call cache_stock_write
    pushf
    cli
    call cache_stock_fill
    mov al,0x1E
    call acc_read
    or al,0x20
    mov ah,0x1E
    xchg ah,al
    call cache_stock_write
    mov al,0x1A
    call acc_read
    and al,0xE7
    mov ah,0x1A
    xchg ah,al
    call cache_stock_write
    popf
cache_stock_enable_end:
    mov byte [fs:HW_CACHE_ENABLED],1
    post_code 0x69
cache_late_done:
    pb_stage 0x54
cache_late_restore:
    ; OEM978E..9794: retain the stock word-sized frame through return.
    pop bp
    pop si
    pop ds
    pop cx
    pop bx
    pop ax
    ret
cache_late_restore_end:

; OEM971F..972B, before external-cache activation.
cache_stock_cpu_enable:
    mov eax,cr0
    and eax,0x9FFFFFFF
    mov cr0,eax
    invd
cache_stock_cpu_enable_end:
    ret

; Preserve OEM encodings as well as instructions while tag initialization is active.
cache_stock_fill:
    incbin "../reference/pb430-m27c1001.bin",0x19795,0x12
.fill:
    incbin "../reference/pb430-m27c1001.bin",0x197A7,9
.reads:
    incbin "../reference/pb430-m27c1001.bin",0x197B0,0x17
cache_stock_fill_end:

; OEMA171..A17B: AL becomes the written value, as the stock caller expects.
cache_stock_write:
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,ah
    out CHIPSET_DATA,al
    out 0xED,al
    ret
cache_stock_write_end:

; OEMDC2C..DC37; its CLI/NMI selection is part of cache activation.
cache_stock_cmos_read:
    push dx
    mov dx,0x70
    cli
    out dx,al
    inc dx
    out 0xED,al
    in al,dx
    pop dx
    ret
cache_stock_cmos_read_end:

; OEMCFDF..D027: retain its low-BDA timer, INT1C hook and late PIC EOI.
; Only the ROM address of the zero DS constant moves with this routine.
cache_stock_timer:
    incbin "../reference/pb430-m27c1001.bin",0x1CFDF,3
    mov ds,[cs:cache_stock_timer_zero]
    incbin "../reference/pb430-m27c1001.bin",0x1CFE7,0x41
cache_stock_timer_end:
cache_stock_timer_zero:
    dw 0

; OEM963D..9687, reached only after the normal warm-marker classification.
cache_stock_warm_entry:
    incbin "../reference/pb430-m27c1001.bin",0x1963D,0x1A
    call cache_stock_fill
    mov al,0x69
    call cache_stock_cmos_read
    sti
    incbin "../reference/pb430-m27c1001.bin",0x19660,0x0C
    mov al,0x1E
    call acc_read
    and al,0xDF
    mov ah,0x1E
    xchg ah,al
    call cache_stock_write
    incbin "../reference/pb430-m27c1001.bin",0x1967A,0x0E
cache_stock_warm_entry_end:
    jmp di

; OEM9808 high branch: preserve caller state and wait after the final data write.
cache_stock_controller_high:
    push ax
    pushf
    call kbc_wait_input_clear
    jc .failed
    cli
    mov al,0xC7
    call kbc_command
    jc .failed
    mov al,0x20
    call kbc_write_data
    jc .failed
    call kbc_wait_input_clear
    jc .failed
    popf
    pop ax
    ret
.failed:
    mov al,0xD5
    jmp keyboard_halt

; OEM968E..9705 precedes the reference controller-reset pulse.
cache_stock_reset:
    push ds
    push fs
    push ax
    pushf
    call load_bios_state
    mov al,0x34
    pushf
    call cache_stock_cmos_read
    popf
    cmp byte [fs:C_CHIP+1],0
    je .done
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    invd
    mov al,0x3D
    call cache_stock_cmos_read
    cmp byte [fs:C_CHIP+2],0
    je .done
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    jne .done
    mov al,0x1A
    call acc_read
    and al,0xE7
    or al,8
    mov ah,0x1A
    xchg ah,al
    call cache_stock_write
    call cache_stock_fill
    mov al,0x70
    call cache_stock_cmos_read
    sti
    mov al,4
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xFE
    mov ah,al
    mov al,4
    call cache_stock_write
    mov al,0x1A
    call acc_read
    and al,0xE7
    mov ah,0x1A
    xchg ah,al
    call cache_stock_write
    mov byte [fs:HW_CACHE_ENABLED],0
.done:
    popf
    pop ax
    pop fs
    pop ds
    ret

cache_initial_policy:
    pushad
    call chipset_settings_load
    cmp byte [fs:HW_CACHE_WARM],1
    je .done
    mov al,0xBD
    out 0x70,al ; OEM9112 retains NMI masking across cold range/timing setup.
    call cache_ranges
    mov ax,0x9301 ; OEM9142 complete probe/range continuation.
    call acc_write
    in al,0x78
    and al,7
    sub al,3
    jnc .lower
    xor al,al
.lower:
    cmp al,3
    jbe .index
    mov al,3
.index:
    movzx bx,al
    mov si,acc_cache_safe_table
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    jne .rows
    cmp byte [fs:C_CHIP+1],0
    je .rows
    mov si,acc_cache_live_table
.rows:
    cs lodsb
    cmp al,0xFF
    je .ranges
    mov dl,al
    call cache_table_read
    cs mov ah,[si]
    inc si
    and ah,al
    or ah,[cs:si+bx]
    add si,4
    mov al,dl
    call cache_table_write
    jmp .rows
.ranges:
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    jne .cold_resume
    cmp byte [fs:C_CHIP+1],0
    je .cold_resume
    movzx bx,byte [fs:HW_CACHE_CODE]
    dec bx
    mov al,0x1D
    call cache_table_read
    mov ah,[cs:acc_cache_size_1d+bx]
    mov al,0x1D
    call cache_table_write
    mov al,0x1E
    call cache_table_read
    and al,0x80
    or al,[cs:acc_cache_size_1e+bx]
    mov ah,al
    mov al,0x1E
    call cache_table_write
.cold_resume:
    call cache_stock_cold_resume
.done:
    popad
    ret

; Healthy stock cold POST resumes its shutdown test here before shadow/RAM testing.
; The modular startup already holds L1/IRQs off; retain the reset's hardware writes.
cache_stock_cold_resume:
    incbin "../reference/pb430-m27c1001.bin",0x1E081,0x31
cache_stock_cold_resume_controls:
    incbin "../reference/pb430-m27c1001.bin",0x1E0E6,0x26
cache_stock_cold_resume_end:
    ret

cache_ranges:
    pushad
    mov al,2
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    or al,0x40
    mov ah,al
    mov al,2
    call acc_write
    ; OEM9DA5..9DB9 retains both reads before its equivalent range rows.
    mov al,0xBD
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    jne .mask
    mov al,0xBF
.mask:
    out 0x70,al
    xor al,al
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    jne .read_rows
    mov al,[fs:HW_CACHE_CODE]
.read_rows:
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,7
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,3
    mov si,acc_range_absent
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    jne .write
    mov si,acc_range128
    cmp byte [fs:HW_CACHE_CODE],1
    je .write
    mov si,acc_range256_512
.write:
    mov bl,0x0C
.next:
    cs lodsb
    mov ah,al
    mov al,bl
    call acc_write
    inc bl
    cmp bl,0x12
    jb .next
    popad
    ret
; OEM9306..9323 has an index delay, but no delay after either data access.
cache_table_read:
    out CHIPSET_INDEX,al
    out 0xED,al
    in al,CHIPSET_DATA
    ret
cache_table_write:
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,ah
    out CHIPSET_DATA,al
    ret
; OEM91EA/9232 triples: index,preserve-mask,four jumper-indexed values.
acc_cache_safe_table:
    db 4,0,0x94,0x54,0x54,0x14
    db 6,0,0x13,0x33,0xB7,0x12
    db 7,0xE0,0x18,0x18,0x14,0x18
    db 0x0B,0,4,5,5,0x15
    db 0x18,0x8C,0x20,0x20,0,0
    db 0x1A,0x40,0x24,0x24,0x24,0x24,0xFF
acc_cache_live_table:
    db 4,0,0x14,0x14,0x14,0x34
    db 6,0,0x23,0x33,0xB7,0x12
    db 7,0xE0,0x18,0x18,0x14,0x18
    db 0x0B,0,4,0x15,0x15,0x15
    db 0x18,0x8C,0x20,0,0,0
    db 0x1A,0x40,0x24,0x24,0x24,0x24,0xFF
acc_range_absent:
    db 0,0,0,0,0,0
acc_range128:
    db 0x0B,0x40,0x0C,0x80,0,0
acc_range256_512:
    db 0x0C,0x80,0,0,0,0

; OEM927A/92CA: qualified code1/2/3 columns are identical at all jumpers.
acc_cache_size_1d:
    db 0xFC,0xF0,0xF8
acc_cache_size_1e:
    db 0x79,0x7B,0x7B
