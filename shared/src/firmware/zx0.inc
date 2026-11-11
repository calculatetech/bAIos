; Bounded forward ZX0v2 adaptation of Emmanuel Marty's unzx0_8088.S.
; Upstream b2beaa04daf11ed67d68b911393ba6c04260e113, zlib license.
; Copyright (C) 2021 Emmanuel Marty
; ZX0 compression (c) 2021 Einar Saukas, https://github.com/einar-saukas/ZX0
;
; This software is provided 'as-is', without any express or implied
; warranty. In no event will the authors be held liable for any damages
; arising from the use of this software.
;
; Permission is granted to anyone to use this software for any purpose,
; including commercial applications, and to alter it and redistribute it
; freely, subject to the following restrictions:
;
; 1. The origin of this software must not be misrepresented; you must not
;    claim that you wrote the original software. If you use this software
;    in a product, an acknowledgment in the product documentation would be
;    appreciated but is not required.
; 2. Altered source versions must be plainly marked as such, and must not be
;    misrepresented as being the original software.
; 3. This notice may not be removed or altered from any source distribution.
;
; Adaptation: finite input/output, checked Elias/offset arithmetic and a single
; frame-unwind failure. No prefix/backward/classic stream support.
; DS:SI/BX = exact input; ES:DI=0/CX = exact output below64KiB.
; CF=status. BP/DS/ES preserved. Other GP registers and DF are scratch.
zx0_decode:
    push bp
    mov bp,sp
    push cx
    cld
    test bx,bx
    jz .failed
    test di,di
    jnz .failed
    mov ax,bx
    dec ax
    add ax,si
    jc .failed
    mov al,0x80
    mov dx,0xFFFF
.literals:
    call .elias
    cmp cx,bx
    ja .failed
    sub bx,cx
    call .output
    rep movsb
    call .bit
    jc .offset
    call .elias
.match:
    call .output
    push si
    mov si,di
    add si,dx
    jnc .failed
    push ds
    push es
    pop ds
    rep movsb
    pop ds
    pop si
    call .bit
    jnc .literals
.offset:
    mov cx,0x00FE
    call .elias_loop
    inc cl
    jz .eof
    test ch,0x80
    jnz .failed
    mov dh,cl
    mov cx,1
    test bx,bx
    jz .failed
    mov dl,[si]
    inc si
    dec bx
    stc
    rcr dx,1
    jc .length
    call .elias_data
.length:
    inc cx
    jz .failed
    jmp .match
.eof:
    test bx,bx
    jnz .failed
    cmp word [ss:bp-2],0
    jne .failed
    mov sp,bp
    pop bp
    clc
    ret
.output:
    cmp cx,[ss:bp-2]
    ja .failed
    sub [ss:bp-2],cx
    ret
.elias:
    mov cx,1
.elias_loop:
    call .bit
    jc .return
.elias_data:
    call .bit
    adc cx,cx
    jc .failed
    jmp .elias_loop
.bit:
    add al,al
    jnz .return
    test bx,bx
    jz .failed
    lodsb
    dec bx
    stc                         ; Bounds checks destroyed the refill sentinel CF.
    adc al,al
.return:
    ret
.failed:
    mov sp,bp
    pop bp
    stc
    ret
zx0_decode_end:
