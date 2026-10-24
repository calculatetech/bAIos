; Preserve the reference E2-open/E0-write/E2-close transaction. BH is the
; bAIos policy computed before entry; CMOS diagnostic flags do not gate it.
oem_cache_92EB:
    mov al,0xE2
oem_cache_92ED:
    mov bp,oem_cache_92F3
oem_cache_92F0:
    jmp near oem_cache_23FC
oem_cache_92F3:
    or al,2
oem_cache_92F5:
    mov ah,al
oem_cache_92F7:
    mov al,0xE2
oem_cache_92F9:
    mov cx,ax
oem_cache_92FB:
    mov bp,oem_cache_9301
oem_cache_92FE:
    jmp near oem_cache_2407
oem_cache_9301:
    in al,0x5F
oem_cache_9303:
    test al,0x80
oem_cache_9305:
    jne short oem_cache_9335
    test si,si
    jz short oem_cache_9335
oem_cache_9307:
    mov ah,bh
    jmp short oem_cache_93A1
oem_cache_9335:
    xor ah,ah
oem_cache_9337:
    jmp short oem_cache_93A1
oem_cache_93A1:
    mov al,0xE0
oem_cache_93A3:
    mov bh,ah
oem_cache_93A5:
    mov bp,oem_cache_93AB
oem_cache_93A8:
    jmp near oem_cache_2407
oem_cache_93AB:
    mov ah,bh
oem_cache_93AD:
    mov dx,0x2FF
oem_cache_93B0:
    mov bp,oem_cache_93B6
oem_cache_93B3:
    jmp near mp_cache_record_write
oem_cache_93B6:
    mov ax,cx
oem_cache_93B8:
    and ah,0xFD
oem_cache_93BB:
    mov bp,oem_cache_93C1
oem_cache_93BE:
    jmp near oem_cache_2407
oem_cache_93C1:
    ret

cache_memory_policy:
    push ds
    mov ax,0x40
    mov ds,ax
    mov ax,[0x13]
    mov bl,1
    cmp ax,0x100
    jbe .base_ready
    inc bl
    cmp ax,0x200
    jbe .base_ready
    inc bl
.base_ready:
    pop ds
    mov ax,[fs:S_EXTENDED_KIB]
    shr ax,10
    xor bh,bh
    cmp ax,2
    jbe .done
    mov bh,0x20
    cmp ax,4
    jbe .done
    mov bh,0x30
    cmp ax,6
    jbe .done
    mov bh,0x40
    cmp ax,8
    jbe .done
    mov bh,0x50
    cmp ax,10
    jbe .done
    mov bh,0x60
    cmp ax,12
    jbe .done
    mov bh,0x68
    cmp ax,14
    jbe .done
    mov bh,0x78
.done:
    or bh,bl
    ret
