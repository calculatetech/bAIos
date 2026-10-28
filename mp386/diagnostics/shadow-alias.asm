bits 16
org 0x100
; OEM RAM-E / mp_shadow_prepare aperture; E000 is unused generated ROM padding.
%include "shadow-alias-rom.inc"
%macro check16 2-3 refused
    mov byte [guard_step],%1
    movzx eax,ax
    mov [guard_actual],eax
    mov dword [guard_expected],0
    mov word [guard_expected],%2
    cmp ax,%2
    jne %3
%endmacro

start:
    cld
    smsw ax
    test al,1
    jnz mode_error
    mov ax,cs
    cmp ax,0x7000
    jae placement_error
    mov ax,ss
    cmp ax,0x7000
    jae placement_error
    push cs
    pop ds
    push cs
    pop es
    pushf
    cli
    in ax,0x26
    mov [saved_index],ax
    xor ax,ax
    mov fs,ax
    mov ax,[fs:0x40E]
    check16 1,0x9E00
    mov ax,0x9E00
    mov fs,ax
    mov byte [guard_step],2
    mov eax,[fs:0x1004]
    mov [guard_actual],eax
    mov dword [guard_expected],0x5833504D
    cmp eax,0x5833504D
    jne refused
    mov ax,[fs:0x101C]
    check16 3,3
    movzx ax,byte [fs:0x101E]
    check16 4,2
    mov si,banks
    mov di,0x1010
    mov cx,6
.banks:
    lodsw
    mov dx,ax
    mov ax,[fs:di]
    check16 5,dx
    add di,2
    loop .banks
    in al,0x5F
    and ax,0x80
    check16 7,0x80
    mov ax,0x0800
    call read_ti
    check16 8,0x0200
    xor bx,bx
.controller:
    mov ax,bx
    call read_ti
    and ax,0xFF00
    check16 9,bx
    mov ax,bx
    or al,2
    call read_ti
    check16 10,0x8100
    mov ax,bx
    or al,3
    call read_ti
    check16 11,0x4101
    mov ax,bx
    or al,7
    call read_ti
    check16 12,0xAA00
    mov ax,bx
    shl ax,4
    or ax,0x8020
    call read_ti
    test bx,bx
    jnz .other
    check16 13,0x8020
    mov [saved_map],ax
    jmp .next
.other:
%ifdef MP386_RAM_BACKING
    cmp bx,0x0200
    jne .not_target
    mov [target_map],ax
.not_target:
%endif
    and ax,0x8000
    check16 14,0
.next:
    add bx,0x100
    cmp bx,0x300
    jb .controller
    mov bx,0x803C
    mov dx,0x8028
.pages:
    mov ax,bx
    call read_ti
    check16 15,dx
    inc bx
    inc dx
    cmp bx,0x8040
    jb .pages
    call verify_rom
    jc refused
%ifdef MP386_RAM_BACKING
    mov ax,0x0200
    call read_ti
%ifdef MP386_ZERO_BASE
    check16 22,0x0200
%else
    check16 22,0x020A
%endif
%endif
    mov ax,[gs:0xE000]
    mov [low_values],ax
    check16 18,0xFFFF
    xor eax,eax
    mov ax,cs
    shl eax,4
    add eax,high_value
    mov [table+0x1A],ax
    shr eax,16
    mov [table+0x1C],al
    mov [table+0x1F],ah
%ifdef MP386_APERTURE_ADDRESS
    call address_probe
    jmp .report
%endif
%ifdef MP386_RAM_BACKING
    ; Qualify this aperture against both known linear banks before a tag write.
    mov word [copy_words],8
    mov word [target_page],0x8000
    mov byte [control_step],1
    mov word [table+0x12],0
    mov byte [table+0x14],0xA0
    call aperture_control
    jc .report
    mov word [target_page],0x8100
    mov byte [control_step],2
    mov byte [table+0x14],0xE0
    call aperture_control
    jc .report
    mov word [copy_words],1
    mov word [target_page],0x817F
    mov word [table+0x12],0xE000
    mov byte [table+0x14],0xFF
%endif
%ifdef MP386_TAIL_SAMPLES
    mov word [target_page],0x8180
    mov word [table+0x12],0x2000
    mov byte [table+0x14],0
    mov byte [table+0x17],1
.tail_sample:
%endif
%ifdef MP386_UPPER_ALIAS
    call upper_begin
    jc .report
%endif
    mov byte [guard_step],19
    mov dword [guard_expected],0
    call read_high
    mov [guard_actual],eax
    jc refused
    mov ax,[high_value]
    mov [high_values],ax
    mov al,0x8D
    out 0x70,al
    call open_aperture
    jc .backing_mismatch
    mov ax,[es:0x2000]
    mov [backing_values],ax
%ifdef MP386_TAIL_SAMPLES
    cmp ax,[high_values]
    jne .tail_before_mismatch
%endif
%ifdef MP386_RAM_BACKING
    mov dx,0xA55A
    cmp ax,dx
    jne .tag_selected
    mov dx,0x5AA5
.tag_selected:
    mov [tag_value],dx
    mov [es:0x2000],dx
%else
    check16 21,0xFFFF,.backing_mismatch
    mov word [es:0x2000],0xA55A
%endif
    mov ax,[es:0x2000]
    mov [backing_values+2],ax
    call close_aperture
%ifdef MP386_RAM_BACKING
    cmp ax,[tag_value]
%else
    cmp ax,0xA55A
%endif
    jne .tag_failed
%ifdef MP386_UPPER_ALIAS
    mov byte [table+0x14],0
    mov byte [table+0x17],1
    call read_high
    mov byte [table+0x14],0xFF
    mov byte [table+0x17],0
    jc .read_failed
    mov ax,[high_value]
    mov [upper_value],ax
%endif
    mov ax,[gs:0xE000]
    mov [low_values+2],ax
    call read_high
    jc .read_failed
    mov ax,[high_value]
    mov [high_values+2],ax
    jmp .restore
.backing_mismatch:
    call close_aperture
    jmp refused
%ifdef MP386_TAIL_SAMPLES
.tail_before_mismatch:
    call close_aperture
    mov byte [error_code],8
    jmp .report
%endif
.tag_failed:
    mov byte [error_code],2
    jmp .restore
.read_failed:
    mov byte [error_code],3
.restore:
    call open_aperture
    jc .restore_open_failed
    mov ax,[backing_values]
    mov [es:0x2000],ax
    mov ax,[es:0x2000]
    mov [backing_values+4],ax
    call close_aperture
    cmp ax,[backing_values]
    jne .restore_failed
    mov ax,[gs:0xE000]
    mov [low_values+4],ax
    call read_high
    jc .read_failed_after_restore
    mov ax,[high_value]
    mov [high_values+4],ax
%ifdef MP386_TAIL_SAMPLES
    cmp byte [error_code],0
    jne .report
    mov ax,[high_values+2]
    cmp ax,[tag_value]
    jne .tail_mismatch
    mov ax,[high_values+4]
    cmp ax,[backing_values]
    jne .tail_mismatch
    inc word [target_page]
    add word [table+0x12],0x4000
    adc byte [table+0x14],0
    cmp word [target_page],0x8200
    jb .tail_sample
%endif
    call verify_rom
    jnc .report
.restore_open_failed:
    call close_aperture
.restore_failed:
    mov byte [error_code],4
    jmp .report
.read_failed_after_restore:
    mov byte [error_code],3
%ifdef MP386_TAIL_SAMPLES
    jmp .report
.tail_mismatch:
    mov byte [error_code],8
%endif
.report:
    call restore_index
    popf
%ifdef MP386_RAM_BACKING
    call backing_result
%else
    mov dx,heading
    call message
    mov dx,backing_label
    call message
    mov si,backing_values
    call values
    mov dx,low_label
    call message
    mov si,low_values
    call values
    mov dx,high_label
    call message
    mov si,high_values
    call values
    mov dx,restored_text
    cmp byte [error_code],0
    je .message
    mov dx,error_text
.message:
    call message
%endif
    mov al,[error_code]
    mov ah,0x4C
    int 0x21

refused:
    call restore_index
    popf
%ifdef MP386_RAM_BACKING
    mov byte [error_code],1
    jmp error_exit
%else
    call guard_report
    mov dx,guard_text
    jmp error_exit
%endif
placement_error:
    push cs
    pop ds
%ifdef MP386_RAM_BACKING
    mov byte [error_code],6
%endif
    mov dx,placement_text
    jmp error_exit
mode_error:
%ifdef MP386_RAM_BACKING
    mov byte [error_code],5
%endif
    mov dx,mode_text
error_exit:
%ifdef MP386_RAM_BACKING
    call backing_result
    mov al,[error_code]
    mov ah,0x4C
%else
    call message
    mov ax,0x4C01
%endif
    int 0x21

read_ti:
    mov [last_ti],ax
    out 0x26,ax
    in ax,0x24
    mov [last_value],ax
    ret
write_map:
    xchg ax,dx
    out 0x26,ax
    xchg ax,dx
    out 0x24,ax
    ret
open_aperture:
%ifdef MP386_RAM_BACKING
    ; RAM-E695D/6A1D: displace the low owner before installing the target.
    mov al,0x8D
    out 0x70,al
    mov dx,0x8020
    mov ax,[saved_map]
    and ax,0x7FFF
    call write_map
    mov ax,0x8020
    call read_ti
    check16 23,0x0020,.bad
    mov dx,0xA020
    mov ax,[target_page]
%else
    mov dx,0x8020
    mov ax,0x802B
%endif
    call write_map
%ifdef MP386_RAM_BACKING
    mov ax,0xA020
%else
    mov ax,0x8020
%endif
    call read_ti
    mov byte [guard_step],20
    movzx eax,ax
    mov [guard_actual],eax
%ifdef MP386_RAM_BACKING
    mov dword [guard_expected],0
    mov dx,[target_page]
    mov [guard_expected],dx
    cmp ax,dx
%else
    mov dword [guard_expected],0x802B
    cmp ax,0x802B
%endif
    jne .bad
    mov ax,0x8000
    mov es,ax
    clc
    ret
.bad:
    stc
    ret
close_aperture:
    push ax
%ifdef MP386_RAM_BACKING
    ; RAM-E6A96/6C20: remove target first, then restore the displaced owner.
    mov dx,0xA020
    mov ax,[target_map]
    call write_map
    mov ax,0xA020
    call read_ti
    cmp ax,[target_map]
    jne .failed
    mov dx,0x8020
%endif
    mov ax,[saved_map]
    call write_map
%ifdef MP386_RAM_BACKING
    mov ax,0x8020
    call read_ti
    cmp ax,[saved_map]
    jne .failed
%endif
    push cs
    pop es
    pop ax
    ret
%ifdef MP386_RAM_BACKING
.failed:
    ; DOS can own 80000 again: stop instead of returning with a wrong map.
    mov al,0xE4
    out 0x80,al
    cli
.halt:
    hlt
    jmp .halt
%endif
restore_index:
%ifdef MP386_UPPER_ALIAS
    call upper_end
%endif
    mov ax,[saved_index]
    out 0x26,ax
    mov al,0x0D
    out 0x70,al
    ret
%ifdef MP386_UPPER_ALIAS
upper_begin:
    mov byte [upper_write],0
    call upper_entry
    jc .bad
    check16 24,0x8180,.bad
    mov [upper_saved],ax
    mov byte [upper_active],1
    mov byte [upper_write],1
    mov ax,0x817C
    call upper_entry
    jc .bad
    check16 25,0x817C,.bad
    clc
    ret
.bad:
    mov byte [error_code],1
    stc
    ret
upper_end:
    cmp byte [upper_active],0
    je .done
    mov byte [upper_write],1
    mov ax,[upper_saved]
    call upper_entry
    jc close_aperture.failed
    cmp ax,[upper_saved]
    jne close_aperture.failed
    mov byte [upper_active],0
.done:
    ret
upper_entry:
    ; Texas89CE/896A single-entry view; verify and close it before RAM access.
    push bx
    push dx
    mov bx,ax
    mov al,0x8D
    out 0x70,al
    mov ax,0x0202
    call upper_read
    check16 27,0x8100,.bad
    mov dx,0x0202
    mov ax,0x8120
    call upper_write_map
    mov ax,0x0202
    call upper_read
    mov byte [upper_error],1
    check16 26,0x8120,.restore
    cmp byte [upper_write],0
    je .read
    mov dx,0xA400
    mov ax,bx
    call upper_write_map
.read:
    mov ax,0xA400
    call upper_read
    mov [upper_result],ax
    mov byte [upper_error],0
.restore:
    mov dx,0x0202
    mov ax,0x8100
    call upper_write_map
    mov ax,0x0202
    call upper_read
    cmp ax,0x8100
    jne close_aperture.failed
    cmp byte [upper_error],0
    jne .bad
    mov ax,[upper_result]
    pop dx
    pop bx
    clc
    ret
.bad:
    pop dx
    pop bx
    stc
    ret
upper_read:
    mov [last_ti],ax
    out 0x26,ax
    jmp short $+2
    jmp short $+2
    in ax,0x24
    mov [last_value],ax
    ret
upper_write_map:
    xchg ax,dx
    out 0x26,ax
    jmp short $+2
    jmp short $+2
    xchg ax,dx
    out 0x24,ax
    ret
%endif
verify_rom:
    pushad
    mov ax,0xF000
    mov gs,ax
    xor ebx,ebx
    xor si,si
.sum:
    movzx eax,byte [gs:si]
    add ebx,eax
    inc si
    jnz .sum
    mov byte [guard_step],16
    mov [guard_actual],ebx
    mov dword [guard_expected],ALIAS_ROM_SUM32
    mov di,alias_roms
    mov cx,ALIAS_ROM_COUNT
.candidate:
    cmp ebx,[di]
    je .match
    add di,4
    loop .candidate
    popad
    stc
    ret
.match:
    popad
    clc
    ret
read_high:
    ; DOS can hook INT15; use its chain, as the working boundary reader does.
    push cs
    pop es
    mov si,table
%ifdef MP386_RAM_BACKING
    mov cx,[copy_words]
%else
    mov cx,1
%endif
    mov ax,0x8700
    int 0x15
    jc .bad
    test ah,ah
    jnz .bad
    clc
    ret
.bad:
    stc
    ret

%ifdef MP386_RAM_BACKING
%ifdef MP386_APERTURE_ADDRESS
address_probe:
    ; Read-only discriminator: distinct sources must replace the old window data.
    mov word [copy_words],256
    mov eax,0xA80000
    call address_read
    jc .bios_failed
    mov si,high_value
    mov di,address_before
    mov cx,256
    rep movsw
    mov word [address_row],address_sources
.candidate:
    mov bx,[address_row]
    mov eax,[bx]
    call address_read
    jc .bios_failed
    mov si,high_value
    mov di,address_before
    mov cx,256
    repe cmpsw
    je .next
    mov di,high_value
    mov ax,0xFFFF
    mov cx,256
    repe scasw
    je .next
    mov byte [address_tried],1
    mov si,high_value
    mov di,address_expected
    mov cx,256
    rep movsw
    mov bx,[address_row]
    mov ax,[bx+4]
    mov [target_page],ax
    call open_aperture
    jc .map_failed
    mov eax,0xA80000
    call address_read
    pushf
    call close_aperture
    popf
    jc .bios_failed
    mov si,high_value
    mov di,address_expected
    mov cx,256
    repe cmpsw
    je .matched
.next:
    add word [address_row],6
    cmp word [address_row],address_sources_end
    jb .candidate
    mov byte [error_code],10
    cmp byte [address_tried],0
    je .done
    mov byte [error_code],8
.done:
    ret
.matched:
    mov byte [error_code],0
    ret
.map_failed:
    call close_aperture
    mov byte [error_code],1
    ret
.bios_failed:
    mov byte [error_code],3
    ret
address_read:
    mov [table+0x12],ax
    shr eax,16
    mov [table+0x14],al
    mov [table+0x17],ah
    jmp read_high
%endif
aperture_control:
    call read_high
    jc .bios_failed
    mov di,high_value
    mov cx,8
    mov ax,0xFFFF
    repe scasw
    je .empty
    call open_aperture
    jc .map_failed
    mov si,high_value
    mov di,0
    mov cx,8
    xor bp,bp
.compare:
    lodsw
    cmp ax,[es:di]
    je .next
    inc bp
.next:
    add di,2
    loop .compare
    call close_aperture
    test bp,bp
    jnz .mismatch
    clc
    ret
.map_failed:
    call close_aperture
    mov byte [error_code],1
    stc
    ret
.bios_failed:
    mov byte [error_code],3
    stc
    ret
.empty:
    mov byte [error_code],10
    stc
    ret
.mismatch:
    mov al,[control_step]
    add al,7
    mov [error_code],al
    stc
    ret

backing_result:
%ifdef MP386_TAIL_SAMPLES
    mov dl,'T'
%elifdef MP386_UPPER_ALIAS
    mov dl,'U'
%elifdef MP386_APERTURE_ADDRESS
    mov dl,'A'
%else
    mov dl,'B'
%endif
    call character
    mov al,[error_code]
    mov dl,al
    add dl,'0'
    cmp dl,'9'
    jbe .digit
    add dl,7
.digit:
    call character
    test al,al
    jnz .failed
%ifdef MP386_TAIL_SAMPLES
    jmp .end
%elifdef MP386_UPPER_ALIAS
    mov dl,'N'
    mov ax,[upper_value]
    cmp ax,[tag_value]
    jne .kind
    mov dl,'P'
    mov ax,[high_values+2]
    cmp ax,[high_values]
    je .kind
    mov dl,'B'
    cmp ax,[tag_value]
    je .kind
    mov dl,'U'
.kind:
    call character
    jmp .end
%elifdef MP386_APERTURE_ADDRESS
    jmp .end
%else
    mov dl,'R'
    mov ax,[high_values+2]
    cmp ax,[tag_value]
    je .kind
    mov dl,'H'
    cmp ax,[high_values]
    je .kind
    mov dl,'U'
.kind:
    call character
    jmp .end
%endif
.failed:
%ifdef MP386_TAIL_SAMPLES
    cmp al,1
    je .guard
    mov dl,'-'
    call character
    mov ax,[target_page]
    call hex16
    jmp .end
.guard:
%endif
    cmp al,1
    jne .end
    mov dl,'-'
    call character
    movzx ax,byte [guard_step]
    call hex16
.end:
    mov dx,line_end
    jmp message
%endif
guard_report:
    mov dx,guard_label
    call message
    movzx ax,byte [guard_step]
    call hex16
    mov dx,expected_label
    call message
    mov eax,[guard_expected]
    call hex32
    mov dx,actual_label
    call message
    mov eax,[guard_actual]
    call hex32
    mov dx,line_end
    call message
    mov dx,ti_label
    call message
    mov si,last_ti
    mov cx,2
    jmp values.next
values:
    mov cx,3
.next:
    lodsw
    call hex16
    mov dl,' '
    call character
    loop .next
    mov dx,line_end
    jmp message
hex16:
    pushad
    mov bx,ax
    mov cx,4
.digit:
    rol bx,4
    mov dl,bl
    and dl,15
    add dl,'0'
    cmp dl,'9'
    jbe .print
    add dl,7
.print:
    call character
    loop .digit
    popad
    ret
hex32:
    push eax
    shr eax,16
    call hex16
    pop eax
    jmp hex16
character:
    push ax
    mov ah,2
    int 0x21
    pop ax
    ret
message:
    push ax
    mov ah,9
    int 0x21
    pop ax
    ret

%ifdef MP386_RAM_BACKING
heading db 'MP386 hidden RAM: Before / Tagged / Restored',13,10,'$'
backing_label db 'MCU2  5FE000: $'
%else
heading db 'MP386 shadow alias: Before / Tagged / Restored',13,10,'$'
backing_label db 'Backing AE000: $'
%endif
low_label db 'Low     FE000: $'
high_label db 'High   FFE000: $'
%ifdef MP386_RAM_BACKING
restored_text db 'Original RAM word and both aperture maps restored.',13,10,'$'
%else
restored_text db 'Original padding word and aperture map restored.',13,10,'$'
%endif
error_text db 'Test error. Exit 2=tag failed, 3=BIOS read, 4=restore failed (reboot).',13,10,'$'
guard_text db 'Known bAIos ROM, 18MB topology, active F shadow and cache Off required. No tag retained.',13,10,'$'
guard_label db 'Guard $'
expected_label db ': expected $'
actual_label db ' read $'
ti_label db 'Last TI index / value: $'
placement_text db 'DOS program and stack must be below 70000. No hardware accessed.',13,10,'$'
mode_text db 'Plain real-mode DOS required. No hardware accessed.',13,10,'$'
line_end db 13,10,'$'
banks dw 16,16,64,64,64,64
saved_index dw 0
saved_map dw 0
%ifdef MP386_RAM_BACKING
target_map dw 0
tag_value dw 0
target_page dw 0x817F
copy_words dw 1
control_step db 0
%endif
%ifdef MP386_UPPER_ALIAS
upper_saved dw 0
upper_result dw 0
upper_value dw 0
upper_write db 0
upper_active db 0
upper_error db 0
%endif
backing_values times 3 dw 0
low_values times 3 dw 0
high_values times 3 dw 0
%ifdef MP386_RAM_BACKING
%ifdef MP386_APERTURE_ADDRESS
high_value times 256 dw 0
address_before times 512 db 0
address_expected times 512 db 0
address_row dw 0
address_tried db 0
address_sources:
    dd 0xA00000
    dw 0x8000
    dd 0xE00000
    dw 0x8100
    dd 0x1000000
    dw 0x8180
    dd 0x1100000
    dw 0x81C0
address_sources_end:
%else
high_value times 8 dw 0
%endif
%else
high_value dw 0
%endif
error_code db 0
guard_step db 0
guard_actual dd 0
guard_expected dd 0
last_ti dw 0
last_value dw 0
alias_roms:
ALIAS_ROM_ROWS
align 8
table:
    dq 0,0
    dw 0xFFFF,0xE000
    db 0xFF,0x93,0,0
    dw 0xFFFF,0
    db 0,0x93,0,0
    dq 0,0
