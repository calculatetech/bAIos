; Fixed transfers and PIT0 polling. Optional I briefly clears IDE41 bits09.
bits 16
cpu 386
org 0x100
%include "configuration.inc"

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
    call argument
    jc refuse
    mov eax,cr0
    mov di,out_cr0
    call hex32
    xor ax,ax
    mov es,ax
    movzx eax,word [es:0x413]
    mov di,out_kb
    call hex32
    movzx eax,word [es:0x40E]
    mov di,out_ebda
    call hex32
    push ds
    mov ah,0x0F
    int 0x10
    pop ds
    and al,0x7F
    cmp al,3
    jne refuse
    mov ax,0xC000
    mov es,ax
    cmp word [es:0],0xAA55
    jne refuse
    pushf
    cli
    mov al,0xE2                 ; 8254 read-back: latch only channel0 status.
    out 0x43,al
    in al,0x40
    popf
    and al,0x7F
    cmp al,0x34                 ; Binary, lo/hi access, mode2 or3, count loaded.
    je .timer
    cmp al,0x36
    jne refuse
    mov byte [halve],1
.timer:
    movzx eax,al
    mov di,out_pit
    call hex32
    call ide_prepare
    jc ide_error
    mov ax,cs
    mov es,ax
    mov word [offset],buffer
    mov bx,empty_kernel
    call measure
    jc timer_error
    mov [results],eax
    mov bx,word_kernel
    call measure
    jc timer_error
    mov [results+4],eax
    mov ax,0xC000
    mov es,ax
    mov word [offset],0
    mov bx,read_kernel
    call measure
    jc timer_error
    mov [results+8],eax
    mov ax,0xB800
    mov es,ax
    mov word [offset],0xA0
    mov bx,word_kernel
    call measure
    jc timer_error
    mov [results+12],eax
    mov al,0x13
    call set_mode
    mov byte [graphics],1
    mov ax,0xA000
    mov es,ax
    mov word [offset],0
    mov bx,byte_kernel
    call measure
    jc timer_error
    mov [results+16],eax
    call planar
    mov bx,column_kernel
    call measure
    jc timer_error
    mov [results+20],eax
    call restore_text
    mov si,results
    mov bx,fields
    mov cx,6
.format:
    lodsd
    mov di,[bx]
    add bx,2
    call hex32
    loop .format
    mov dx,output
    mov cx,output_end-output
    xor al,al
    jmp finish

refuse:
    mov dx,refusal
    mov cx,refusal_end-refusal
    mov al,2
    jmp finish
timer_error:
    call restore_text
    mov dx,timer_message
    mov cx,timer_message_end-timer_message
    mov al,3
    jmp finish
ide_error:
    mov dx,ide_message
    mov cx,ide_message_end-ide_message
    mov al,4
finish:
    mov [exit_code],al
    call ide_restore
    mov bx,1
    mov ah,0x40
    int 0x21
    jc .write_error
    cmp ax,cx
    jne .write_error
    mov al,[exit_code]
    jmp .exit
.write_error:
    mov al,1
.exit:
    mov ah,0x4C
    int 0x21

argument:
    movzx cx,byte [0x80]
    mov si,0x81
.next:
    jcxz .done
    lodsb
    dec cx
    cmp al,' '
    je .next
    cmp al,9
    je .next
    or al,0x20
    cmp al,'i'
    jne .bad
    cmp byte [ide_trial],0
    jne .bad
    mov byte [ide_trial],1
    jmp .next
.done:
    clc
    ret
.bad:
    stc
    ret

; Never issue an IDE command while the temporary control value is installed.
ide_prepare:
    cmp byte [ide_trial],0
    je .done
    mov ax,0xB101
    int 0x1A
    jc .bad
    test ah,ah
    jnz .bad
    cmp edx,0x20494350
    jne .bad
    xor si,si
.id:
    call ide_read
    jc .bad
    cmp al,[ide_id+si]
    jne .bad
    inc si
    cmp si,4
    jb .id
    mov si,4
    call ide_read
    jc .bad
    and al,5
    cmp al,1                    ; I/O enabled, bus mastering disabled.
    jne .bad
    mov si,0x40
    call ide_read
    jc .bad
    test al,al                  ; No enabled FIFO mode/direction.
    jnz .bad
    mov si,0x58
    call ide_read
    jc .bad
    test al,al
    jnz .bad
    inc si
    call ide_read
    jc .bad
    test al,al
    jnz .bad
    mov si,0x41
    call ide_read
    jc .bad
    mov [ide_saved],al
    mov cl,al
    and cl,0xF6
    cmp cl,al
    je .bad
    mov [ide_requested],cl
    movzx eax,al
    mov di,out_ide_original
    call hex32
    ; A failed API call may still have reached the register; always restore.
    mov byte [ide_active],1
    call ide_write
    jc .bad
    call ide_read
    jc .bad
    cmp al,[ide_requested]
    jne .bad
    movzx eax,al
    mov di,out_ide_test
    call hex32
.done:
    clc
    ret
.bad:
    stc
    ret

ide_restore:
    cmp byte [ide_active],0
    je .done
    pushad
    mov si,0x41
    mov cl,[ide_saved]
    call ide_write
    ; Readback decides whether restoration succeeded even if the API failed.
    call ide_read
    jc restore_failed
    cmp al,[ide_saved]
    jne restore_failed
    mov byte [ide_active],0
    movzx eax,al
    mov di,out_ide_restored
    call hex32
    popad
.done:
    ret

ide_read:
    mov ax,0xB108
    jmp ide_access
ide_write:
    mov ax,0xB10B
ide_access:
    pushad
    push ds
    push es
    push fs
    push gs
    mov bx,(CFG_PLATFORM_ISA_PCI_DEVICE << 3) | 1
    mov di,si
    int 0x1A
    setc [cs:ide_carry]
    mov [cs:ide_status],ah
    mov [cs:ide_value],cl
    pop gs
    pop fs
    pop es
    pop ds
    popad
    cmp byte [ide_carry],0
    jne .bad
    cmp byte [ide_status],0
    jne .bad
    mov al,[ide_value]
    clc
    ret
.bad:
    stc
    ret

restore_failed:
    ; Do not enter DOS or write the redirected log with unconfirmed IDE state.
    mov si,restore_message
.print:
    lodsb
    test al,al
    jz .halt
    push ds
    push si
    mov ah,0x0E
    mov bx,7
    int 0x10
    pop si
    pop ds
    jmp .print
.halt:
    cli
    hlt
    jmp .halt

; Each accepted window transfers3840 bytes. Interrupts run between windows.
; Reject counter wrap instead of assuming its reload value. Fresh DOS required:
; a window spanning multiple periods cannot be recognized from two samples.
measure:
    mov dword [total],0
    mov bp,256
    mov word [retries],1024
.again:
    mov di,[offset]
    mov si,di
    pushf
    cli
    call pit_sample
    mov dx,ax
    call bx
    call pit_sample
    cmp ax,dx
    jae .retry
    sub dx,ax
    movzx ecx,dx
    add [total],ecx
    popf
    dec bp
    jnz .again
    mov eax,[total]
    cmp byte [halve],0
    je .done
    shr eax,1
.done:
    clc
    ret
.retry:
    popf
    dec word [retries]
    jnz .again
    stc
    ret

pit_sample:
    xor al,al
    out 0x43,al
    in al,0x40
    mov ah,al
    in al,0x40
    xchg al,ah
    ret
empty_kernel:
    ret
word_kernel:
    mov ax,0x0720
    mov cx,1920
    rep stosw
    ret
read_kernel:
    mov cx,1920
    es rep lodsw
    ret
byte_kernel:
    xor al,al
    mov cx,3840
    rep stosb
    ret
column_kernel:
    xor al,al
    mov si,20
.column:
    push di
    mov cx,192
.row:
    mov [es:di],al
    add di,80
    loop .row
    pop di
    inc di
    dec si
    jnz .column
    ret

; The established S3STATE / retained Doom standard-VGA unchaining sequence.
; Select one write plane to measure Doom-like byte stores, without S3 tuning.
planar:
    pushf
    cli
    mov dx,0x3C4
    mov al,4
    out dx,al
    inc dx
    in al,dx
    and al,0xF7
    or al,4
    out dx,al
    mov dx,0x3CE
    mov al,5
    out dx,al
    inc dx
    in al,dx
    and al,0xEC
    out dx,al
    dec dx
    mov al,6
    out dx,al
    inc dx
    in al,dx
    and al,0xFD
    out dx,al
    mov dx,0x3C4
    mov ax,0x0102
    out dx,ax
    mov dx,0x3D4
    mov al,0x14
    out dx,al
    inc dx
    in al,dx
    and al,0xBF
    out dx,al
    dec dx
    mov al,0x17
    out dx,al
    inc dx
    in al,dx
    or al,0x40
    out dx,al
    popf
    ret

restore_text:
    cmp byte [graphics],0
    je .done
    mov al,3
    call set_mode
    mov byte [graphics],0
.done:
    ret
set_mode:
    pushad
    push ds
    push es
    push fs
    push gs
    xor ah,ah
    int 0x10
    pop gs
    pop fs
    pop es
    pop ds
    popad
    cld
    ret

hex32:
    push cx
    push dx
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
    pop dx
    pop cx
    ret

halve db 0
graphics db 0
exit_code db 0
offset dw 0
retries dw 0
total dd 0
results times 6 dd 0
fields dw out_empty,out_ram,out_rom,out_text,out_gfx,out_planar
output db 'VGAIO 2 - PIT ticks; lower is faster. Each transfer: 983040 bytes.',13,10
       db 'KB/EBDA/CR0/PIT: '
out_kb db '00000000 '
out_ebda db '00000000 '
out_cr0 db '00000000 '
out_pit db '00000000',13,10
       db 'Empty   '
out_empty db '00000000',13,10
       db 'RAM W16 '
out_ram db '00000000',13,10
       db 'ROM R16 '
out_rom db '00000000',13,10
       db 'TextW16 '
out_text db '00000000',13,10
       db 'VGA W8  '
out_gfx db '00000000',13,10
       db 'Doom W8 '
out_planar db '00000000',13,10
       db 'IDE41 original/test/restored: '
out_ide_original db '-------- '
out_ide_test db '-------- '
out_ide_restored db '--------',13,10
       db 'V0 Complete. Text and original IDE state restored. Cache settings unchanged.',13,10
output_end:
refusal db 'V2 Use VGAIO or VGAIO I in fresh plain DOS, text mode3, with VGA ROM and normal PIT.',13,10
refusal_end:
timer_message db 'V3 Timer did not provide enough advancing windows. Text mode restored.',13,10
timer_message_end:
ide_message db 'V4 IDE trial unavailable or readback failed. No trial state retained.',13,10
ide_message_end:
restore_message db 'V5 IDE restore not confirmed. Reset before continuing.',13,10,0
ide_id db 0x60,0x10,0x3A,0x67
ide_trial db 0
ide_active db 0
ide_saved db 0
ide_requested db 0
ide_carry db 0
ide_status db 0
ide_value db 0
align 16,db 0
buffer times 3840 db 0
