%ifndef PC_PROCESSOR_PRIMITIVES
%include "pc/processor.inc"
%endif

; EAX: mapped upper limit in whole 64 KiB pages; returns contiguous end in EAX.
; OEM7630/6162 witnesses; preserve the three words and the existing mode owners.
memory_qualify_contiguous:
    pushf
    cli
    pushad
    push ds
    push es
    mov ebx,eax
    sub sp,6
    mov di,sp
    o32 sgdt [ss:di]
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    board_a20_read
    push ax
    and al,0xFE
    or al,2
    board_a20_write
    mov ebp,cr0
    cpu_cache_flush
    mov eax,ebp
    cpu_cache_disable
    or al,1
    o32 lgdt [cs:move_gdtr]
    mov cr0,eax
    jmp 0x08:.protected
.protected:
    mov ax,0x10
    mov ds,ax
    mov es,ax
    mov edi,0x100000
.next:
    cmp edi,ebx
    jae .leave
    mov dx,[edi]
    mov cx,[edi+0xFFF0]
    mov si,[edi+0xFFFC]
    mov word [edi],0x1234
    jmp short $+2
    jmp short $+2
    mov word [edi+0xFFF0],0
    jmp short $+2
    jmp short $+2
    cmp word [edi],0x1234
    jne .first_failed
    mov word [edi],0
    mov word [edi+0xFFFC],0x1234
    jmp short $+2
    jmp short $+2
    mov word [edi],0
    jmp short $+2
    jmp short $+2
    cmp word [edi+0xFFFC],0x1234
    jne .last_failed
    mov word [edi+0xFFFC],0
    xor ax,ax
    jmp .restore_words
.first_failed:
    mov word [edi],0
    jmp .failed
.last_failed:
    mov word [edi+0xFFFC],0
.failed:
    mov ax,1
.restore_words:
    mov [edi+0xFFFC],si
    mov [edi+0xFFF0],cx
    mov [edi],dx
    test ax,ax
    jnz .leave
    add edi,0x10000
    jmp .next
.leave:
    cpu_cache_flush
    mov ax,0x18
    mov ds,ax
    mov es,ax
    mov eax,ebp
    mov cr0,eax
    jmp 0xF000:.real
.real:
    pop ax
    board_a20_write
    pop ax
    out 0x61,al
    mov bp,sp
    o32 lgdt [ss:bp]
    add sp,6
    pop es
    pop ds
    mov bp,sp
    mov [ss:bp+28],edi
    popad
    popf
    ret
