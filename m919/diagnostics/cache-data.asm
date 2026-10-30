; DOS-owned conventional RAM only; no disk I/O or chipset setting changes.
; I1..I3: partial-byte writes before flush / after flush / after eviction.
; I4..I6: unaligned writes at the same three boundaries. I0 passes.
; I7/I8: ascending/descending moving inversions; suffix A=2B68, B=8F7C.
; Failures append the DWORD XOR mask and aligned physical address.
; N0: virtual/protected DOS; N1: no L2; N2: insufficient RAM.
; N4: DOS allocation does not own all observed physical failure locations.
bits 16
org 0x100
%ifndef HOST_PCI_DEVICE
%error "Pass the configured host PCI device"
%endif
start:
    mov ax,cs
    mov ds,ax
    mov es,ax
    mov ss,ax
    mov sp,stack_top
    cld
    smsw ax
    test al,1
    jnz not_real
    pushfd
    cli
    mov dx,0xCF8
    in eax,dx
    push eax
    mov eax,0x80000050 | (HOST_PCI_DEVICE << 11)
    out dx,eax
    mov dx,0xCFC
    in al,dx
    mov bl,al
    pop eax
    mov dx,0xCF8
    out dx,eax
    popfd
    test bl,0x80
    jz no_cache
    and bl,7
    jz no_cache
    cmp bl,5
    ja no_cache
    mov cl,bl
    mov eax,0x1000           ; Two complete cache spans, in paragraphs.
    shl eax,cl
    cmp eax,0xFFFF
    ja no_room
    mov [paragraphs],ax
    mov eax,0x8000
    shl eax,cl
    shr eax,16
    mov [segments],al       ; One cache span, in 64-KiB segments.
    mov bx,(stack_top-$$+0x10F)/16
    mov ah,0x4A
    int 0x21
    jc no_room
    mov bx,[paragraphs]
    mov ah,0x48
    int 0x21
    jc no_room
    mov [allocation],ax
    mov [first],ax
    mov bx,[paragraphs]
    shr bx,1
    add ax,bx
    mov [second],ax
    ; These are observed Memtest addresses, never assumed to be free RAM.
    movzx eax,word [first]
    shl eax,4
    cmp eax,0x42B68
    ja no_targets
    movzx edx,word [paragraphs]
    shl edx,4
    add edx,eax
    cmp edx,0x88F80
    jb no_targets
    mov ax,[first]
    mov es,ax
    mov ax,0xA55A
    call fill
    mov al,0x3C
    call write_bytes
    mov byte [result+1],'1'
    call verify_bytes
    jc done
    call flush
    mov byte [result+1],'2'
    call verify_bytes
    jc done
    mov al,0xC3              ; Dirty data must differ from the flushed RAM copy.
    mov byte [byte_value],al
    call write_bytes
    call evict
    mov byte [result+1],'3'
    call verify_bytes
    jc done
    mov ax,0xB74E
    mov edx,0xD18B4F29
    call write_unaligned
    mov byte [result+1],'4'
    call verify_unaligned
    jc done
    call flush
    mov byte [result+1],'5'
    call verify_unaligned
    jc done
    mov ax,0x5678
    mov edx,0xA19B6F49
    mov dword [expected12],0x78234567
    mov dword [expected16],0x89ABCD56
    mov dword [expected28],0x49234567
    mov dword [expected32],0x89A19B6F
    call write_unaligned
    call evict
    mov byte [result+1],'6'
    call verify_unaligned
    jc done
    call moving_inversions
    jc done
    mov byte [result+1],'0'
done:
    mov es,[allocation]
    mov ah,0x49
    int 0x21
print:
    mov dx,result
    mov ah,9
    int 0x21
    mov ax,0x4C00
    cmp byte [result+1],'0'
    je .exit
    inc al
.exit:
    int 0x21
not_real:
    mov word [result],'N0'
    jmp print
no_cache:
    mov word [result],'N1'
    jmp print
no_room:
    mov word [result],'N2'
    jmp print
no_targets:
    mov word [result],'N4'
    jmp done
next_segment:
    push ax
    mov ax,es
    add ax,0x1000
    mov es,ax
    pop ax
    ret
fill:
    movzx bx,byte [segments]
.segment:
    xor di,di
    mov cx,0x8000
    rep stosw
    call next_segment
    dec bx
    jnz .segment
    ret
evict:
    mov es,[second]
    mov ax,0xC639
    jmp fill
flush:
    pushf
    cli
    wbinvd
    popf
    ret
write_bytes:
    mov es,[first]
    movzx bx,byte [segments]
.segment:
    mov di,1
    mov cx,0x8000
.byte:
    mov [es:di],al
    add di,2
    loop .byte
    call next_segment
    dec bx
    jnz .segment
    ret
write_unaligned:
    mov es,[first]
    movzx bx,byte [segments]
.segment:
    mov dword [es:12],0x01234567
    mov dword [es:16],0x89ABCDEF
    mov [es:15],ax
    mov dword [es:28],0x01234567
    mov dword [es:32],0x89ABCDEF
    mov [es:31],edx
    call next_segment
    dec bx
    jnz .segment
    ret
verify_bytes:
    mov es,[first]
    movzx bx,byte [segments]
.segment:
    xor di,di
    mov ah,[byte_value]
    mov al,0x5A
    mov cx,0x8000
.read:
    mov dx,[es:di]
    cmp dx,ax
    jne .failed
    add di,2
    loop .read
    call next_segment
    dec bx
    jnz .segment
    clc
    ret
.failed:
    xor dx,ax
    movzx ecx,dx
    test di,2
    jz .aligned
    shl ecx,16
.aligned:
    and di,0xFFFC
    jmp report_failure
verify_unaligned:
    mov es,[first]
    movzx bx,byte [segments]
.segment:
    mov di,12
    mov eax,[expected12]
    mov edx,[es:di]
    cmp edx,eax
    jne .failed
    mov di,16
    mov eax,[expected16]
    mov edx,[es:di]
    cmp edx,eax
    jne .failed
    mov di,28
    mov eax,[expected28]
    mov edx,[es:di]
    cmp edx,eax
    jne .failed
    mov di,32
    mov eax,[expected32]
    mov edx,[es:di]
    cmp edx,eax
    jne .failed
    call next_segment
    dec bx
    jnz .segment
    clc
    ret
.failed:
    xor edx,eax
    mov ecx,edx
    jmp report_failure
bad:
    stc
    ret
; Memtest moving inversions: initialize, check/write complement ascending,
; then check/write original descending. No flush interrupts either traversal.
moving_inversions:
.pattern:
    movzx eax,byte [pattern_bit]
    imul eax,0x01010101
    mov ebp,eax
    not ebp
    mov es,[first]
    call fill
    mov es,[second]
    call fill
    mov es,[first]
    movzx bx,byte [segments]
    shl bx,1
    mov byte [result+1],'7'
.up_segment:
    xor di,di
    mov cx,0x4000
.up:
    mov edx,[es:di]
    cmp edx,eax
    jne .failed
    mov [es:di],ebp
    add di,4
    loop .up
    call next_segment
    dec bx
    jnz .up_segment
    movzx bx,byte [segments]
    shl bx,1
    mov byte [result+1],'8'
.down_segment:
    push ax
    mov ax,es
    sub ax,0x1000
    mov es,ax
    pop ax
    mov di,0xFFFC
    mov cx,0x4000
.down:
    mov edx,[es:di]
    cmp edx,ebp
    jne .failed
    mov [es:di],eax
    sub di,4
    loop .down
    dec bx
    jnz .down_segment
    shl byte [pattern_bit],1
    jnz .pattern
    clc
    ret
.failed:
    mov ecx,edx
    cmp byte [result+1],'7'
    jne .reverse
    xor ecx,eax
    jmp .address
.reverse:
    xor ecx,ebp
.address:
report_failure:
    movzx eax,di
    mov dx,es
    movzx edx,dx
    shl edx,4
    add eax,edx
    mov ebp,eax
    and eax,0x3FFFF          ; Observed 256-KiB repetition, not a RAM-size guess.
    mov byte [result+2],'X'
    cmp eax,0x2B68
    jne .second
    mov byte [result+2],'A'
.second:
    cmp eax,0x8F7C
    jne .mask
    mov byte [result+2],'B'
.mask:
    mov byte [result+3],' '
    mov di,result+4
    call .hex
    mov byte [di],' '
    inc di
    mov ecx,ebp
    call .hex
    mov word [di],0x0A0D
    mov byte [di+2],'$'
    jmp bad
.hex:
    mov bx,8
.digit:
    rol ecx,4
    mov al,cl
    and al,15
    add al,'0'
    cmp al,'9'
    jbe .store
    add al,7
.store:
    mov [di],al
    inc di
    dec bx
    jnz .digit
    ret
result db 'I0 ',13,10,'$'
    times 18 db 0
pattern_bit db 1
byte_value db 0x3C
expected12 dd 0x4E234567
expected16 dd 0x89ABCDB7
expected28 dd 0x29234567
expected32 dd 0x89D18B4F
paragraphs dw 0
allocation dw 0
first dw 0
second dw 0
segments db 0
align 2
times 256 dw 0
stack_top:
