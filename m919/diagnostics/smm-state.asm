; Read the current boot's result. No SMI, chipset writes or cache changes.
bits 16
org 0x100
%ifndef SMM_STATUS
%error "Pass the board-owned SMM status offset"
%endif
%ifndef STATE_KIB
%error "Pass the configured EBDA size"
%endif
%ifndef SMM_ERROR
%error "Pass the board-owned SMM error offset"
%endif
%ifndef SMM_BOOT_TRACE
%error "Pass the board-owned entry trace offsets"
%endif
%ifndef SMM_FINAL_TRACE
%error "Pass the board-owned entry trace offsets"
%endif
%ifndef SMM_TRACE_VALID
%error "Pass the board-owned trace validity offset"
%endif
start:
    push cs
    pop ds
    mov ax,0xE000
    mov es,ax
    mov dl,'X'
    cmp dword [es:0x14],0x53494142
    jne .print
    cmp dword [es:0x18],0x00314D4D
    jne .print
    xor ax,ax
    mov es,ax
    mov ax,[es:0x40E]
    cmp ax,0x8000
    jb .print
    cmp ax,0xA000-STATE_KIB*64
    ja .print
    mov es,ax
    cmp byte [es:0],STATE_KIB
    jne .print
    mov al,[es:SMM_STATUS]
    cmp al,4
    ja .print
    mov dl,al
    add dl,'0'
    cmp al,3
    jb .print
    mov al,[es:SMM_ERROR]
    mov bl,'?'
    cmp al,1
    jb .detail
    cmp al,4
    ja .detail
    mov bl,al
    add bl,'0'
.detail:
    mov [message+2],bl
    mov byte [message+3],13
    mov byte [message+4],10
    mov byte [message+5],'$'
    cmp bl,'4'
    jne .print
    cmp byte [es:SMM_TRACE_VALID],0xA5
    jne .print
    mov al,[es:SMM_BOOT_TRACE]
    call hex_digit
    mov [message+3],al
    mov al,[es:SMM_FINAL_TRACE]
    call hex_digit
    mov [message+4],al
    mov byte [message+5],13
    mov byte [message+6],10
    mov byte [message+7],'$'
.print:
    mov [code],dl
    mov dx,message
    mov ah,9
    int 0x21
    mov ax,0x4C00
    int 0x21
hex_digit:
    and al,15
    cmp al,10
    jb .digit
    add al,7
.digit:
    add al,'0'
    ret
message: db 'S'
code: db 'X',13,10,'$',0,0,0
