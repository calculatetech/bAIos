; PB4309325/94E9 staged copies; never replace the executing F000 mapping.
shadow_system_bios:
    post_code 0x34
    pushf
    cli
    pushad
    push ds
    push es
    mov al,2
    call acc_read
    test al,0x10
    jnz .already
    mov ax,0xF000
    mov ds,ax
    mov ax,0x3000
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x8000
    rep movsw
    jmp 0x3000:.staged
.staged:
    post_code 0x35
    mov al,2
    call acc_read
    and al,0xDF
    or al,0x10 ; F000 alone: the unused E800 setup resource is not copied.
    mov ah,al
    mov al,2
    call acc_write
    mov ax,0x3000
    mov ds,ax
    mov ax,0xF000
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x8000
    rep movsw
    wbinvd
    jmp 0xF000:.mapped
.mapped:
    post_code 0x36
    mov al,2
    call acc_read
    or al,0x20
    mov ah,al
    mov al,2
    call acc_write
    call shadow_memory_finish
.already:
    post_code 0x37
    pop es
    pop ds
    popad
    popf
    ret

; OEM94B1..94E8 follows the shadow copy; retain its mode-specific register00 write.
shadow_memory_finish:
    xor bx,bx
    mov bl,0x80
    mov al,0x12
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,3
    mov ah,al
    mov al,0
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    cmp ah,2
    jne .set
    mov bh,al
    and bh,0x0F
    cmp bh,9
    je .write
.set:
    or al,bl
.write:
    mov ah,al
    mov al,0
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,ah
    out CHIPSET_DATA,al
    out 0xED,al
    ret
shadow_memory_finish_end:

shadow_external_video:
    push ds
    push es
    mov al,2
    call acc_read
    test al,1
    jnz .done
    mov ax,0xC000
    mov ds,ax
    mov ax,0x2000
    mov es,ax
    xor si,si
    xor di,di
    movzx cx,byte [2]
    cmp cx,0x40             ; ACC bit0 controls only the C00032KiB window.
    jbe .extent
    mov cx,0x40
.extent:
    shl cx,8               ; Header512-byte units to words.
    push cx
    rep movsw
    post_code 0x3D ; Provider bytes are staged before the C000 map changes.
    mov al,2
    call acc_read
    and al,0xDF
    or al,1
    mov ah,al
    mov al,2
    call acc_write
    mov ax,0x2000
    mov ds,ax
    mov ax,0xC000
    mov es,ax
    xor si,si
    xor di,di
    pop cx
    rep movsw
    post_code 0x3E ; C000 provider bytes are copied into the selected mapping.
    mov al,2
    call acc_read
    or al,0x20
    mov ah,al
    mov al,2
    call acc_write
.done:
    pop es
    pop ds
    ret

shadow_system_policy:
    post_code 0x38
    push ds
    push es
    mov ax,0xF000
    mov ds,ax
    mov ax,0x3000
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x8000
    rep movsw
    jmp 0x3000:.staged
.staged:
    post_code 0x39
    mov al,2
    call acc_read
    and al,0xCF
    cmp byte [fs:C_CHIP+3],0
    je .map
    or al,0x10
.map:
    mov ah,al
    mov al,2
    call acc_write
    cmp byte [fs:C_CHIP+3],0
    je .protected
    mov ax,0x3000
    mov ds,ax
    mov ax,0xF000
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x8000
    rep movsw
.protected:
    mov al,2
    call acc_read
    or al,0x20
    mov ah,al
    mov al,2
    call acc_write
    wbinvd
    jmp 0xF000:.return
.return:
    post_code 0x3A
    pop es
    pop ds
    ret

; The caller holds L1/L2 off. Stage the whole window before changing its map.
shadow_additional_policy:
    pushad
    push ds
    push es
    cld
    post_code 0xDA
    mov bl,2
    mov dx,0xC800
    mov bp,0x4000
    mov bh,[fs:C_CHIP+10]
    call shadow_optional_window
    mov bl,4
    mov dx,0xD000
    mov bp,0x8000
    mov bh,[fs:C_CHIP+11]
    call shadow_optional_window
    cmp byte [fs:HW_VGA_REQUIRED],1
    je .done ; Keep the onboard VGA source hidden by its established E000 map.
    mov bl,8
    mov dx,0xE000
    mov bh,[fs:C_CHIP+12]
    call shadow_optional_window
.done:
    wbinvd
    post_code 0xDB
    pop es
    pop ds
    popad
    ret

shadow_optional_window:
    mov al,2
    call acc_read
    test bh,bh
    jz .disable
    test al,bl
    jnz .done
    mov ds,dx
    mov ax,0x2000
    mov es,ax
    xor si,si
    xor di,di
    mov cx,bp
    rep movsw
    mov al,2
    call acc_read
    and al,0xDF
    or al,bl
    mov ah,al
    mov al,2
    call acc_write
    call acc_read
    cmp al,ah
    jne .failed
    mov ax,0x2000
    mov ds,ax
    mov es,dx
    xor si,si
    xor di,di
    mov cx,bp
    rep movsw
    xor si,si
    xor di,di
    mov cx,bp
    repe cmpsw
    jne .failed
    mov al,2
    call acc_read
    jmp .protect
.disable:
    mov ah,bl
    not ah
    and al,ah
.protect:
    or al,0x20
    mov ah,al
    mov al,2
    call acc_write
    call acc_read
    cmp al,ah
    jne .failed
.done:
    ret
.failed:
    mov al,2
    call acc_read
    or al,0x20
    mov ah,al
    mov al,2
    call acc_write
    post_code_early 0xDC
    jmp hard_halt

initialize_video:
    post_code 0x3C
    pushf
    cli
    pushad
    push ds
    push es
    mov ax,0xC000
    mov ds,ax
    cmp word [0],0xAA55
    je .present
    mov byte [fs:HW_VGA_REQUIRED],1
    mov al,2
    call acc_read
    and al,0xD7
    mov ah,al
    mov al,2
    call acc_write
    mov ax,0xE000
    mov ds,ax
    mov ax,0x2000
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x4000
    rep movsw
    post_code 0x3D
    mov al,2
    call acc_read
    or al,9
    mov ah,al
    mov al,2
    call acc_write
    mov ax,0xE000
    mov es,ax
    xor ax,ax
    xor di,di
    mov cx,0x4000
    rep stosw
    mov ax,0x2000
    mov ds,ax
    mov ax,0xC000
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x4000
    rep movsw
    post_code 0x3E
.present:
    mov ax,0xC000
    mov ds,ax
    cmp word [0],0xAA55
    jne .failed
    movzx bp,byte [2]
    test bp,bp
    jz .failed
    cmp bp,0x80            ; The declared provider must fit the C000 segment.
    ja .failed
    cmp byte [fs:HW_VGA_REQUIRED],1
    jne .external
    cmp bp,0x40            ; The retained onboard provider is exactly32KiB.
    jne .failed
.external:
    xor bx,bx
    xor si,si
.sum_unit:
    mov cx,512
.sum:
    lodsb
    add bl,al
    loop .sum
    dec bp
    jnz .sum_unit
    test bl,bl
    jnz .failed
    post_code 0x3F ; The complete declared provider header and checksum passed.
    mov al,2
    call acc_read
    or al,0x20
    mov ah,al
    mov al,2
    call acc_write
    ; Existing ROM-return owner: restore our stack even if the VGA poisons it.
    mov [fs:HW_VIDEO_SS],ss
    mov [fs:HW_VIDEO_SP],sp
    xor ax,ax
    mov es,ax
    xor di,di
    call 0xC000:3
    cli
    xor ax,ax
    mov fs,ax
    mov fs,[fs:0x40E]
    mov ss,[fs:HW_VIDEO_SS]
    mov sp,[fs:HW_VIDEO_SP]
    cld
    xor ax,ax
    mov ds,ax
    mov es,ax
    ; Far aliases retain the existing C0000..CFFFF physical handler window.
    movzx eax,word [0x42]
    shl eax,4
    movzx edx,word [0x40]
    add eax,edx
    cmp eax,0xC0000
    jb .failed
    cmp eax,0xD0000
    jae .failed
    mov eax,[0x40]
%ifdef PB430_VGA60
    cmp byte [fs:HW_VGA_REQUIRED],1
    jne .fallback_ready
    ; VGA 1.41 chains unknown calls to INT42; keep its guarded ROM bridge.
    mov eax,0xF000F065
.fallback_ready:
%endif
    mov [0x108],eax
    mov ax,3
    int 0x10
    pop es
    pop ds
    popad
    popf
    clc
    ret
.failed:
    pb_stage 0xE5
    pop es
    pop ds
    popad
    popf
    stc
    ret
