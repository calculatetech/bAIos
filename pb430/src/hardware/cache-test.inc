%include "pc/cache-test.inc"

cache_test:
    pushf
    cli
    cld
    pushad
    push ds
    push es
    mov byte [fs:HW_CACHE_CHECKED],0
    ; Reuse the accepted SRAM/tag state on the complete reference warm path.
    cmp byte [fs:HW_CACHE_WARM],1
    jne .test
    cmp byte [fs:HW_CACHE_VALID],CACHE_STATE_VALID
    jne .test
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    je .return
.test:
    movzx bx,byte [fs:HW_CACHE_CODE]
    dec bx
    cmp bx,2
    ja .return
    mov eax,cr0
    and eax,0x60000001
    cmp eax,0x60000000
    jne .return
    mov al,4
    call acc_read
    test al,1
    jnz .return
    movzx edx,al
    shl edx,16
    mov al,0x1A
    call acc_read
    ; Stock warm entry leaves mode08 selected with L2 already off.
    test al,0x10
    jnz .return
    mov dh,al
    mov dl,[cs:cache_test_segments+bx]
    ; Save controls before direct mode can redirect the stack or state.
    mov al,1
    call acc_read
    mov ah,al
    and ah,0xD3 ; Reserved readback bits are not the programmed control value.
    mov al,1
    push ax
    mov al,0x0A
    call acc_read
    mov ah,al
    mov al,0x0A
    push ax
    or ah,4
    call acc_write
    mov al,0x18
    call acc_read
    mov ah,al
    mov al,0x18
    push ax
    or ah,0x20
    call acc_write
    post_code 0x1D
    mov al,0xF0
    out 0x70,al
    invd
    ; Stock live rows use a 32-bit line (04=14/34); keep the probe's wait.
    ; The sizing value33 selects a second DWORD bank that this board lacks.
    mov al,0x35
    acc_commit_early 4
    mov al,dh
    and al,0xE7
    or al,0x10
    acc_commit_early 0x1A
    mov al,0x92
    acc_commit_early 1
    ; 10000..8FFFF is free POST scratch; stock probing owns presence/size.
    cache_sram_patterns .failed
    xor ebp,ebp
    jmp .restore
.failed:
    movzx ebx,bx
    movzx esi,di
    movzx edi,ax
    mov ax,es
    movzx eax,ax
    shl eax,4
    add esi,eax
    mov ebp,1
.restore:
    ; Match the reference exit order before touching stack/state again.
    mov eax,edx
    shr eax,16
    acc_commit_early 4
    mov al,dh
    acc_commit_early 0x1A
    pop ax
    call acc_write
    pop ax
    call acc_write
    pop ax
    call acc_write
    test ebp,ebp
    jz .success
    mov [fs:HW_CACHE_FAIL_ADDRESS],esi
    mov [fs:HW_CACHE_FAIL_EXPECTED],ebx
    mov [fs:HW_CACHE_FAIL_READ],edi
    xor ebp,ebp
    jmp .publish
.success:
    inc bp
.publish:
    mov ax,bp
    cmp al,[fs:HW_CACHE_QUALIFIED]
    je .result
    mov byte [fs:HW_CACHE_WARM],0 ; A changed result needs the cold tables.
.result:
    mov [fs:HW_CACHE_QUALIFIED],al
    mov byte [fs:HW_CACHE_CHECKED],1
    test al,al
    jnz .passed
    mov byte [fs:HW_CACHE_CHECKED],2
    post_code 0x1A
    jmp .normal
.passed:
    post_code 0x1E
.normal:
    mov al,0x70
    out 0x70,al
.return:
    pop es
    pop ds
    popad
    popf
    ret

cache_test_end:
cache_test_segments db 2,8,4 ; Stock codes: 128,512,256 KiB.
acc_cache_failed db 'Cache test failed',0
pb430_cache_labels
