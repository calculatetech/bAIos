; Observe the existing AT refresh request cadence without programming timers.
bits 16
cpu 386
org 0x100

start:
    push cs
    pop ds
    cld
    smsw ax
    test al,1
    jnz refuse
    pushf
    pop ax
    test ax,0x200
    jz refuse
    mov dx,title
    mov cx,title_end-title
    call print
    pushf
    cli
    mov al,0xE2                 ; Latch channel0 status only.
    out 0x43,al
    in al,0x40
    and al,0x7F
    mov [status0],al
    mov al,0xE4                 ; Latch channel1 status only.
    out 0x43,al
    in al,0x41
    and al,0x7F
    mov [status1],al
    popf
    mov al,[status0]
    cmp al,0x34
    je .counter1
    cmp al,0x36
    jne timer_error
    mov byte [halve],1
.counter1:
    mov al,[status1]
    test al,0x40                ; Null count: no usable loaded count.
    jnz timer_error
    and al,0x30
    jz timer_error
    mov [access1],al
    mov bp,256
.sample:
    pushf
    cli
    mov al,0x40                 ; Channel1 count latch; mode/reload unchanged.
    out 0x43,al
    xor ax,ax
    in al,0x41
    cmp byte [access1],0x10
    je .latched
    mov ah,al
    xor al,al
    cmp byte [access1],0x20
    je .latched
    in al,0x41
    xchg al,ah
.latched:
    popf
    cmp ax,[minimum]
    jae .max
    mov [minimum],ax
.max:
    cmp ax,[maximum]
    jbe .next
    mov [maximum],ax
.next:
    dec bp
    jnz .sample

    mov bp,64
.window:
    pushf
    cli
    mov cx,8192                ; Bounded even if port61.4 never changes.
    in al,0x61
    and al,0x10
    mov dl,al
    call edge
    jc .stalled
    call pit0
    mov si,ax
    mov bh,32
.edges:
    call edge
    jc .stalled
    dec bh
    jnz .edges
    call pit0
    popf
    cmp ax,si                  ; Reject wrap, as in the existing VGAIO tool.
    jae .retry
    sub si,ax
    movzx eax,si
    add [ticks],eax
    dec bp
    jnz .window
    cmp byte [halve],0
    je .complete
    shr dword [ticks],1
.complete:
    mov byte [exit_code],0
    jmp report
.retry:
    dec byte [retries]
    jnz .window
    jmp timer_error
.stalled:
    popf
timer_error:
    mov byte [exit_code],3
report:
    movzx eax,byte [status0]
    mov di,out_status0
    call hex32
    movzx eax,byte [status1]
    mov di,out_status1
    call hex32
    movzx eax,word [minimum]
    mov di,out_minimum
    call hex32
    movzx eax,word [maximum]
    mov di,out_maximum
    call hex32
    mov eax,[ticks]
    mov di,out_ticks
    call hex32
    mov al,[exit_code]
    add al,'0'
    mov [out_code],al
    mov dx,output
    mov cx,output_end-output
    call print
    mov al,[exit_code]
    jmp exit
refuse:
    mov dx,refusal
    mov cx,refusal_end-refusal
    call print
    mov al,2
exit:
    mov ah,0x4C
    int 0x21

edge:
    in al,0x61
    and al,0x10
    cmp al,dl
    jne .changed
    loop edge
    stc
    ret
.changed:
    mov dl,al
    dec cx
    jz .timeout
    clc
    ret
.timeout:
    stc
    ret

pit0:
    xor al,al
    out 0x43,al
    in al,0x40
    mov ah,al
    in al,0x40
    xchg al,ah
    ret

hex32:
    mov cx,8
.digit:
    rol eax,4
    mov dl,al
    and dl,15
    add dl,'0'
    cmp dl,'9'
    jbe .store
    add dl,7
.store:
    mov [di],dl
    inc di
    loop .digit
    ret

print:
    mov bx,1
    mov ah,0x40
    int 0x21
    jc .error
    cmp ax,cx
    jne .error
    ret
.error:
    mov ax,0x4C01
    int 0x21

status0 db 0
status1 db 0
access1 db 0
halve db 0
retries db 32
exit_code db 3
minimum dw 0xFFFF
maximum dw 0
ticks dd 0
title db 'REFRESH 1 - counter latches and port61 reads only',13,10
title_end:
output db 'PIT0/PIT1 status: '
out_status0 db '00000000 '
out_status1 db '00000000',13,10
       db 'PIT1 sampled min/max: '
out_minimum db '00000000 '
out_maximum db '00000000',13,10
       db '2048 refresh-bit transitions, PIT ticks: '
out_ticks db '00000000',13,10
       db 'R'
out_code db '3'
       db ' (0=complete; 3=unsupported/stalled timer, discard tick total).',13,10
output_end:
refusal db 'R2 Boot fresh plain DOS without EMM386; interrupts must be enabled.',13,10
refusal_end:
