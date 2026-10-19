; Independent APM1.2 consumer. Native DOS/86Box probe, never part of a flash ROM.
bits 16
org 0x100
start:
    cld
    push cs
    pop ds
    mov ax, 0x5300
    xor bx, bx
    int 0x15
    jc fail
    cmp ax, 0x0102
    jne fail
    test cx, 4
    jnz fail
%ifdef APM_DRIVER_ONLY
    jmp driver
%endif
    and cx, 3
    cmp cx, 3
    jne fail
    mov ax, 0x5301
    xor bx, bx
    int 0x15
    jc fail
    mov ax, 0x530E
    mov cx, 0x0102
    int 0x15
    jc fail
    cmp ax, 0x0102
    jne fail
    call idle_flags
    mov ax, 0x5307
    mov bx, 1
    mov cx, 2
    int 0x15
    jnc fail
    cmp ah, 0x60
    jne fail
    mov ax, 0x5310
    xor bx, bx
    int 0x15
    jc fail
    or bx, cx
    jnz fail
    call disconnect
%ifndef APM_REAL_ONLY
    mov ax, 0x5302
    xor bx, bx
    int 0x15
    jc fail
    mov [entry16], bx
    mov [code_paragraph], ax
    mov [data_paragraph], cx
    mov [code_length], si
    mov [data_length], di
    call prepare
    movzx eax, word [code_paragraph]
    shl eax, 4
    mov cx, [code_length]
    mov di, gdt+0x18
    call set_descriptor
    movzx eax, word [data_paragraph]
    shl eax, 4
    mov cx, [data_length]
    mov di, gdt+0x20
    call set_descriptor
    mov word [idt+8*8], irq16
    mov word [idt+8*8+2], 8
    mov byte [idt+8*8+5], 0x86
    lgdt [gdtr]
    lidt [idtr]
    mov eax, cr0
    or al, 1
    mov cr0, eax
    jmp 8:pm16
real16:
    call restore
    cmp byte [passed], 1
    jne fail
    call disconnect
    mov ax, 0x5303
    xor bx, bx
    int 0x15
    jc fail
    mov [entry32], ebx
    mov [code_paragraph], ax
    mov [code16_paragraph], cx
    mov [data_paragraph], dx
    mov [code_length], si
    shr esi, 16
    mov [code16_length], si
    mov [data_length], di
    call prepare
    movzx eax, word [code_paragraph]
    shl eax, 4
    mov cx, [code_length]
    mov di, gdt+0x18
    call set_descriptor
    mov byte [gdt+0x18+6], 0x40
    movzx eax, word [code16_paragraph]
    shl eax, 4
    mov cx, [code16_length]
    mov di, gdt+0x20
    call set_descriptor
    mov byte [gdt+0x20+5], 0x9A
    movzx eax, word [data_paragraph]
    shl eax, 4
    mov cx, [data_length]
    mov di, gdt+0x28
    call set_descriptor
    mov word [idt+8*8], irq32
    mov word [idt+8*8+2], 0x30
    mov byte [idt+8*8+5], 0x8E
    lgdt [gdtr]
    lidt [idtr]
    mov eax, cr0
    or al, 1
    mov cr0, eax
    jmp dword 0x30:pm32
real32:
    call restore
    cmp byte [passed], 1
    jne fail
    call disconnect
%endif
    mov dx, probe_pass
    mov ah, 9
    int 0x21
    mov bl, 0x6A
    jmp exit_vm

idle_flags:
    std
    cli
    mov ax, 0x5305
    int 0x15
    pushf
    pop bx
    cld
    sti
    test bx, 1
    jnz fail
    and bx, 0x600
    cmp bx, 0x400
    jne fail
    ret
disconnect:
    mov ax, 0x5304
    xor bx, bx
    int 0x15
    jc fail
    ret

%ifndef APM_REAL_ONLY
prepare:
    cli
    mov byte [passed], 0
    mov dword [irq_count], 0
    mov ax, sp
    add ax, 2
    mov [old_sp], ax
    sgdt [old_gdtr]
    sidt [old_idtr]
    mov ax, cs
    mov [real_target+2], ax
    movzx eax, ax
    shl eax, 4
    mov [program_base], eax
    mov di, gdt+8
    mov cx, 0                   ; 65536-byte caller code/data/stack.
    call set_descriptor
    mov eax, [program_base]
    mov di, gdt+0x10
    call set_descriptor
    mov eax, [program_base]
    mov di, gdt+0x30
    call set_descriptor
    mov eax, [program_base]
    mov di, gdt+0x38
    call set_descriptor
    mov eax, [program_base]
    add eax, gdt
    mov [gdtr+2], eax
    mov eax, [program_base]
    add eax, idt
    mov [idtr+2], eax
    in al, 0x21
    mov [pic_masks], al
    in al, 0xA1
    mov [pic_masks+1], al
    mov al, 0xFE                ; Caller OS enables only IRQ0 for its test IDT.
    out 0x21, al
    mov al, 0xFF
    out 0xA1, al
    ret
set_descriptor:
    push cx
    dec cx
    mov [di], cx
    mov [di+2], ax
    shr eax, 16
    mov [di+4], al
    mov [di+7], ah
    pop cx
    ret
restore:
    pop bx                      ; Move this helper's return to the original DOS stack.
    push cs
    pop ds
    mov ax, cs
    mov ss, ax
    mov sp, [old_sp]
    lgdt [old_gdtr]
    lidt [old_idtr]
    mov al, [pic_masks]
    out 0x21, al
    mov al, [pic_masks+1]
    out 0xA1, al
    cld
    sti
    push bx
    ret

pm16:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0xE000
    mov ax, 0x530E
    xor bx, bx
    mov cx, 0x0102
    call far [entry16]
    jc pm16_done
    mov ax, 0x530A
    mov bx, 1
    call far [entry16]
    jc pm16_done
    cmp bx, 0x01FF
    jne pm16_done
    cmp cx, 0x80FF
    jne pm16_done
    cmp dx, 0xFFFF
    jne pm16_done
    test si, si
    jnz pm16_done
    std
    mov ax, 0x5305
    call far [entry16]
    pushf
    pop ax
    cld
    and ax, 0x601
    cmp ax, 0x400
    jne pm16_done
    cmp dword [irq_count], 0
    je pm16_done
    mov byte [passed], 1
pm16_done:
    mov word [real_target], real16
    jmp real_mode
real_mode:
    cli
    mov eax, cr0
    and al, 0xFE
    mov cr0, eax
    jmp far [cs:real_target]
irq16:
    push ax
    push ds
    mov ax, 0x10
    mov ds, ax
    inc dword [irq_count]
    mov al, 0x20
    out 0x20, al
    pop ds
    pop ax
    iret

bits 32
pm32:
    mov ax, 0x38
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov esp, 0xE000
    mov ax, 0x530E
    xor bx, bx
    mov cx, 0x0102
    call far [entry32]
    jc pm32_done
    mov ax, 0x530A
    mov bx, 1
    call far [entry32]
    jc pm32_done
    cmp bx, 0x01FF
    jne pm32_done
    cmp cx, 0x80FF
    jne pm32_done
    cmp dx, 0xFFFF
    jne pm32_done
    test si, si
    jnz pm32_done
    std
    mov ax, 0x5305
    call far [entry32]
    pushfd
    pop eax
    cld
    and eax, 0x601
    cmp eax, 0x400
    jne pm32_done
    cmp dword [irq_count], 0
    je pm32_done
    mov byte [passed], 1
pm32_done:
    jmp word 8:return32
irq32:
    push eax
    push ds
    mov ax, 0x38
    mov ds, ax
    inc dword [irq_count]
    mov al, 0x20
    out 0x20, al
    pop ds
    pop eax
    iretd
bits 16
return32:
    mov word [real_target], real32
    jmp real_mode

align 8
gdt:
    dq 0
    dw 0xFFFF,0
    db 0,0x9A,0,0               ; 08:caller16.
    dw 0xFFFF,0
    db 0,0x92,0,0               ; 10:caller16data.
    dw 0,0
    db 0,0x9A,0,0               ; 18:APMcode16/32.
    dw 0,0
    db 0,0x92,0,0               ; 20:APMdata16/code16.
    dw 0,0
    db 0,0x92,0,0               ; 28:APMdata32.
    dw 0xFFFF,0
    db 0,0x9A,0x40,0            ; 30:caller32.
    dw 0xFFFF,0
    db 0,0x92,0x40,0            ; 38:caller32data/stack.
gdt_end:
gdtr: dw gdt_end-gdt-1
      dd 0
idt: times 9*8 db 0
idtr: dw 9*8-1
      dd 0
old_gdtr: times 6 db 0
old_idtr: times 6 db 0
program_base: dd 0
real_target: dw 0,0
entry16: dw 0,0x18
entry32: dd 0
         dw 0x18
code_paragraph: dw 0
code16_paragraph: dw 0
data_paragraph: dw 0
code_length: dw 0
code16_length: dw 0
data_length: dw 0
old_sp: dw 0
pic_masks: dw 0
irq_count: dd 0
passed: db 0
%endif

%ifdef APM_DRIVER_ONLY
driver:
    test cx, 8
    jnz fail
    call driver_context
    mov ax, 0x5400              ; Independent DOS POWER installation interface.
    xor bx, bx
    int 0x2F
    cmp bx, 0x504D
    jne fail
    cmp ah, 1
    jne fail
    mov ax, 0x5401
    mov bx, 0x0103              ; Enable both driver and APM firmware power management.
    int 0x2F
    test ax, ax
    jnz fail
    cmp bl, 3
    jne fail
    mov dx, installed
    mov ah, 9
    int 0x21
    call snapshot
    mov [idle_before], eax
    mov ax, 0x351C
    int 0x21
    mov [old_tick], bx
    mov [old_tick+2], es
    mov dx, tick_hook
    mov ax, 0x251C
    int 0x21
    mov word [countdown], 36
    mov dx, prompt
    mov ah, 9
    int 0x21
    mov ah, 8                   ; Real DOS wait lets POWER's idle hook call BIOS.
    int 0x21
    cmp al, 13
    jne fail
    push ds
    lds dx, [old_tick]
    mov ax, 0x251C
    int 0x21
    pop ds
    call snapshot
    sub eax, [idle_before]
    jz fail
    mov [idle_delta], eax
    cmp edx, [es:0x27D]
    jne fail                    ; Every observed HLT returned from its interrupt.
    call driver_context
    mov dx, driver_pass
    mov ah, 9
    int 0x21
    mov bl, 0x6B
    jmp exit_vm
driver_context:
    pusha
    smsw ax                     ; Intel386 reference: CR0.PE, readable in virtual86.
    test al, 1
%ifdef APM_MANAGERS
    jz fail                     ; This DOS consumer never enables protected mode.
    mov ax, 0x4300              ; Independent XMS installation check for HIMEM.
    int 0x2F
    cmp al, 0x80
    jne fail
    mov dx, context_managed
%else
    jnz fail
    mov dx, context_real
%endif
    mov ah, 9
    int 0x21
    popa
    ret
snapshot:
    mov ax, 0x40
    mov es, ax
    mov ax, [es:0xE]
    mov es, ax
    mov eax, [es:0x27D]
    mov edx, [es:0x281]
    ; Outputs:EAX entries,EDX wakes,ES current EBDA.
    ret
tick_hook:
    push ax
    push cx
    cmp word [cs:countdown], 0
    je .chain
    dec word [cs:countdown]
    jnz .chain
    mov cx, 0xFFFF
.ready1:
    in al, 0x64
    test al, 2
    jz .command
    loop .ready1
    jmp .chain
.command:
    mov al, 0xD2
    out 0x64, al
    mov cx, 0xFFFF
.ready2:
    in al, 0x64
    test al, 2
    jz .data
    loop .ready2
    jmp .chain
.data:
    mov al, 0x1C
    out 0x60, al
.chain:
    pop cx
    pop ax
    jmp far [cs:old_tick]
old_tick: dd 0
countdown: dw 0
idle_before: dd 0
idle_delta: dd 0
prompt: db 'Waiting for driver idle and keyboard wake...',13,10,'$'
installed: db 'Compaq POWER installed and APM active',13,10,'$'
context_managed: db 'HIMEM XMS present; DOS caller is virtual86 (CR0.PE=1)',13,10,'$'
context_real: db 'DOS caller is real mode (CR0.PE=0)',13,10,'$'
driver_pass: db 'Compaq POWER: actual BIOS idle/wake and DOS keyboard return PASS',13,10,'$'
%endif

fail:
    cld
    sti
    mov dx, failed
    mov ah, 9
    int 0x21
    mov bl, 0x7C
exit_vm:
    push bx
    mov bx, 1                   ; Close redirected stdout before the VM exits.
    mov ah, 0x3E
    int 0x21
    pop bx
    mov dx, 0x80
    mov al, '8'
    out dx, al
    mov al, '6'
    out dx, al
    mov al, 'B'
    out dx, al
    mov al, 'o'
    out dx, al
    mov al, 'x'
    out dx, al
    mov al, 1
    out dx, al
    mov al, 5
    out dx, al
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
    mov ax, 0x4C00
    int 0x21
probe_pass: db 'APM 1.2 real/protected interfaces and HLT wake: PASS',13,10,'$'
failed: db 'APM native check FAILED',13,10,'$'
