bits 16
org 0x100

    mov sp,stack_end
    push cs
    pop ds
    push cs
    pop es
    mov bx,(image_end+15)/16
    mov ah,0x4A
    int 0x21
    jc .memory
    mov bx,0x34
    call find_entry
    jz .missing
    mov [cm_entry],di
    mov [cm_entry+2],es
    xor ax,ax
    call far [cs:cm_entry]
    mov [cs:version],ax
    mov [cs:nodes],bx
    cmp ax,0xFFFF
    je .missing
    mov bx,0x304C
    call find_entry
    jz .missing
    mov [ca_entry],di
    mov [ca_entry+2],es
    push cs
    pop es
    mov di,size
    mov ax,0x16
    call far [cs:ca_entry]
    mov [cs:info_status],ax
    test ax,ax
    jnz .info_failed
    cmp word [cs:size],buffer_end-buffer
    ja .too_large
    push cs
    pop es
    mov di,buffer
    mov ax,0x17
    call far [cs:ca_entry]
    mov [cs:read_status],ax
    mov bx,[cs:buffer]
    mov [cs:declared],bx
    test ax,ax
    jnz .read_failed
    cmp word [cs:buffer+2],0x4341
    jne .bad_header
    cmp word [cs:buffer+4],0x4746
    jne .bad_header
    cmp word [cs:buffer+6],0x200
    jne .bad_header
    xor bx,bx
.node:
    cmp bx,[cs:nodes]
    jae .report
    push bx
    push cs
    pop es
    mov di,buffer
    mov ax,1
    call far [cs:cm_entry]
    pop bx
    test ax,ax
    jnz .node_failed
    inc bx
    jmp .node
.node_failed:
    mov [cs:node_status],ax
    mov [cs:node_index],bx
    mov word [cs:result],7
    jmp .report
.memory:
    mov word [cs:result],1
    jmp .report
.missing:
    mov word [cs:result],2
    jmp .report
.info_failed:
    mov word [cs:result],3
    jmp .report
.too_large:
    mov word [cs:result],4
    jmp .report
.read_failed:
    mov word [cs:result],5
    jmp .report
.bad_header:
    mov word [cs:result],6
.report:
    push cs
    pop ds
%ifdef PNP_ESCD_WRITE_PROBE
    mov ax,0x40
    mov es,ax
    mov es,[es:0x0E]
    cmp word [es:0x1046],0x5045
    jne .probe_done
    mov ax,[es:0x1048]
    mov [probe_status],ax
    mov eax,[es:0x104A]
    mov [probe_id],eax
.probe_done:
%endif
    mov si,fields
    mov di,line+1
    mov cx,(fields_end-fields)/2
.field:
    lodsw
    mov bx,ax
    mov dx,[bx]
    push cx
    mov cx,4
.digit:
    rol dx,4
    mov bx,dx
    and bx,15
    mov al,[hex+bx]
    mov [di],al
    inc di
    loop .digit
    add di,2
    pop cx
    loop .field
    mov dx,line
    mov ah,9
    int 0x21
    mov ax,0x4C00
    int 0x21

find_entry:
    xor ax,ax
    mov es,ax
    xor di,di
    mov ax,0x1684
    int 0x2F
    push cs
    pop ds
    mov ax,es
    or ax,di
    ret

cm_entry dd 0
ca_entry dd 0
result dw 0
version dw 0xFFFF
nodes dw 0
info_status dw 0xFFFF
size dw 0
read_status dw 0xFFFF
declared dw 0
node_status dw 0xFFFF
node_index dw 0xFFFF
fields dw result,version,nodes,info_status,size,read_status,declared,node_status,node_index
%ifdef PNP_ESCD_WRITE_PROBE
    dw probe_status,probe_id,probe_id+2
%endif
fields_end:
hex db '0123456789ABCDEF'
line db 'I0000 V0000 N0000 G0000 S0000 R0000 D0000 E0000 X0000'
%ifdef PNP_ESCD_WRITE_PROBE
    db ' W0000 M0000 T0000'
%endif
    db 13,10,'$'
%ifdef PNP_ESCD_WRITE_PROBE
probe_status dw 0xFFFF
probe_id dd 0xFFFFFFFF
%endif
buffer times 8192 db 0
buffer_end:
    times 256 db 0
stack_end:
image_end equ $-$$+0x100
