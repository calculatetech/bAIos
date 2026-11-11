    pushf
    pushad
    push es
    movzx cx,byte [fs:C_POST_DELAY]
    imul cx,2500               ; Each saved step is five seconds.
    jcxz .done
    mov ax,0x40
    mov es,ax
    mov byte [es:KB_POST_STATE],1
    sti
.wait:
    call post_keyboard_wait    ; Existing Pause/Delete and pending LED owners.
    call post_wait_2ms
    loop .wait
    call setup_post_gate       ; Consume Delete, then close the existing gate.
.done:
    pop es
    popad
    popf
    ret
