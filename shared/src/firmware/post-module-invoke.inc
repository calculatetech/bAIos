; Resolve the current EBDA without replacing a caller's selected-device FS.
; RETF consumes the target pair, leaving the same frame as a direct far CALL.
pnp_post_invoke:
    push cs
    push word .returned
    push word 0
    push word 0
    push bp
    mov bp,sp
    push ax
    push fs
    xor ax,ax
    mov fs,ax
    mov fs,[fs:0x040E]
    mov ax,[fs:PNP_MODULE_POINTER]
    mov [ss:bp+2],ax
    mov ax,[fs:PNP_MODULE_POINTER+2]
    mov [ss:bp+4],ax
    pop fs
    pop ax
    cmp word [ss:bp+4],0
    pop bp
    je .missing
    retf
.returned:
    ret
.missing:
    add sp,8
    stc
    ret
