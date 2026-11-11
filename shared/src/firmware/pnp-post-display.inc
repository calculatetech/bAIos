; The final table consumes the journal while its private code remains live.
pnp_publish_finish:
    call post_summary_pause
    call pnp_publish
    call post_debug_summary
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
    int 0x10
    pop gs
    pop fs
    pop es
    pop ds
    popad
    retf
