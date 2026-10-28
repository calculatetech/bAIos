bits 16
org 0x100

    smsw ax
    test al,1
    jnz .mode
    push cs
    pop ds
    cld
    mov ax,cs
    cmp ax,0x7000
    jae .placement
    mov ax,ss
    cmp ax,0x7000
    jae .placement
    xor eax,eax
    mov ax,cs
    shl eax,4
    add eax,buffer
    mov [table+0x1A],ax
    shr eax,16
    mov [table+0x1C],al
    mov [table+0x1F],ah
    mov byte [matches],0
    mov word [low_segment],0xF000
.next:
    push cs
    pop es
    mov si,table
    mov cx,256
    mov ax,0x8700
    int 0x15
    jc .copy_error
    test ah,ah
    jnz .copy_error
    mov es,[low_segment]
    mov si,buffer
    xor di,di
    mov cx,256
    repe cmpsw
    jne .different
    inc byte [matches]
.different:
    cmp word [low_segment],0xF800
    je .result
    mov word [low_segment],0xF800
    mov word [table+0x12],0x8000
    jmp .next
.result:
    xor al,al
    cmp byte [matches],2
    je .report
    mov al,1
    cmp byte [matches],0
    je .report
    mov al,2
    jmp .report
.copy_error:
    mov al,3
    jmp .report
.mode:
    mov al,4
    jmp .report
.placement:
    mov al,5
.report:
    mov [status],al
    add al,'0'
    mov [message+1],al
    mov dx,message
    mov ah,9
    int 0x21
    mov al,[status]
    mov ah,0x4C
    int 0x21

status db 0
matches db 0
low_segment dw 0
message db 'H0',13,10,'$'
align 4
table:
    dq 0,0
    dw 0xFFFF,0
    db 0xFF,0x93,0,0
    dw 0xFFFF,0
    db 0,0x93,0,0
    dq 0,0
buffer times 512 db 0
