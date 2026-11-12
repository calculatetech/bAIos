; Read assigned ISA PnP cards and their gameport resource descriptors.
; Wake/LDN selection and Wait for Key are the only configuration writes.
bits 16
org 0x100

    push cs
    pop ds
    push cs
    pop ss
    mov sp,stack_end
    cld
    mov si,0x81
    xor cx,cx
    mov cl,[0x80]
.argument:
    jcxz .arguments_done
    lodsb
    and al,0xDF
    cmp al,'D'
    jne .next_argument
    mov byte [dump],1
.next_argument:
    loop .argument
.arguments_done:
    xor ax,ax
    mov es,ax
    mov al,[es:0x4FB]
    mov [cards],al
    mov dx,[es:0x4FC]
    cmp dx,0x203
    jb unavailable
    cmp dx,0x3FF
    ja unavailable
    mov ax,dx
    and al,3
    cmp al,3
    jne unavailable
    mov [read_port],dx
    cmp byte [cards],0
    je unavailable
    cmp byte [dump],0
    je .no_policy
    mov ax,[es:0x40E]
    cmp ax,0x1000
    jb .no_policy
    cmp ax,0xA000
    jae .no_policy
    mov es,ax
    mov si,msg_policy
    call text
    mov bx,0x300
    mov cx,15
.policy:
    mov al,[es:bx]
    call hex_byte
    inc bx
    loop .policy
    mov si,msg_newline
    call text
.no_policy:
    push cs
    pop es
    mov si,key
    mov dx,0x279
    mov cx,34
.key:
    lodsb
    out dx,al
    loop .key
    mov byte [csn],1
.card:
    mov al,3
    mov ah,[csn]
    call write_register
    mov word [remaining],0xFFFF
    mov byte [ldn],0xFF
    mov byte [gameport],0
    mov cx,9
.serial:
    call read_byte
    jc failed
    loop .serial
    mov byte [checksum],0
.item:
    call read_byte
    jc failed
    mov [tag],al
    mov cl,al
    and cx,7
    test al,0x80
    jz .length
    call read_byte
    jc failed
    mov cl,al
    call read_byte
    jc failed
    mov ch,al
.length:
    mov di,payload
    jcxz .dispatch
.payload:
    call read_byte
    jc failed
    cmp di,payload+8
    jae .skip_store
    stosb
.skip_store:
    loop .payload
.dispatch:
    mov al,[tag]
    cmp al,0x15
    je .logical
    cmp al,0x16
    je .logical
    cmp al,0x1C
    je .compatible
    cmp al,0x30
    je .dependent
    cmp al,0x31
    je .dependent
    cmp al,0x38
    je .end_dependent
    cmp al,0x79
    je .next_card
    cmp byte [gameport],0
    je .item
    cmp al,0x47
    je .variable
    cmp al,0x4B
    je .fixed
    jmp .item
.logical:
    inc byte [ldn]
    mov byte [gameport],0
    mov byte [alternative],0xFF
    mov byte [ordinal],0xFF
    mov byte [priority],1
.compatible:
    cmp dword [payload],0x2FB0D041 ; PNPB02F
    je .recognized
    cmp dword [payload],0x01007316 ; ESS0001
    jne .item
.recognized:
    mov byte [gameport],1
    mov al,7
    mov ah,[ldn]
    call write_register
    mov al,0x60
    call read_register
    mov [current+1],al
    mov al,0x61
    call read_register
    mov [current],al
    mov al,0x30
    call read_register
    mov [active],al
    jmp .item
.dependent:
    inc byte [ordinal]
    mov al,[ordinal]
    mov [alternative],al
    mov byte [priority],1
    cmp byte [tag],0x31
    jne .item
    mov al,[payload]
    mov [priority],al
    jmp .item
.end_dependent:
    mov byte [alternative],0xFF
    mov byte [priority],1
    jmp .item
.variable:
    mov ax,[payload+1]
    mov [minimum],ax
    mov ax,[payload+3]
    mov [maximum],ax
    mov ax,[payload+5]
    mov [alignment],al
    mov [extent],ah
    jmp .report
.fixed:
    mov ax,[payload]
    mov [minimum],ax
    mov [maximum],ax
    mov byte [alignment],1
    mov al,[payload+2]
    mov [extent],al
.report:
    cmp byte [dump],0
    jne .reported
    mov si,msg_start
    call text
    mov al,[csn]
    call hex_byte
    mov si,msg_ldn
    call text
    mov al,[ldn]
    call hex_byte
    mov si,msg_current
    call text
    mov ax,[current]
    call hex_word
    mov si,msg_enabled
    call text
    mov al,[active]
    call hex_byte
    mov si,msg_alt
    call text
    mov al,[alternative]
    call hex_byte
    mov si,msg_priority
    call text
    mov al,[priority]
    call hex_byte
    mov si,msg_range
    call text
    mov ax,[minimum]
    call hex_word
    mov dl,'-'
    call character
    mov ax,[maximum]
    call hex_word
    mov si,msg_align
    call text
    mov al,[alignment]
    call hex_byte
    mov si,msg_length
    call text
    mov al,[extent]
    call hex_byte
    mov si,msg_newline
    call text
.reported:
    inc word [found]
    jmp .item
.next_card:
    cmp byte [payload],0
    je .checksum_ok
    cmp byte [checksum],0
    jne failed
.checksum_ok:
    call dump_newline
    mov al,[csn]
    cmp al,[cards]
    jae finish
    inc byte [csn]
    jmp .card

unavailable:
    mov si,msg_unavailable
    call text
    mov ax,0x4C01
    int 0x21
failed:
    mov byte [exit_status],2
    call dump_newline
    mov si,msg_failed
    call text
finish:
    mov ax,0x0202
    call write_register
    cmp word [found],0
    jne .exit
    mov si,msg_none
    call text
.exit:
    mov ax,0x4C00
    mov al,[exit_status]
    int 0x21

write_register:
    push dx
    mov dx,0x279
    out dx,al
    mov dx,0xA79
    mov al,ah
    out dx,al
    pop dx
    ret
read_register:
    push dx
    mov dx,0x279
    out dx,al
    mov dx,[read_port]
    in al,dx
    pop dx
    ret
read_byte:
    push bx
    push dx
    cmp word [remaining],0
    je .bad
    dec word [remaining]
    mov bx,0xFFFF
.wait:
    mov al,5
    call read_register
    test al,1
    jnz .ready
    dec bx
    jnz .wait
.bad:
    stc
    jmp .return
.ready:
    mov al,4
    call read_register
    add [checksum],al
    cmp byte [dump],0
    je .read_done
    call dump_byte
.read_done:
    clc
.return:
    pop dx
    pop bx
    ret
dump_byte:
    pusha
    mov bp,sp
    cmp byte [column],0
    jne .value
    mov si,msg_raw
    call text
    mov al,[csn]
    call hex_byte
    mov dl,' '
    call character
.value:
    mov al,[ss:bp+14]
    call hex_byte
    inc byte [column]
    cmp byte [column],16
    jne .done
    call dump_newline
.done:
    popa
    ret
dump_newline:
    cmp byte [column],0
    je .done
    pusha
    mov si,msg_newline
    call text
    mov byte [column],0
    popa
.done:
    ret
text:
    lodsb
    test al,al
    jz .done
    mov dl,al
    call character
    jmp text
.done:
    ret
hex_word:
    push ax
    mov al,ah
    call hex_byte
    pop ax
hex_byte:
    push ax
    shr al,4
    call nibble
    pop ax
    and al,15
nibble:
    and al,15
    cmp al,10
    jb .digit
    add al,'A'-10
    jmp .emit
.digit:
    add al,'0'
.emit:
    mov dl,al
character:
    push ax
    mov ah,2
    int 0x21
    pop ax
    ret

key db 0,0,0x6A,0xB5,0xDA,0xED,0xF6,0xFB,0x7D,0xBE,0xDF,0x6F,0x37,0x1B,0x0D,0x86,0xC3,0x61
    db 0xB0,0x58,0x2C,0x16,0x8B,0x45,0xA2,0xD1,0xE8,0x74,0x3A,0x9D,0xCE,0xE7,0x73,0x39
msg_start db 'G C',0
msg_raw db 'R C',0
msg_policy db 'P ',0
msg_ldn db ' L',0
msg_current db ' V',0
msg_enabled db ' E',0
msg_alt db ' A',0
msg_priority db ' P',0
msg_range db ' R',0
msg_align db ' S',0
msg_length db ' N',0
msg_newline db 13,10,0
msg_unavailable db 'G1 No published ISA PnP cards/read port.',13,10,0
msg_failed db 'G2 Resource read incomplete.',13,10,0
msg_none db 'G3 No gameport I/O descriptor found.',13,10,0
read_port dw 0
cards db 0
csn db 0
ldn db 0
gameport db 0
tag db 0
alternative db 0
ordinal db 0
priority db 0
current dw 0
active db 0
minimum dw 0
maximum dw 0
alignment db 0
extent db 0
found dw 0
remaining dw 0
payload times 8 db 0
exit_status db 0
checksum db 0
dump db 0
column db 0
    times 512 db 0
stack_end:
