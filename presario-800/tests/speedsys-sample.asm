; Run SPWHERE once before original SPEEDSYS from a fresh DOS boot.
; Observe the interrupted instruction through Speedsys's original IRQ0 chain.
; Only the verified divide-error handler is redirected; normal work is unchanged.
bits 16
org 0x100
    jmp install
    db 'SPSM'
    dw tick, old08, raw_pages
    dw version_hook, old21, divide_fault, fault_frame, fault_halt
old08: dd 0
old21: dd 0
raw_pages: db 0
%ifdef EMULATOR_PROFILE
samples: dw 0
%endif
tick:
    pushf
    push ax
    push bx
    push bp
    push ds
    mov bp, sp
    ; Speedsys A340: PUSHF / CALL FAR old08. Its saved IRQ frame follows
    ; that six-byte call frame. Do not sample unrelated timer invocations.
    cmp word [ss:bp+10], 0xA346
    jne .done
    mov ax, [ss:bp+12]
    mov ds, ax
    cmp dword [0x001F], 0x21CD30B4
    jne .done
    cmp dword [0xA340], 0x1EFF2E9C
    jne .done
    cmp word [0xA344], 0xA303
    jne .done
    cmp ax, [ss:bp+18]
    jne .external
    mov bx, [ss:bp+16]
    cmp byte [cs:raw_pages], 0
    jne .page
    mov al, 0xE0              ; Elsewhere in the application.
    cmp bx, 0x5BA0
    jb .emit
    cmp bx, 0x5DF3
    jae .emit
    mov al, 0xC0              ; Fixed CPU entry/exit/timer helper boundary.
    cmp bx, 0x5BAD
    jb .emit
    cmp bx, 0x5DE6
    jae .emit
    ; 33 passes shift the body left by 1..33 bytes. Recover original IP.
    mov ax, [0x5E02]
    cmp ax, 1
    jb .unknown
    cmp ax, 33
    ja .unknown
    sub bx, ax
    add bx, 34
    mov al, 0xC1              ; First integer/x87 alternative.
    cmp bx, 0x5C66
    jb .emit
    mov al, 0xC2              ; Common integer arithmetic.
    cmp bx, 0x5CA7
    jb .emit
    mov al, 0xC3              ; Stack/local-variable arithmetic.
    cmp bx, 0x5D3A
    jb .emit
    mov al, 0xC4              ; Scratch-buffer sorting.
    jmp .emit
.page:
    mov al, bh                ; /R: exact interrupted IP's high byte.
    jmp .emit
.unknown:
    mov al, 0xEF
    jmp .emit
.external:
    mov ax, [ss:bp+18]
    cmp ax, 0xC000
    mov al, 0xE2              ; DOS/driver/other RAM code.
    jb .emit
    mov al, 0xE1              ; Firmware address range.
.emit:
    out 0x80, al
%ifdef EMULATOR_TEST
%ifndef EMULATOR_FAULT_TEST
%ifdef EMULATOR_PROFILE
    inc word [cs:samples]
    cmp word [cs:samples], 128
    jb .done
    mov bl, al
%endif
%ifndef EMULATOR_SAMPLE_ANY
    cmp al, 0xC1
    jb .done
    cmp al, 0xC4
    ja .done
%endif
    ; Exit only after sampling a real CPU workload, not just application load.
    mov dx, 0x80
    mov si, tester
.enable:
    mov al, [cs:si]
    out dx, al
    inc si
    cmp si, tester_end
    jb .enable
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, 0x67
%ifdef EMULATOR_PROFILE
    mov al, bl
%endif
    out dx, al
    jmp $
%endif
%endif
.done:
    pop ds
    pop bp
    pop bx
    pop ax
    popf
    jmp far [cs:old08]         ; Original BIOS still owns the IRQ and its EOI.

; Reuse the one-shot DOS-version hook from SPNOFPU. Match the unpacked image
; before changing only its terminal error path, never its timed workload.
version_hook:
    pushf
    push bp
    mov bp, sp
    pushad
    push es
    cmp ah, 0x30
    jne .done
    cmp word [ss:bp+4], 0x0023
    jne .done
    mov ax, [ss:bp+6]
    mov es, ax
    cmp dword [es:0x001F], 0x21CD30B4
    jne .done
    cmp dword [es:0x2767], 0xE89C0CE8
    jne .done
    cmp word [es:0x276B], 0x82FF
    jne .done
    cmp dword [es:0xA2D3], 0xBA2500B8
    jne .done
    cmp word [es:0xA2D7], 0x2767
    jne .done
    mov byte [es:0x2767], 0xEA
    mov word [es:0x2768], divide_fault
    mov [es:0x276A], cs
%ifdef EMULATOR_FAULT_TEST
    ; Fixture only: force a real DIV fault after original INT00 installation.
    mov dword [es:0xA2FC], 0xF1F7C931 ; XOR CX,CX / DIV CX after vector setup.
%endif
    xor ax, ax
    mov es, ax
    mov eax, [cs:old21]
    mov [es:0x84], eax
    mov al, 0xD4              ; Exact-image error capture armed.
    out 0x80, al
.done:
    pop es
    popad
    pop bp
    popf
    jmp far [cs:old21]

divide_fault:
    cli
    pushad
    push ds
    push es
    push fs
    push gs
    mov bp, sp
    cmp byte [cs:captured], 0
    jne fault_halt
    mov byte [cs:captured], 1
    cld
    push ss
    pop ds
    mov si, bp
    push cs
    pop es
    mov di, fault_frame
    mov cx, 23               ; Segments, PUSHAD, and original IP/CS/FLAGS.
    rep movsw
    mov ax, ss
    mov [cs:fault_ss], ax
    mov ax, [cs:fault_frame+42]
    mov ds, ax
    mov ax, [0x5E02]
    mov [cs:fault_pass], ax
    mov ax, cs
    mov ss, ax
    mov sp, resident_end     ; Do not use the application's faulting stack.
    mov ds, ax
    xor ax, ax
    mov es, ax
    mov eax, [old08]
    mov [es:0x20], eax       ; Stop application timer callbacks after failure.
    mov al, 0xDE
    out 0x80, al
    mov ax, 3
    int 0x10
    push cs
    pop ds
    cld
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov si, fault_title
    call .text
    mov di, 160
    mov si, fault_heading
    call .text
    mov si, fault_frame+40
    mov cx, 3
    call .words
    mov di, 320
    mov si, fault_segments
    call .text
    mov si, fault_frame
    mov cx, 4
    call .words
    mov si, fault_ss
    mov cx, 2
    call .words
    mov di, 480
    mov si, fault_registers
    call .text
    mov di, 640
    mov si, fault_frame+8
    mov cx, 8
.register:
    push cx
    mov ax, [si+2]
    call .hex
    lodsw
    call .hex
    add si, 2
    mov ax, 0x0720
    stosw
    pop cx
    loop .register
    mov di, 960
    mov si, fault_footer
    call .text
%ifdef EMULATOR_FAULT_TEST
    mov dx, 0x80
    mov si, tester
.enable:
    lodsb
    out dx, al
    cmp si, tester_end
    jb .enable
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, 0x67
    out dx, al
%endif
    jmp fault_halt
.words:
    lodsw
    call .hex
    mov ax, 0x0720
    stosw
    loop .words
    ret
.hex:
    push cx
    mov cx, 4
.digit:
    rol ax, 4
    push ax
    and al, 0x0F
    add al, '0'
    cmp al, '9'
    jbe .emit
    add al, 7
.emit:
    mov ah, 7
    stosw
    pop ax
    loop .digit
    pop cx
    ret
.text:
    lodsb
    test al, al
    jz .end
    mov ah, 7
    stosw
    jmp .text
.end:
    ret
fault_halt:
    mov al, 0xDE
    out 0x80, al
    sti
    hlt
    jmp fault_halt
captured: db 0
fault_frame: times 46 db 0
fault_ss: dw 0
fault_pass: dw 0
fault_title: db 'SPWHERE v3: DIVIDE FAULT captured. Photograph this screen.',0
fault_heading: db 'IP CS FLAGS: ',0
fault_segments: db 'GS FS ES DS SS PASS: ',0
fault_registers: db 'EDI      ESI      EBP      ESP*     EBX      EDX      ECX      EAX',0
fault_footer: db 'ESP* is at exception entry. Diagnostic stopped; Ctrl+Alt+Del to reboot.',0
%ifdef EMULATOR_TEST
tester: db '86Box',1,5
tester_end:
%endif
    times 512 db 0           ; Private stack, only used after a divide fault.
resident_end:
install:
    ; /R reports actual code pages instead of grouping all other code as E0.
    mov si, 0x81
    xor cx, cx
    mov cl, [0x80]
    jcxz .ready
.argument:
    lodsb
    and al, 0xDF
    cmp al, 'R'
    jne .next
    mov byte [raw_pages], 1
.next:
    loop .argument
.ready:
    mov dx, message
    mov ah, 9
    int 0x21
    mov ax, 0x3508
    int 0x21
    mov [old08], bx
    mov [old08+2], es
    mov dx, tick
    mov ax, 0x2508
    int 0x21
    mov ax, 0x3521
    int 0x21
    mov [old21], bx
    mov [old21+2], es
    mov dx, version_hook
    mov ax, 0x2521
    int 0x21
    mov dx, (resident_end - $$ + 0x100 + 15) / 16
    mov ax, 0x3100
    int 0x21
message: db 'SPWHERE v3. Run original SPEEDSYS; report codes during slowdown.',13,10
         db 'C1 first arithmetic, C2 integer, C3 stack, C4 sort.',13,10
         db '/R mode: codes are interrupted instruction pages instead.',13,10
         db 'D4 arms divide-error capture. DE and a register screen mean a fault.',13,10
         db 'Sampler stays resident until reboot. Ignore benchmark scores.',13,10,'$'
