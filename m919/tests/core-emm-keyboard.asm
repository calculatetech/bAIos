bits 16
org 0x100
    push cs
    pop ds
    smsw ax
    test al,1
    mov al,0x71
    jz terminal                 ; Require the real EMM386 protected monitor.
    cli
    call input_clear
    mov al,0x20
    out 0x64,al
    mov cx,0xFFFF
.controller_reply:
    in al,0x64
    test al,1
    loopz .controller_reply
    jz .policy_failed
    in al,0x60
    and al,0x71
    cmp al,0x41
    jne .policy_failed
    in al,0x21
    test al,2
    jnz .policy_failed
    mov ax,0x3509
    int 0x21
    mov [old_irq],bx
    mov [old_irq+2],es
    mov ax,0x351C
    int 0x21
    mov [old_tick],bx
    mov [old_tick+2],es
    mov dx,irq_observer
    mov ax,0x2509
    int 0x21
    mov dx,tick_observer
    mov ax,0x251C
    int 0x21
    sti
    call wait_ticks
    mov al,0x1E                 ; D2 tests IRQ delivery, not serial reception.
    call inject
    call wait_ticks
    mov al,0x72
    cmp word [entries],0
    je terminal
    mov al,0x73
    mov bx,[entries]
    cmp bx,[returns]
    jne terminal
    mov ah,1
    int 0x16
    jz .no_queue
    cmp ax,0x1E61
    jne .bad_key
    mov ah,8
    int 0x21                    ; Real DOS console input through the queue.
    cmp al,'a'
    jne .bad_key
    mov al,0x3A
    call inject
    call wait_ticks
    mov al,0xBA
    call inject
    mov cx,20
.led_wait:
    call wait_ticks
    push es
    xor ax,ax
    mov es,ax
    mov al,[es:0x417]
    shr al,4
    and al,7
    cmp al,[es:0x49B]
    pop es
    je .pass
    loop .led_wait
    mov al,0x76
    jmp terminal
.pass:
%ifdef EMULATOR_DMA_TEST
    call floppy_cache_check
%endif
    mov al,0x68
    jmp terminal
.no_queue:
    mov al,0x74
    jmp terminal
.bad_key:
    mov al,0x75
    jmp terminal
.policy_failed:
    mov al,0x79
    jmp terminal
wait_ticks:
    push cx
    push bx
    mov bx,[ticks]
    mov ecx,0x02000000
.wait:
    mov ax,[ticks]
    sub ax,bx
    cmp ax,4
    jae .done
    dec ecx
    jnz .wait
    mov al,0x77
    jmp terminal
.done:
    pop bx
    pop cx
    ret
inject:
    push ax
    call input_clear
    mov al,0xD2
    out 0x64,al
    call input_clear
    pop ax
    out 0x60,al
    ret
input_clear:
    push cx
    mov cx,0xFFFF
.wait:
    in al,0x64
    test al,2
    loopnz .wait
    pop cx
    jnz .fail
    ret
.fail:
    mov al,0x78
    jmp terminal
irq_observer:
    inc word [cs:entries]
    pushf
    call far [cs:old_irq]
    inc word [cs:returns]
    iret
tick_observer:
    inc word [cs:ticks]
    jmp far [cs:old_tick]
old_irq dw 0,0
old_tick dw 0,0
ticks dw 0
entries dw 0
returns dw 0
%ifdef EMULATOR_DMA_TEST
floppy_cache_check:
    push cs
    pop es
    mov ax,0x0201
    mov bx,floppy_original
    mov cx,0x4F12             ; Last sector of the disposable 1.44 MiB image.
    mov dx,0x0100
    int 0x13
    jc .failed
    mov di,floppy_pattern
    mov cx,256
    mov ax,0xA55A
.pattern:
    stosw
    inc ax
    loop .pattern
    mov ax,0x0301
    mov bx,floppy_pattern
    mov cx,0x4F12
    mov dx,0x0100
    int 0x13
    jc .failed
    mov ax,0x0201
    mov bx,floppy_read
    mov cx,0x4F12
    mov dx,0x0100
    int 0x13
    jc .failed
    mov si,floppy_pattern
    mov di,floppy_read
    mov cx,256
    repe cmpsw
    jne .failed
    mov ax,0x0301
    mov bx,floppy_original
    mov cx,0x4F12
    mov dx,0x0100
    int 0x13
    jc .failed
    mov ax,0x0201
    mov bx,floppy_read
    mov cx,0x4F12
    mov dx,0x0100
    int 0x13
    jc .failed
    mov si,floppy_original
    mov di,floppy_read
    mov cx,256
    repe cmpsw
    jne .failed
    mov ax,0x0301
    mov bx,vm86_record
    mov cx,2
    mov dx,0x0080
    int 0x13                  ; Record completed comparisons on disposable HDD.
    jc .failed
    ret
.failed:
    mov al,0x6A
    jmp terminal
floppy_original times 512 db 0
floppy_pattern times 512 db 0
floppy_read times 512 db 0
vm86_record db 'DMA/EMM1'
    dw 5
    times 512-10 db 0
%endif
%include "test-terminal.inc"
