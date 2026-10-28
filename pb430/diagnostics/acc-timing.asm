bits 16
cpu 386
org 0x100

%ifdef ACC_PROFILE
%include "acc-profile.inc"
%else
%macro timing_write 1
    mov al,[cs:target_index]
    out 0xF2,al
    out 0xED,al
    mov al,%1
    out 0xF3,al
    out 0xED,al
%endmacro
%endif

%macro pit_sample 0
    xor al,al
    out 0x43,al
    in al,0x40
    mov ah,al
    in al,0x40
    xchg ah,al
%endmacro

start:
    push cs
    pop ds
    push cs
    pop es
    cld
    mov si,0x81
    movzx cx,byte [0x80]
    mov bl,5
%ifdef ACC_PROFILE
    xor bl,bl
    mov byte [stock_value],4
    mov byte [refresh_trial],1
    jmp .trailing
%endif
%ifdef ACC_ORDER
    mov byte [target_index],0x18
    jmp .trailing
%endif
.argument:
    test cx,cx
    jz .parsed
    lodsb
    dec cx
    cmp al,' '
    je .argument
    cmp al,'W'
    je .write_trial
    cmp al,'w'
    je .write_trial
    cmp al,'C'
    je .cas
    cmp al,'c'
    je .cas
    cmp al,'R'
    je .reference
    cmp al,'r'
    je .reference
    cmp al,'T'
    je .timing
    cmp al,'t'
    je .timing
    cmp al,'S'
    je .sampling
    cmp al,'s'
    je .sampling
    cmp al,'H'
    je .hidden
    cmp al,'h'
    je .hidden
    cmp al,'D'
    je .dram
    cmp al,'d'
    je .dram
    cmp al,'F'
    je .refresh
    cmp al,'f'
    je .refresh
    cmp al,'4'
    je .choice
    cmp al,'5'
    jne refused
.choice:
    sub al,'0'
    mov bl,al
    jmp .trailing
.write_trial:
    jcxz .write_refused
    lodsb
    dec cx
    cmp al,'4'
    je .write_ready
    cmp al,'5'
    jne .write_refused
.write_ready:
    mov byte [write_trial],1
    mov dword [access_text],'Writ'
    mov byte [access_text+4],'e'
    jmp .choice
.write_refused:
    jmp refused
.cas:
    mov bl,0x19
    jcxz .trailing
    cmp byte [si],'1'
    jne .trailing
    jmp retired_cas
.reference:
    mov bl,0x92
    mov byte [target_index],1
    mov byte [stock_value],0x93
    mov byte [readback_or],0x2C
    jmp .trailing
.timing:
    mov bl,0x10
    jmp .timing_ready
.sampling:
    mov bl,0x20
    jmp .timing_ready
.hidden:
    mov bl,2
    mov byte [refresh_trial],1
    mov byte [hidden_refresh],1
.timing_ready:
    mov byte [target_index],0x18
    mov byte [stock_value],0
    jmp .trailing
.dram:
    jmp retired_dram
.refresh:
    cmp cx,0
    je refused
    lodsb
    dec cx
    mov bl,0x9D
    cmp al,'2'
    je .refresh_ready
    inc bl
    cmp al,'4'
    je .refresh_ready
    inc bl
    cmp al,'8'
    jne refused
.refresh_ready:
    mov byte [target_index],5
    mov byte [stock_value],0x9C
    mov byte [refresh_trial],1
.trailing:
    jcxz .parsed
    lodsb
    dec cx
    cmp al,' '
    je .trailing
    jmp refused
.parsed:
    mov [candidate],bl
    smsw ax
    test al,1
    jnz refused
    mov eax,cr0
    test eax,0x60000000
    jnz refused
    mov ax,0x4300
    int 0x2F
    cmp al,0x80
    je refused
    mov ah,0x88
    int 0x15
    jc refused
    cmp ax,4096
    jb refused

    pushf
    cli
    in al,0xF2
    mov [saved_index],al
    in al,0x78
    and al,7
    cmp al,5
    jne .bad_board
    mov si,guards
    mov cx,(guards_end-guards)/2
.guard:
    lodsb
    call acc_read
    cmp al,[si]
    jne .bad_board
    inc si
    loop .guard
    ; Preserve accepted Setup choices unless this command tests their register.
    mov al,5
    call acc_read
    mov [baseline_refresh],al
    cmp al,0x9C
    je .refresh_ready_guard
    cmp byte [target_index],5
    je .bad_board
    cmp al,0x9F
    jne .bad_board
.refresh_ready_guard:
    mov al,0x0B
    call acc_read
    mov [baseline_write_timing],al
    cmp al,0x15
    je .write_ready_guard
    cmp byte [target_index],0x0B
%ifndef ACC_PROFILE
    je .bad_board
%endif
    cmp al,4
    jne .bad_board
.write_ready_guard:
    cmp byte [hidden_refresh],0
    je .hidden_ready
    mov al,0x19
    call acc_read
    mov [refresh_configuration],al
    test al,0xF7
    jnz .bad_refresh
.hidden_ready:
%ifdef ACC_ORDER
    mov al,4
    call acc_read
    mov ah,al
    and al,0xFE
    cmp al,0x14
    jne .bad_board
    and ah,1
    mov [order_l2],ah
    mov al,0x1A
    call acc_read
    mov ah,0x24
    cmp byte [order_l2],1
    je .l2_pair
    mov ah,0x2C
    mov word [order_l2_text],'Of'
    mov byte [order_l2_text+2],'f'
.l2_pair:
    cmp al,ah
    jne .bad_board
%endif
    ; Require the reference size pair; a ROM entry alone is not board support.
    mov al,0x1D
    call acc_read
    mov bl,0x7B
    cmp al,0xF0
    je .size_ready
    cmp al,0xFC
    jne .bad_board
    mov bl,0x79
    mov word [cache_text],'12'
    mov byte [cache_text+2],'8'
.size_ready:
%ifdef ACC_ORDER
    cmp byte [order_l2],1
    je .cache_state_ready
    and bl,0xDF
.cache_state_ready:
%endif
    mov al,0x1E
    call acc_read
    cmp al,bl
    jne .bad_board
    ; Read status only: channel 0 must have the standard binary mode-3 clock.
    mov al,0xE2
    out 0x43,al
    in al,0x40
    and al,0x7F
    cmp al,0x36
    jne .bad_board
    mov al,[saved_index]
    out 0xF2,al
    out 0xED,al
    popf

    xor eax,eax
    mov ax,cs
    mov [real_jump+3],ax
    shl eax,4
    mov [code_descriptor+2],ax
    mov [data_descriptor+2],ax
    mov edx,eax
    shr edx,16
    mov [code_descriptor+4],dl
    mov [data_descriptor+4],dl
    add eax,gdt
    mov [new_gdtr+2],eax
    mov al,[baseline_write_timing]
    mov di,baseline_write_text
    call hex_byte
    mov al,[baseline_refresh]
    mov di,baseline_refresh_text
    call hex_byte
    mov dx,intro
    mov cx,intro_end-intro
    call stdout
    jc output_failed
    cmp byte [refresh_trial],0
    je .begin
    mov dx,refresh_notice
    mov cx,refresh_notice_end-refresh_notice
    call stdout
    jc output_failed
.begin:
%ifdef ACC_ORDER
    call order_main
%else
    mov al,[stock_value]
    mov [setting],al
    call phase
    jc test_failed
    call report
    jc output_failed
    mov al,[candidate]
    mov [setting],al
    call phase
    jc test_failed
    call report
    jc output_failed
    mov al,[stock_value]
    mov [setting],al
    call phase
    jc test_failed
    call report
    jc output_failed
%endif
    mov ax,0x4C00
    int 0x21
.bad_refresh:
    mov al,[saved_index]
    out 0xF2,al
    out 0xED,al
    popf
    mov al,[refresh_configuration]
    mov di,refresh_configuration_text
    call hex_byte
    mov dx,refresh_refusal
    mov cx,refresh_refusal_end-refresh_refusal
    call stdout
    mov ax,0x4C02
    int 0x21
.bad_board:
    mov al,[saved_index]
    out 0xF2,al
    out 0xED,al
    popf
    jmp refused
retired_dram:
    mov dx,dram_retired
    mov cx,dram_retired_end-dram_retired
    jmp retired_exit
retired_cas:
    mov dx,retired
    mov cx,retired_end-retired
retired_exit:
    call stdout
    mov ax,0x4C02
    int 0x21
refused:
    mov dx,refusal
    mov cx,refusal_end-refusal
    call stdout
    mov ax,0x4C02
    int 0x21
output_failed:
    mov ax,0x4C03
    int 0x21
test_failed:
%ifndef ACC_ORDER
    mov al,[target_index]
    mov di,failure_register
    call hex_byte
    mov al,[setting]
    mov di,failure_setting
    call hex_byte
%endif
    mov dx,failure_phase
    mov cx,failure_phase_end-failure_phase
    call stdout
    jc output_failed
%ifdef ACC_ORDER
    cmp byte [failure_kind],4
    je .pointer
%endif
    cmp byte [failure_kind],1
    je .a20
    cmp byte [failure_kind],2
    je .register
    cmp byte [failure_kind],3
    je .memory
    mov dx,failure_timer
    mov cx,failure_timer_end-failure_timer
    jmp .reason
%ifdef ACC_ORDER
.pointer:
    mov eax,[failure_actual]
    mov di,order_bad_pointer
    call hex_dword
    mov dx,order_pointer_failure
    mov cx,order_pointer_failure_end-order_pointer_failure
    jmp .reason
%endif
.a20:
    mov dx,failure_a20
    mov cx,failure_a20_end-failure_a20
    jmp .reason
.register:
%ifdef ACC_PROFILE
    mov al,[profile_failure_index]
    mov di,profile_index_text
    call hex_byte
%endif
    mov al,[failure_readback+1]
    mov di,failure_wanted
    call hex_byte
    mov al,[failure_readback]
    mov di,failure_got
    call hex_byte
    mov dx,failure_reg
    mov cx,failure_reg_end-failure_reg
    jmp .reason
.memory:
    mov eax,[failure_address]
    mov di,failure_address_text
    call hex_dword
    mov eax,[failure_expected]
    mov di,failure_expected_text
    call hex_dword
    mov eax,[failure_actual]
    mov di,failure_actual_text
    call hex_dword
    mov dx,failure_ram
    mov cx,failure_ram_end-failure_ram
.reason:
    call stdout
    jc output_failed
    mov dx,failure
    mov cx,failure_end-failure
    call stdout
    jc output_failed
    mov ax,0x4C01
    int 0x21

acc_read:
    out 0xF2,al
    out 0xED,al
    in al,0xF3
    out 0xED,al
    ret

; Only scratch memory at 1-5 MiB is written. Each chunk returns at stock timing.
phase:
%ifndef ACC_ORDER
    mov al,[target_index]
    mov di,pending_register
    call hex_byte
    mov al,[setting]
    mov di,pending_setting
    call hex_byte
    mov dx,pending
    mov cx,pending_end-pending
    call stdout
    jc output_failed
%endif
    mov byte [failed],0
    mov byte [failure_kind],0
    mov byte [measured_write],0
    mov dword [ticks],0
    pushf
    pop ax
    mov [saved_flags],ax
    cli
    o32 sgdt [old_gdtr]
    in al,0x92
    mov [saved_a20],al
    and al,0xFE
    or al,2
    out 0x92,al
    in al,0x61
    mov [saved_parity],al
    or al,0x0C
    out 0x61,al
%ifdef ACC_ORDER
    call order_run
%else
    mov dword [pattern],0xA55AA55A
.patterns:
    mov byte [operation],0
    call sweep
    jc .done
    cmp byte [refresh_trial],0
    je .verify_pattern
    ; A full read sweep evicts dirty cache lines before the retention wait.
    mov byte [operation],4
    call sweep
    jc .done
    mov byte [operation],3
    call sweep
    jc .done
.verify_pattern:
    mov byte [operation],1
    call sweep
    jc .done
    not dword [pattern]
    cmp dword [pattern],0xA55AA55A
    jne .patterns
    not dword [pattern]
    mov al,[write_trial]
    mov [measured_write],al
    mov byte [passes],4
    mov byte [operation],2
.measure:
    call sweep
    jc .done
    dec byte [passes]
    jnz .measure
    mov byte [operation],1
    call sweep
%endif
.done:
    cli
    o32 lgdt [old_gdtr]
    mov al,[saved_a20]
    and al,0xFE
    out 0x92,al
    mov al,[saved_parity]
    out 0x61,al
    mov al,[saved_index]
    out 0xF2,al
    out 0xED,al
    push word [saved_flags]
    popf
    cmp byte [failed],0
    jne .bad
    cmp dword [ticks],0
    je .bad
    clc
    ret
.bad:
    stc
    ret

sweep:
    mov dword [address],0x100000
.chunk:
    cli
    o32 lgdt [new_gdtr]
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp 0x08:protected_chunk
real_chunk:
    push cs
    pop ds
    push cs
    pop es
    o32 lgdt [old_gdtr]
    push word [saved_flags]
    popf
    nop
    cmp byte [failed],0
    jne .bad
    cmp byte [operation],3
    je .done
    add dword [address],0x4000
    cmp dword [address],0x500000
    jb sweep.chunk
.done:
    clc
    ret
.bad:
    stc
    ret

protected_chunk:
    mov ax,0x10
    mov es,ax
    mov ax,0x18
    mov ds,ax
    cld
    cmp dword [cs:address],0x100000
    jne .a20_ready
    cmp byte [cs:operation],0
    jne .a20_ready
    ; Prove the gate before a failed A20 request can alias writes into DOS.
    mov esi,0x500
    mov edi,0x100500
    mov eax,[es:esi]
    mov edx,[es:edi]
    mov dword [es:esi],0
    mov dword [es:edi],0xFFFFFFFF
    cmp dword [es:esi],0
    mov [es:edi],edx
    mov [es:esi],eax
    jne .a20_bad
.a20_ready:
%ifdef ACC_ORDER
%include "acc-order-kernel.inc"
%else
    mov al,[cs:operation]
    add al,0xB0
    out 0x80,al
    mov bl,[cs:setting]
    timing_write bl
    ; timing_write already selected this register; avoid a stack access here.
    in al,0xF3
    out 0xED,al
    mov ah,bl
    or ah,[cs:readback_or]
    cmp al,ah
    jne .register_bad
    cmp byte [cs:operation],3
    je .retention
    mov edi,[cs:address]
    mov ecx,0x1000
    cmp byte [cs:operation],2
    je .read
    cmp byte [cs:operation],4
    je .evict
    mov edx,[cs:pattern]
    cmp byte [cs:operation],1
    je .verify
.write:
    mov eax,edi
    xor eax,edx
    a32 stosd
    loop .write,ecx
    jmp .restore
.verify:
    mov eax,edi
    xor eax,edx
    cmp byte [cs:measured_write],0
    je .expected_ready
    mov eax,edx
.expected_ready:
    mov ebx,[es:edi]
    cmp ebx,eax
    jne .memory_bad
    add edi,4
    loop .verify,ecx
    jmp .restore
.read:
    mov esi,edi
    pit_sample
    mov dx,ax
    cmp byte [cs:write_trial],0
    je .timed_read
    mov eax,[cs:pattern]
    a32 rep stosd
    jmp .timed_done
.timed_read:
    a32 es rep lodsd
.timed_done:
    pit_sample
    sub dx,ax
    movzx esi,dx
    jmp .restore
.evict:
    mov esi,edi
    a32 es rep lodsd
    jmp .restore
.retention:
    ; Mode-3 PIT counts twice per clock; poll often enough to count wraps.
    xor ecx,ecx
%ifdef ACC_PROFILE
    mov ebp,0x10000
%endif
    pit_sample
    mov dx,ax
.wait:
    pit_sample
    sub dx,ax
%ifdef ACC_PROFILE
    jnz .timer_progress
    dec ebp
    jnz .timer_ready
    mov bp,4
    jmp .bad
.timer_progress:
    mov ebp,0x10000
.timer_ready:
%endif
    movzx ebx,dx
    add ecx,ebx
    mov dx,ax
    cmp ecx,2*1193182
    jb .wait
.restore:
    ; Restore immediately, before any interrupt, BIOS call, or DOS output.
    timing_write [cs:stock_value]
    ; timing_write already selected this register; avoid a stack access here.
    in al,0xF3
    out 0xED,al
    mov ah,[cs:stock_value]
    or ah,[cs:readback_or]
    cmp al,ah
    jne .restore
    mov al,0xBE
    out 0x80,al
    cmp byte [cs:operation],2
    jne .return
    ; Commit local state only after the stock setting reads back correctly.
    add [ds:ticks],esi
    jmp .return
.a20_bad:
    mov bp,1
    jmp .bad
.register_bad:
    mov si,ax
%ifdef ACC_PROFILE
    in al,0xF2
    movzx ebp,al
    shl ebp,16
%endif
    mov bp,2
    jmp .bad
.memory_bad:
    mov esi,eax
    mov bp,3
.bad:
    timing_write [cs:stock_value]
    ; timing_write already selected this register; avoid a stack access here.
    in al,0xF3
    out 0xED,al
    mov ah,[cs:stock_value]
    or ah,[cs:readback_or]
    cmp al,ah
    jne .bad
    mov al,0xBF
    out 0x80,al
    ; Keep evidence in registers until the stock timing readback succeeds.
    mov [ds:failure_readback],si
    mov [ds:failure_address],edi
    mov [ds:failure_expected],esi
    mov [ds:failure_actual],ebx
%ifdef ACC_PROFILE
    mov eax,ebp
    shr eax,16
    mov [ds:profile_failure_index],al
%endif
    mov dx,bp
    mov [ds:failure_kind],dl
    mov byte [ds:failed],1
%endif
.return:
    mov ax,0x18
    mov ds,ax
    mov es,ax
    mov eax,cr0
    and al,0xFE
    mov cr0,eax
real_jump:
    jmp 0:real_chunk

report:
%ifdef ACC_ORDER
    ; Four traversals, each reading 1 MiB of useful pointer bytes.
    mov eax,4*10*2*1193182
%else
    mov al,[target_index]
    mov di,register_text
    call hex_byte
    mov al,[setting]
    mov di,setting_text
    call hex_byte
    ; 16 MiB, tenths of MiB/s; mode 3 decrements twice per PIT clock.
    mov eax,16*10*2*1193182
%endif
    xor edx,edx
    div dword [ticks]
    mov di,speed_text+6
    mov bx,10
    mov cx,7
.number:
    cmp cx,6
    jne .digit
    mov byte [di],'.'
    jmp .next
.digit:
    xor edx,edx
    movzx ebx,bx
    div ebx
    add dl,'0'
    mov [di],dl
.next:
    dec di
    loop .number
    mov di,speed_text
    mov cx,4
.spaces:
    cmp byte [di],'0'
    jne .print
    mov byte [di],' '
    inc di
    loop .spaces
.print:
    mov dx,result
    mov cx,result_end-result
    jmp stdout

stdout:
    mov bx,1
    mov ah,0x40
    int 0x21
    jc .done
    cmp ax,cx
    je .done
    stc
.done:
    ret

hex_dword:
    push cx
    mov cx,4
.byte:
    rol eax,8
    call hex_byte
    loop .byte
    pop cx
    ret

hex_byte:
    push ax
    mov ah,al
    shr al,4
    call .digit
    mov al,ah
    and al,15
    call .digit
    pop ax
    ret
.digit:
    cmp al,9
    jbe .number
    add al,7
.number:
    add al,'0'
    stosb
    ret

%ifdef ACC_ORDER
%include "acc-order.inc"
guards db 0x00,0xA9, 0x01,0xBF, 0x06,0xB7, 0x12,0x09, 0x18,0x00
%else
guards db 0x00,0xA9, 0x01,0xBF, 0x04,0x15, 0x06,0xB7
    db 0x12,0x09, 0x18,0x00, 0x1A,0x24
%ifdef ACC_PROFILE
    db 0x05,0x9F, 0x0B,0x04, 0x14,0x06, 0x16,0x00, 0x19,0x08
%endif
%endif
guards_end:
align 8
gdt dq 0
code_descriptor dq 0x00009A000000FFFF
    dq 0x00CF92000000FFFF
data_descriptor dq 0x000092000000FFFF
new_gdtr dw $-gdt-1
    dd 0
old_gdtr times 6 db 0
saved_flags dw 0
saved_index db 0
%ifdef ACC_PROFILE
profile_failure_index db 0
%endif
saved_a20 db 0
saved_parity db 0
candidate db 5
target_index db 0x0B
stock_value db 0x15
readback_or db 0
refresh_trial db 0
hidden_refresh db 0
refresh_configuration db 0
write_trial db 0
measured_write db 0
baseline_refresh db 0
baseline_write_timing db 0
setting db 0x15
operation db 0
failed db 0
failure_kind db 0
failure_readback dw 0
failure_address dd 0
failure_expected dd 0
failure_actual dd 0
passes db 0
address dd 0
pattern dd 0
ticks dd 0
%ifdef ACC_ORDER
intro db 'PB430 address-order check; no chipset configuration writes.',13,10
    db 'L2: '
order_l2_text db 'On '
    db '  Cache setting: '
cache_text db '512 KiB.',13,10
    db 'Starting settings: 0B='
baseline_write_text db '00 05='
baseline_refresh_text db '00.',13,10
    db 'One pointer per 16-byte line, 1-5 MiB; four timed traversals.',13,10
    db 'Useful-byte MiB/s includes pointer checks and loop overhead.',13,10
    db 'This is address-order throughput, not intrinsic RAM latency.',13,10
intro_end:
%else
%ifdef ACC_PROFILE
intro db 'PB430 combined 33 MHz / 60 ns timing experiment.',13,10
    db 'Baseline: 01=93 0B=04 16=00 19=08. Slow Refresh stays on.',13,10
    db 'Trial:    01=83 0B=00 16=03 19=28.',13,10
    db 'CAS advance plus shorter read pulse; RAS timeout; refresh precharge.',13,10
    db 'Every chunk restores all four baseline registers.',13,10
    db 'L2 configuration: '
%else
intro db 'PB430 timing probe: RAM check and 16 MiB transfer; baseline restored per result.',13,10
    db 'L2 configuration: '
%endif
cache_text db '512 KiB.',13,10
    db 'Starting settings: 0B='
baseline_write_text db '00 05='
baseline_refresh_text db '00.'
%ifdef ACC_PROFILE
    db ' Combined profile shown above.',13,10
%else
    db ' Only the selected register changes.',13,10
%endif
    db 'Trial is temporary. A lock requires a hard reset or power cycle.',13,10
intro_end:
%endif
refresh_notice db 'Refresh test includes 1-second waits. DOS clock may lose several seconds.',13,10
refresh_notice_end:
pending db 'Testing '
pending_register db '00='
pending_setting db '00',13,10
pending_end:
%ifdef ACC_ORDER
result:
order_name db 'Linear   '
    db ' '
speed_text db '00000.0 useful MiB/s; pointer check OK.',13,10
result_end:
; Unreachable legacy argument parser references these labels.
register_text db '00='
setting_text db '00 '
access_text db 'Read '
%else
result:
register_text db '0B='
setting_text db '00  '
access_text db 'Read '
    db ' '
speed_text db '00000.0 MiB/s  RAM check OK; baseline restored.',13,10
result_end:
%endif
%ifdef ACC_ORDER
refusal db 'Requires PB430, L1 on, supported 128K/512K cache settings and plain DOS (F5).',13,10
    db 'Run ACCORDER without arguments. L2 may be enabled or disabled in Setup.',13,10
refusal_end:
%else
%ifdef ACC_PROFILE
refusal db 'ACCPROF needs plain DOS (F5), L1+L2, Fast Writes and Slow Refresh on.',13,10
    db 'Run without arguments. Requires the captured ACCNOW register state.',13,10
refusal_end:
%else
refusal db 'Requires PB430, L1+128K/512K L2, supported settings, and plain DOS (F5).',13,10
    db 'Use W5/W4 (writes), H, S, T, F2/F4/F8, R, C, 5 or 4 (reads).',13,10
    db 'For 0B trials disable Fast Memory Writes. For F trials disable Slow Refresh.',13,10
refusal_end:
%endif
%endif
refresh_refusal db 'H refused: register19='
refresh_configuration_text db '00. Requires (19 AND F7)=00; no timing writes.',13,10
refresh_refusal_end:
retired db 'C1 withdrawn after hardware failure. Keep stock timing.',13,10
retired_end:
dram_retired db 'D withdrawn after hardware lock. Keep DRAM burst enabled.',13,10
dram_retired_end:
%ifdef ACC_ORDER
failure_phase db 'FAILED: '
failure_phase_end:
%else
failure_phase db 'FAILED at '
failure_register db '00='
failure_setting db '00: '
failure_phase_end:
%endif
%ifdef ACC_PROFILE
failure_reg db 'register '
profile_index_text db '00 readback; wanted '
%else
failure_reg db 'register readback; wanted '
%endif
failure_wanted db '00, read '
failure_got db '00.',13,10
failure_reg_end:
failure_ram db 'RAM mismatch at '
failure_address_text db '00000000',13,10
    db 'Expected '
failure_expected_text db '00000000, read '
failure_actual_text db '00000000.',13,10
failure_ram_end:
failure_a20 db 'A20 address check.',13,10
failure_a20_end:
failure_timer db 'timer did not advance.',13,10
failure_timer_end:
%ifdef ACC_ORDER
failure db 'Machine state restored. Stop this test.',13,10
%else
failure db 'Baseline timing restored. Stop tuning.',13,10
%endif
failure_end:
