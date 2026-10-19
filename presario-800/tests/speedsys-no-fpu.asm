; Diagnostic: select Speedsys 4.78's existing integer CPU-test fallback.
; Run once before original SPEEDSYS. No executable or disk sector is changed.
; Scores are invalid. The hook removes itself after the verified RAM patch.
bits 16
org 0x100
    jmp install
    db 'SPNF'
    dw version_hook, old21
old21: dd 0
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
    cmp dword [es:0x5BCE], 0x24BA3E80
    jne .done
    cmp word [es:0x5BD2], 0x7501
    jne .done
    cmp byte [es:0x5BD4], 0x50
    jne .done
    cmp dword [es:0x1599], 0x020E892E
    jne .done
    cmp byte [es:0x159D], 0x5E
    jne .done
    mov byte [es:0x5BD3], 0xEB ; JNE -> JMP to the original integer fallback.
    xor ax, ax
    mov es, ax
    mov eax, [cs:old21]
    mov [es:0x84], eax        ; One shot; no hook during benchmark execution.
    mov al, 0xD0
    out 0x80, al
%ifdef EMULATOR_TEST
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
    out dx, al
    jmp $
%endif
.done:
    pop es
    popad
    pop bp
    popf
    jmp far [cs:old21]
%ifdef EMULATOR_TEST
tester: db '86Box',1,5
tester_end:
%endif
resident_end:
install:
    mov dx, message
    mov ah, 9
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
message: db 'Run original SPEEDSYS now. CPU test uses integer fallback.',13,10
         db 'Diagnostic only: ignore scores. POST D0 confirms activation.',13,10,'$'
