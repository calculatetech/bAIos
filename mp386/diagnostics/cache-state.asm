bits 16
org 0x100

start:
    cld
    smsw ax
    test ax,1
    jnz protected_mode
    push cs
    pop ds
    push cs
    pop es
    xor ax,ax
    mov fs,ax
    mov ax,[fs:0x413]
    mov [boot_state],ax
    mov ax,[fs:0x40E]
    mov [boot_state+2],ax
    mov ax,0x9E00
    mov fs,ax
    mov ax,[fs:0x1006]
    mov [boot_state+4],ax
    mov ax,[fs:0x1004]
    mov [boot_state+6],ax
    movzx ax,byte [fs:0x101F]
    mov [boot_state+8],ax
    movzx ax,byte [fs:0x100E]
    mov [boot_state+10],ax
    mov ax,[fs:0x101C]
    mov [boot_state+12],ax
%ifdef APPLY_CACHE_POLICY
    cmp word [boot_state],632
    jne no_policy
    cmp word [boot_state+2],0x9E00
    jne no_policy
    mov ax,0x9E00
    mov fs,ax
    cmp dword [fs:0x1004],0x5833504D
    jne no_policy
    mov al,[fs:0x101F]
    and al,6
    cmp al,6
    jne no_policy
    mov al,[fs:0x100E]
    mov di,policies
    mov cx,policies_count
    repne scasb
    jne no_policy
    mov [desired],al
    mov ax,[fs:0x101C]
    dec ax
    cmp ax,2
    ja no_policy
    pushf
    cli
    call verify_cache_rom
    jc .unknown_rom
    popf
    jmp .rom_ready
.unknown_rom:
    popf
    mov dx,rom_error
    jmp error_exit
.rom_ready:
%endif
    pushf
    cli
    in ax,0x26
    mov [saved_index],ax
    mov di,straps
    mov si,strap_ports
    mov cx,3
.straps:
    lodsb
    mov dx,ax
    and dx,0xFF
    in al,dx
    stosb
    loop .straps
    mov di,control_values
    mov si,control_indices
    mov cx,6
.controls:
    lodsb
    out 0x5A,al
    jmp short $+2
    jmp short $+2
    jmp short $+2
    in al,0x5B
    stosb
    loop .controls
    mov di,ti_values
    mov si,ti_indices
    mov cx,ti_count
.chipset:
    lodsw
    out 0x26,ax
    jmp short $+2
    in ax,0x24
    stosw
    loop .chipset
    mov ax,[saved_index]
    out 0x26,ax
%ifdef APPLY_CACHE_POLICY
    test byte [straps+2],0x80
    jnz switch_off
    test byte [control_values+2],2
    jnz mode_failed
    test byte [control_values+3],0x7F
    jnz mode_failed
    mov cx,[fs:0x101C]
    mov si,ti_values+4
.check_modes:
    cmp word [si+2],0x8100
    jne mode_failed
    add si,8
    loop .check_modes
    mov al,0x8E
    out 0x70,al
    in al,0x84
    in al,0x71
    mov [rtc_diagnostic],al
    call cmos_checksum_acknowledge
    jc checksum_failed
    mov al,0x8E
    out 0x70,al
    in al,0x84
    in al,0x71
    mov [rtc_after],al
%ifdef CACHE_LOW_TEST
    ; Supply the OEM's 256KiB selector input, then restore the real BDA value.
    xor ax,ax
    mov gs,ax
    mov word [gs:0x413],256
%endif
    ; Near RET in the verified ROM owner reaches its IRET, then this DOS frame.
    pushf
    push cs
    push word .rom_return
    push word [rom_iret]
    jmp far [cs:rom_entry]
.rom_return:
    push cs
    pop ds
%ifdef CACHE_LOW_TEST
    mov ax,[boot_state]
    mov [gs:0x413],ax
%endif
    mov al,[fs:0x100E]
    mov [used],al
    mov al,0xE0
    out 0x5A,al
    jmp short $+2
    jmp short $+2
    jmp short $+2
    in al,0x5B
    mov [after],al
    mov al,0xE2
    out 0x5A,al
    jmp short $+2
    jmp short $+2
    jmp short $+2
    in al,0x5B
    mov [after+1],al
    mov al,0x0D
    out 0x70,al
%endif
    popf

    mov dx,heading
    call message
    call boot_report
    mov dx,strap_label
    call message
    mov si,straps
    mov cx,3
    call byte_values
    mov dx,control_label
    call message
    mov si,control_values
    mov cx,6
    call byte_values
    mov dx,atu_label
    call message
    mov si,ti_values
    mov cx,2
    call word_values
    mov dx,mcu_label
    call message
    mov bx,3
.mcu_line:
    mov cx,4
    call word_values
    dec bx
    jnz .mcu_line
%ifdef APPLY_CACHE_POLICY
    call diagnostic_report
%endif
    mov dx,complete
    call message
%ifdef APPLY_CACHE_POLICY
    mov al,[desired]
    call hex8
    mov dx,used_label
    call message
    mov al,[used]
    call hex8
    mov dx,after_label
    call message
    mov si,after
    mov cx,2
    call byte_values
    mov dx,run_benchmark
    cmp byte [used],0
    jne .request_report
    mov dx,gate_blocked
.request_report:
    call message
%endif
    mov ax,0x4C00
    int 0x21
%ifdef APPLY_CACHE_POLICY
checksum_failed:
    mov al,0x0D
    out 0x70,al
    popf
    call diagnostic_report
    mov dx,checksum_error
    jmp error_exit
switch_off:
    mov dx,switch_error
    jmp refused
mode_failed:
    mov dx,map_error
refused:
    popf
    jmp error_exit
no_policy:
    call boot_report
    mov dx,policy_error
error_exit:
    call message
    mov ax,0x4C02
    int 0x21

diagnostic_report:
    mov dx,diagnostic_label
    call message
    mov al,[rtc_diagnostic]
    call hex8
    cmp byte [rtc_after],0xFF
    je .done
    mov dx,diagnostic_after
    call message
    mov al,[rtc_after]
    call hex8
.done:
    jmp newline

%include "pc/cmos-checksum.inc"

; Select only a known complete ROM and verify every cache-owner byte we call.
verify_cache_rom:
    mov ax,0xF000
    mov gs,ax
    xor ebx,ebx
    xor si,si
.sum:
    movzx eax,byte [gs:si]
    add ebx,eax
    inc si
    jnz .sum
    mov di,cache_roms
    mov cx,cache_rom_count
.candidate:
    cmp ebx,[di]
    je .matched
    add di,12
    loop .candidate
    stc
    ret
.matched:
    mov ax,[di+4]
    mov [rom_entry],ax
    mov ax,[di+6]
    mov [rom_iret],ax
    mov bx,[di+8]
    mov bp,[di+10]
    push es
    mov ax,0xF000
    mov es,ax
.span:
    mov di,[bx]
    mov cx,[bx+2]
    lea si,[bx+4]
    repe cmpsb
    jne .bad
    mov bx,si
    dec bp
    jnz .span
    pop es
    clc
    ret
.bad:
    pop es
    stc
    ret

%include "rom-cache-owner.inc"
%endif
protected_mode:
    mov dx,mode_error
    call message
    mov ax,0x4C01
    int 0x21

boot_report:
    mov dx,boot_label
    call message
    mov si,boot_state
    mov cx,7
    jmp word_values

byte_values:
    lodsb
    call hex8
    call space
    loop byte_values
    jmp newline
word_values:
    lodsw
    xchg al,ah
    call hex8
    xchg al,ah
    call hex8
    call space
    loop word_values
newline:
    push dx
    mov dx,line_end
    call message
    pop dx
    ret
space:
    push ax
    push dx
    mov ah,2
    mov dl,' '
    int 0x21
    pop dx
    pop ax
    ret
hex8:
    push ax
    push bx
    push cx
    push dx
    mov bl,al
    mov cx,2
.digit:
    rol bl,4
    mov dl,bl
    and dl,15
    add dl,'0'
    cmp dl,'9'
    jbe .print
    add dl,7
.print:
    mov ah,2
    int 0x21
    loop .digit
    pop dx
    pop cx
    pop bx
    pop ax
    ret
message:
    push ax
    mov ah,9
    int 0x21
    pop ax
    ret

%ifdef APPLY_CACHE_POLICY
%ifdef CACHE_LOW_TEST
heading db 'MP386 low-memory cache test - OEM 256KiB selector',13,10,'$'
%else
heading db 'MP386 cache request - snapshot before request',13,10,'$'
%endif
complete:
    db 'Stored policy $'
%else
heading db 'MP386 cache state - data reads only',13,10,'$'
complete db 'No configuration data changed.',13,10,'$'
%endif
strap_label db 'PORT 49/5E/5F: $'
control_label db 'CONTROL E0/E1/E2/92/E6/E7: $'
atu_label db 'ATU ID/CTRL3: $'
mcu_label db 'MCU ID / MODE / CTRL / SHADOW:',13,10,'$'
boot_label db 'BOOT KB/EBDA/magic-hi/lo/flags/policy/MCUs: $'
boot_state times 7 dw 0
mode_error db 'Run in plain real-mode DOS. No hardware accessed.',13,10,'$'
line_end db 13,10,'$'
strap_ports db 0x49,0x5E,0x5F
straps times 3 db 0
control_indices db 0xE0,0xE1,0xE2,0x92,0xE6,0xE7
control_values times 6 db 0
ti_indices dw 0x800,0x803,0,2,3,7,0x100,0x102,0x103,0x107,0x200,0x202,0x203,0x207
ti_count equ ($-ti_indices)/2
ti_values times ti_count dw 0
saved_index dw 0
%ifdef APPLY_CACHE_POLICY
policies db 0,0x03,0x23,0x33,0x43,0x53,0x63,0x69,0x6B,0x7B
policies_count equ $-policies
desired db 0
used db 0
rtc_diagnostic db 0
rtc_after db 0xFF
after times 2 db 0
diagnostic_label db 'CMOS diagnostic 0E: $'
diagnostic_after db ' -> $'
checksum_error db 'AT CMOS checksum invalid or not acknowledged. Cache request skipped.',13,10,'$'
rom_error db 'Unknown or changed bAIos ROM. No hardware changed.',13,10,'$'
rom_entry dw 0,0xF000
rom_iret dw 0
used_label db '; requested $'
after_label db '; after E0/E2: $'
run_benchmark db 'Run the same benchmark now.',13,10
%ifdef CACHE_LOW_TEST
    db 'RAM size restored. Run TGENABLE to restore the normal cache policy.',13,10
%endif
    db '$'
gate_blocked db 'Diagnostic gate kept cache off. Report this output.',13,10,'$'
policy_error db 'No qualified bAIos cache policy. No hardware changed.',13,10,'$'
switch_error db 'Cache switch is Off. No configuration data changed.',13,10,'$'
map_error db 'Unexpected memory mode. No configuration data changed.',13,10,'$'
%endif
