; ACCORDER shares the ACCPROBE admission and machine-state envelope.
; It writes only scratch RAM and the established temporary A20/parity controls.
order_main:
    mov dx,order_pending
    mov cx,order_pending_end-order_pending
    call stdout
    jc output_failed
    call phase
    jc test_failed
    call report
    jc output_failed
    inc byte [order_phase]
    cmp byte [order_phase],3
    je .done
    xor byte [order_column],1
    mov si,order_linear
    cmp byte [order_column],0
    je .name
    mov si,order_column_name
.name:
    mov di,order_name
    mov cx,9
    rep movsb
    mov si,order_name
    mov di,order_pending_name
    mov cx,9
    rep movsb
    jmp order_main
.done:
    ret

order_run:
    mov byte [operation],0
    call sweep
    jc .done
    mov byte [operation],1
    call sweep
    jc .done
    mov byte [operation],2
    mov byte [order_measure],0
    call .walk
    jc .done
    mov byte [order_measure],1
    mov byte [passes],4
.measure:
    call .walk
    jc .done
    dec byte [passes]
    jnz .measure
    mov byte [operation],1
    call sweep
.done:
    ret
.walk:
    mov dword [order_pointer],0x100000
    call sweep
    jc .done
    cmp dword [order_pointer],0x100000
    je .done
    mov eax,[order_pointer]
    mov [failure_actual],eax
    mov byte [failed],1
    mov byte [failure_kind],4
    stc
    ret

order_l2 db 0
order_phase db 0
order_column db 0
order_measure db 0
order_pointer dd 0
order_linear db 'Linear   '
order_column_name db '4K-column'
order_pending db 'Building, checking and reading '
order_pending_name db 'Linear   ',13,10
order_pending_end:
order_pointer_failure db 'invalid pointer or chain endpoint: '
order_bad_pointer db '00000000.',13,10
order_pointer_failure_end:
