bits 16
org 0x100
start:
    cld
%ifdef TRACE_FLOPPY
    cmp byte [0x82], 'I'
    je install_trace
    call save_trace
%endif
    cmp byte [0x80], 0
    jne failed
%ifdef MEMORY_MANAGERS
    mov ax, 0x4300
    int 0x2F
    cmp al, 0x80
    jne failed
    smsw ax
    test al, 1              ; EMM386 must actually be active, not just requested.
    jz failed
%endif
%if TYPE_A != 0
    mov dx, path_a
    call check_file
    jc failed
%endif
%if TYPE_B != 0
    mov dx, path_b
    call check_file
    jc failed
%endif
    mov al, 0x68
    jmp exit_emulator
check_file:
    mov ax, 0x3D00
    int 0x21
    jc .done
    mov bx, ax
    mov ah, 0x3F
    mov cx, 9
    mov dx, buffer
    int 0x21
    pushf
    push ax
    mov ah, 0x3E
    int 0x21
    pop ax
    popf
    jc .done
    cmp ax, 9
    jne .bad
    mov si, expected
    mov di, buffer
    mov cx, 9
    repe cmpsb
    jne .bad
    clc
.done:
    ret
.bad:
    stc
    ret
failed:
    ; Preserve the floppy owner's state before reporting a DOS-level failure.
    push ds
    push cs
    pop ds
    mov dx, state_name
    xor cx, cx
    mov ah, 0x3C
    int 0x21
    jc .reported
    mov bx, ax
    xor ax, ax
    mov ds, ax
    mov ds, [0x040E]
    mov dx, 0x80
    mov cx, 48
    mov ah, 0x40
    int 0x21
    mov ah, 0x3E
    int 0x21
.reported:
    pop ds
    mov al, 0x69
exit_emulator:
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
    mov ax, 0x4C00
    int 0x21
path_a: db 'A:\PROBE.TXT',0
state_name: db 'C:\FDSTATE.BIN',0
path_b: db 'B:\PROBE.TXT',0
expected: db 'FLOPPY_OK'
buffer: times 16 db 0

%ifdef TRACE_FLOPPY
; Test-only resident observer. Save the last failed floppy call before DOS
; retries or resets the controller. INT60 is private to this disposable guest.
install_trace:
    xor ax, ax
    mov es, ax
    cli
    mov eax, [es:0x4C]
    mov [old13], eax
    mov word [es:0x4C], trace13
    mov [es:0x4E], cs
    mov word [es:0x180], snapshot
    mov [es:0x182], cs
    sti
    mov dx, (resident_end - $$ + 0x100 + 15) >> 4
    mov ax, 0x3100
    int 0x21
trace13:
    cmp dl, 2
    jb .floppy
    jmp far [cs:old13]
.floppy:
    push bp
    mov bp, sp
    mov [cs:inputs], ax
    mov [cs:inputs+2], cx
    mov [cs:inputs+4], dx
    mov [cs:inputs+6], bx
    mov [cs:inputs+8], es
    pushf
    call far [cs:old13]
    jnc .good
    pushad
    push ds
    push es
    push fs
    mov [cs:snapshot+10], ax
    push cs
    pop ds
    push cs
    pop es
    mov si, inputs
    mov di, snapshot
    mov cx, 5
    cld
    rep movsw
    add di, 2
    xor ax, ax
    mov fs, ax
    mov fs, [fs:0x040E]
    mov si, 0x80
    mov cx, 48
.copy:
    mov al, [fs:si]
    stosb
    inc si
    loop .copy
    pop fs
    pop es
    pop ds
    popad
    or word [ss:bp+6], 1
    pop bp
    iret
.good:
    and word [ss:bp+6], 0xFFFE
    pop bp
    iret
save_trace:
    mov dx, trace_name
    xor cx, cx
    mov ah, 0x3C
    int 0x21
    jc .done
    mov [trace_handle], ax
    mov ax, 0x3560
    int 0x21
    mov dx, bx
    mov bx, [trace_handle]
    push ds
    push es
    pop ds
    mov cx, 60
    mov ah, 0x40
    int 0x21
    pop ds
    mov ah, 0x3E
    int 0x21
    push ds
    pop es
.done:
    ret
old13: dd 0
inputs: times 10 db 0
snapshot: times 60 db 0
trace_name: db 'C:\FDTRACE.BIN',0
trace_handle: dw 0
resident_end:
%endif
