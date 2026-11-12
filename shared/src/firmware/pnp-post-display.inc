; The final table consumes the journal while its private code remains live.
pnp_publish_finish:
    call post_summary_pause
    call pnp_publish
    call post_debug_summary
    mov byte [fs:S_POST_ESCD_ROW],0
    cmp byte [fs:C_PNP+PNP_CLEAR],0
    je .table
    mov byte [fs:S_POST_ESCD_ROW],11+BOARD_ATA_DEVICE_COUNT
    mov al,10
    call post_status
.table:
    push bx
    mov bx,pnp_post_table
    call pnp_post_invoke
    pop bx
    call pnp_finish_entry
pnp_post_summary_complete:
    jmp post_summary_base_memory

; The retained display owns cursor movement and console scrolling.
pnp_console_callback:
    pushad
    push ds
    push es
    push fs
    push gs
    cmp ah,0x0E
    jne .video
    cmp al,13
    je .video
    push ax
    mov ax,0x40
    mov gs,ax
    pop ax
    cmp byte [gs:0x51],24
    jne .video
    cmp al,10
    je .scroll
    cmp byte [gs:0x50],79
    jne .video
.scroll:
    cmp byte [fs:S_POST_ESCD_ROW],0
    je .video
    cmp byte [fs:S_POST_ESCD_ROW],25
    ja .video
    dec byte [fs:S_POST_ESCD_ROW]
    jnz .video
    dec byte [fs:S_POST_ESCD_ROW]
.video:
    int 0x10
    pop gs
    pop fs
    pop es
    pop ds
    popad
    retf
