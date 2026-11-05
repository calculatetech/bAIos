    call board_video_prepare
    jc .prepare_failed
    pushf
    cli
    pushad
    push ds
    push es
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
    mov ax,0xFFFF
    mov dx,0xC000
    mov cl,2
    call pnp_rom_enter
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
.prepare_failed:
    stc
    ret
