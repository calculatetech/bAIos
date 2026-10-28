; Run the real DOS editor, exercise its mouse cursor, type and save a file.
bits 16
org 0x100
start:
    push cs
    pop ds
    push cs
    pop es
    mov [parameters+4], cs
    mov [parameters+8], cs
    mov [parameters+12], cs
    cli
    mov sp, stack_end
    sti
    mov bx, (program_end-$$+0x100+15)/16
    mov ah, 0x4A
    int 0x21
    jc fail
    mov ax, 0x3508
    int 0x21
    mov [old_tick], bx
    mov [old_tick+2], es
    mov ax, 0x3516
    int 0x21
    mov [old16], bx
    mov [old16+2], es
    mov dx, observe16
    mov ax, 0x2516
    int 0x21
    mov ax, 0x3509
    int 0x21
    mov [old09], bx
    mov [old09+2], es
    mov dx, observe09
    mov ax, 0x2509
    int 0x21
    mov dx, tick
    mov ax, 0x2508
    int 0x21
    push ds
    pop es
    mov dx, editor
    mov bx, parameters
    mov ax, 0x4B00
    int 0x21
    pushf
    push cs
    pop ds
    push ds
    lds dx, [old_tick]
    mov ax, 0x2508
    int 0x21
    pop ds
    push ds
    lds dx, [old16]
    mov ax, 0x2516
    int 0x21
    pop ds
    push ds
    lds dx, [old09]
    mov ax, 0x2509
    int 0x21
    pop ds
    popf
    jc fail
    cmp byte [saw_editor], 1
    jne fail
    cmp word [key_index], key_end-keys
    jne fail
%ifndef NO_MOUSE
    cmp word [motion_index], motion_end-motion
    jne fail
%endif
    mov al, 0x69
    jmp exit_vm
fail:
    mov al, 0x79
exit_vm:
    mov bl, al
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
    cli
    hlt

tick:
    pushf
    call far [cs:old_tick]
    pushad
    push ds
    push es
    push cs
    pop ds
    inc word [elapsed]
    mov ax, 0xB800
    mov es, ax
    cmp word [elapsed], 450
    jb .inspect
    ; Disposable VHD only: preserve the screen at LBA32 before watchdog exit.
    mov [dap+6], cs
    xor si, si
.capture:
    mov ax, [es:si]
    mov [screen+si], ax
    add si, 2
    cmp si, 4000
    jb .capture
    mov si, dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov ax, 0x40
    mov es, ax
    xor si, si
.bda:
    mov ax, [es:si]
    mov [debug+si], ax
    add si, 2
    cmp si, 256
    jb .bda
    in al, 0x64
    mov [debug_status], al
    in al, 0x21
    mov [debug_pic], al
    mov ax, [key_index]
    mov [debug_keys], ax
    push es
    xor ax, ax
    mov es, ax
    mov eax, [es:0x24]
    mov [debug_vector09], eax
    mov es, [es:0x26]
    mov si, ax
    xor di, di
.irqcode:
    mov al, [es:si]
    mov [debug_irqcode+di], al
    inc si
    inc di
    cmp di, 128
    jb .irqcode
    pop es
    mov ax, [es:0x0E]
    mov es, ax
    xor si, si
.ebda:
    mov al, [es:0x100+si]
    mov [debug_ebda+si], al
    inc si
    cmp si, 33
    jb .ebda
    mov [debug_dap+6], cs
    mov si, debug_dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov al, 0x7A
    jmp exit_vm
.inspect:
    ; Editor's top menu line has File. Do not count COMMAND.COM as editor.
    cmp word [es:4], 0x7046
    jne .scan_text
    mov byte [saw_editor], 1
.scan_text:
    mov di, 0
.scan:
    cmp byte [es:di], 'F'
    jne .next
    cmp byte [es:di+2], 'i'
    jne .next
    cmp byte [es:di+4], 'l'
    jne .next
    cmp byte [es:di+6], 'e'
    jne .next
    mov byte [saw_editor], 1
.next:
    add di, 2
    cmp di, 160
    jb .scan
    cmp word [elapsed], 180
    jb .done
    test byte [elapsed], 3
    jnz .done
    mov si, [key_index]
    cmp si, key_end-keys
    jae .done
    in al, 0x64
    test al, 3
    jnz .done
    ; Real keyboard controller injection; IRQ1/BIOS queue handles the bytes.
    mov al, 0xD2
    out 0x64, al
    mov cx, 0xFFFF
.ready:
    in al, 0x64
    test al, 2
    jz .send
    loop .ready
    jmp .done
.send:
    mov al, [keys+si]
    out 0x60, al
    inc word [key_index]
.done:
    pop es
    pop ds
    popad
    iret

observe16:
%ifndef NO_MOUSE
    ; Force the pending-AUX/INT16 polling case while real EDIT owns IRQ1.
    ; INT entry has IF clear: IRQ12 cannot drain this byte before the BIOS
    ; polls. EDIT's pre-reading IRQ1 hook must never see these mouse bytes.
    cmp ah, 1
    je .poll
    cmp ah, 0x11
    jne .observe
.poll:
    cmp word [cs:key_index], 2     ; ESC has dismissed the opening dialog.
    jb .observe
    cli                          ; EMM386 may reflect INT16 with virtual IF set.
    pushad
    mov bx, [cs:motion_index]
    cmp bx, motion_end-motion
    jae .motion_done
    in al, 0x64
    test al, 3
    jnz .motion_done
    mov al, 0xD3
    out 0x64, al
    mov cx, 0xFFFF
.input_wait:
    in al, 0x64
    test al, 2
    jz .motion_send
    loop .input_wait
    mov al, 0x7B
    jmp exit_vm
.motion_send:
    mov al, [cs:motion+bx]
    out 0x60, al
    mov cx, 0xFFFF
.output_wait:
    in al, 0x64
    and al, 0x21
    cmp al, 0x21
    je .motion_ready
    loop .output_wait
    mov al, 0x7C
    jmp exit_vm
.motion_ready:
    inc word [cs:motion_index]
.motion_done:
    popad
.observe:
%endif
    push bp
    mov bp, sp
    push bx
    mov [cs:last16], ax
    xor bx, bx
    mov bl, ah
    shl bx, 1
    inc word [cs:counts+bx]
    mov bx, [ss:bp+2]
    mov [cs:last16+2], bx
    mov bx, [ss:bp+4]
    mov [cs:last16+4], bx
    pop bx
    pop bp
    jmp far [cs:old16]

observe09:
    inc word [cs:irq09_count]
    push ax
    in al, 0x64
    mov [cs:irq09_status], al
    pop ax
    pushf
    call far [cs:old09]
    push ax
    push ds
    mov ax, 0x40
    mov ds, ax
    mov ax, [0x1A]
    mov [cs:queue_after], ax
    mov ax, [0x1C]
    mov [cs:queue_after+2], ax
    pop ds
    pop ax
    iret

editor: db 'C:\DOS\EDIT.COM',0
tail: db tail_end-tail-2,' C:\EDITTEST.TXT',13
tail_end:
parameters: dw 0,tail,0,0x5C,0,0x6C,0
old_tick: dd 0
old16: dd 0
old09: dd 0
elapsed: dw 0
saw_editor: db 0
key_index: dw 0
motion_index: dw 0
motion: db 8,0x1E,0,8,1,0        ; Two motion packets, no buttons.
motion_end:
; ESC, type 'test', Alt-F S(save), Alt-F X(exit).
keys: db 1,0x81,0x14,0x94,0x12,0x92,0x1F,0x9F,0x14,0x94
      db 0x38,0x21,0xA1,0xB8,0x1F,0x9F
      db 0x38,0x21,0xA1,0xB8,0x2D
key_end:
dap: db 16,0
     dw 8,screen,0
     dq 32
screen: times 4096 db 0
debug_dap: db 16,0
           dw 2,debug,0
           dq 40
debug: times 256 db 0
counts: times 256 dw 0
last16: times 3 dw 0
debug_status: db 0
debug_pic: db 0
debug_keys: dw 0
irq09_count: dw 0
queue_after: dd 0
debug_ebda: times 33 db 0
irq09_status: db 0
debug_vector09: dd 0
debug_irqcode: times 128 db 0
times 1024-($-debug) db 0
times 1024 db 0
stack_end:
program_end:
