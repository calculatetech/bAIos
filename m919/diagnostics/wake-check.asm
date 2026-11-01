; RTC prerequisite only: no SMI, clock request, cache or PS/2 operations.
bits 16
org 0x100
%ifndef SMM_STATUS
%error "Pass the board SMM status offset"
%endif
%ifndef STATE_KIB
%error "Pass the configured EBDA size"
%endif
%ifndef NMI_POLICY
%error "Pass the configured board NMI policy"
%endif

%ifdef IDLE_TRIAL
%ifndef IDLE_STATUS
%error "Pass the board idle result offset"
%endif
%endif

start:
    mov ax,cs
    mov ds,ax
    mov ss,ax
    mov sp,stack_top
    pushf
    pop ax
    mov [entry_flags],ax
    cld
%ifndef IDLE_TRIAL
    smsw ax
    test al,1
    jnz protected_dos
%endif
    test word [entry_flags],0x200
    jz busy
    mov ax,0xE000
    mov es,ax
    cmp dword [es:0],0x53494142
    jne invalid
    cmp dword [es:4],0x00314D4D
    jne invalid
%ifdef CLOCK_TRIAL
    cmp dword [es:8],0x43494142
    jne invalid
    cmp dword [es:12],0x00314B4C
    jne invalid
    mov eax,[es:16]
    mov [clock_entry],eax
%endif
    xor ax,ax
    mov es,ax
    mov ax,[es:0x40E]
    cmp ax,0x8000
    jb invalid
    cmp ax,0xA000-STATE_KIB*64
    ja invalid
    mov es,ax
    cmp byte [es:0],STATE_KIB
    jne invalid
    cmp byte [es:SMM_STATUS],1
    jne invalid
%ifdef IDLE_TRIAL
    mov ax,0x5300
    xor bx,bx
    int 0x15
    jc invalid
    test cx,4
    jz invalid
    test cx,0x18
    jnz busy
    mov ax,0x5301
    xor bx,bx
    int 0x15
    jc busy
    mov byte [idle_connected],1
    cmp byte [0x80],0
    je .idle_timer
    mov si,0x81
.idle_arg:
    lodsb
    cmp al,' '
    je .idle_arg
    and al,0xDF
    cmp al,'K'
    jne invalid
    mov byte [idle_keyboard],1
    mov byte [message],'K'
    mov dx,key_message
    mov ah,9
    int 0x21
.idle_drain:
    mov ah,1
    int 0x16
    jz .idle_timer
    xor ah,ah
    int 0x16
    jmp .idle_drain
.idle_timer:
%endif

    cli
    in al,0x21
    mov [master_mask],al
    test al,1
    jnz busy_restore
    in al,0xA1
    mov [slave_mask],al
    mov al,0x0B
    call rtc_read
    mov [rtc_b],al
    test al,0xF0
    jnz busy_restore
    call irq8_pending
    jnz busy_restore
    mov al,0x0A
    call rtc_read
    and al,0x70
    cmp al,0x20
    jne rtc_bad_restore
    mov al,0x0D
    call rtc_read
    test al,0x80
    jz rtc_bad_restore
    mov al,1
    call rtc_read
    mov [alarm_second],al
    mov al,3
    call rtc_read
    mov [alarm_minute],al
    mov al,5
    call rtc_read
    mov [alarm_hour],al
    call rtc_policy
    sti

    mov ah,2
    int 0x1A
    jc rtc_bad
    mov al,dh
    call from_bcd
    add al,2
    cmp al,60
    jb .seconds
    sub al,60
    push ax
    mov al,cl
    call from_bcd
    inc al
    cmp al,60
    jb .minutes
    xor al,al
    push ax
    mov al,ch
    call from_bcd
    inc al
    cmp al,24
    jb .hours
    xor al,al
.hours:
    call to_bcd
    mov ch,al
    pop ax
.minutes:
    call to_bcd
    mov cl,al
    pop ax
.seconds:
    call to_bcd
    mov dh,al
    mov [target_cx],cx
    mov [target_dx],dx
    mov ax,0x354A
    int 0x21
    mov [old_vector],bx
    mov [old_vector+2],es
    mov dx,alarm_callback
    mov ax,0x254A
    int 0x21
    mov cx,[target_cx]
    mov dx,[target_dx]
    mov ah,6
    int 0x1A
    jc arm_bad
    xor ax,ax
    mov es,ax
    cli
    mov eax,[es:0x46C]
    mov [start_ticks],eax
%ifdef IDLE_TRIAL
    cmp byte [idle_keyboard],0
    je .idle_wait
    in al,0x21
    or al,1
    and al,0xFD
    out 0x21,al
    mov ax,[es:0x41C]
    mov [key_tail],ax
.idle_wait:
    mov ax,0x5305
    xor bx,bx
    int 0x15
    jc .idle_error
    push es
    xor ax,ax
    mov es,ax
    mov ax,[es:0x40E]
    mov es,ax
    cmp byte [es:IDLE_STATUS],0
    pop es
    jne .idle_error
    cli
    cmp byte [idle_keyboard],0
    jne .idle_key
    mov eax,[es:0x46C]
    sub eax,[start_ticks]
    jnc .idle_ticks
    add eax,0x1800B0
.idle_ticks:
    cmp eax,2
    jae .idle_success
    jmp .idle_timeout
.idle_key:
    mov ax,[es:0x41C]
    cmp ax,[key_tail]
    jne .idle_success
.idle_timeout:
    cmp byte [observed],0
    je .idle_wait
    mov byte [code],'6'
    jmp cleanup
.idle_success:
    mov byte [code],'0'
    jmp cleanup
.idle_error:
    mov byte [code],'7'
    jmp cleanup
%endif
%ifdef CLOCK_TRIAL
    cmp byte [observed],0
    jne clock_expired
    call irq8_pending
    jnz clock_expired
    mov ax,2
    call far [clock_entry]
    cmp ax,4
    jne .clock_reply
    mov ax,7
.clock_reply:
    test ax,ax
    jz .clock_wait
    cmp ax,6
    je .clock_wait
    cmp ax,9
    jbe .clock_error
    mov ax,7
.clock_error:
    add al,'0'
    mov [code],al
    jmp cleanup
.clock_wait:
    add al,'0'
    mov [clock_result],al
%endif
    sti
    mov edi,0x04000000
.wait:
    cmp byte [observed],0
    jne .success
    cli
    mov eax,[es:0x46C]
    sti
    sub eax,[start_ticks]
    jnc .elapsed
    add eax,0x1800B0
.elapsed:
    cmp eax,91
    jae .timeout
    dec edi
    jnz .wait
.timeout:
    mov byte [code],'4'
    jmp cleanup
.success:
%ifdef CLOCK_TRIAL
    mov al,[clock_result]
    mov [code],al
%else
    mov byte [code],'0'
%endif
    jmp cleanup
arm_bad:
    mov byte [code],'3'
%ifdef CLOCK_TRIAL
    jmp cleanup
clock_expired:
    mov byte [code],'2'
%endif
cleanup:
    cli
    mov ah,7
    int 0x1A
    mov ah,[rtc_b]
    mov al,0x0B
    call rtc_write
    ; Cancel leaves a latched PIC edge; int70 must acknowledge that edge too.
    mov cx,0xFFFF
.drain:
    call irq8_pending
    jz .drained
    sti
    nop
    cli
    loop .drain
    mov byte [code],'5'
.drained:
    mov ah,[alarm_second]
    mov al,1
    call rtc_write
    mov ah,[alarm_minute]
    mov al,3
    call rtc_write
    mov ah,[alarm_hour]
    mov al,5
    call rtc_write
    mov al,[master_mask]
    out 0x21,al
    mov al,[slave_mask]
    out 0xA1,al
    call rtc_policy
    sti
    lds dx,[old_vector]
    mov ax,0x254A
    int 0x21
    push cs
    pop ds
    jmp print

irq8_pending:
    mov al,0x0A
    out 0xA0,al
    in al,0xA0
    mov ah,al
    mov al,0x0B
    out 0xA0,al
    in al,0xA0
    or ah,al
    mov al,0x0A
    out 0xA0,al
    test ah,1
    ret
rtc_read:
    or al,NMI_POLICY
    out 0x70,al
    in al,0x84
    in al,0x71
    ret
rtc_write:
    or al,NMI_POLICY
    out 0x70,al
    in al,0x84
    mov al,ah
    out 0x71,al
    ret
rtc_policy:
    mov al,NMI_POLICY | 0x0D
    out 0x70,al
    ret
from_bcd:
    mov ah,al
    and al,15
    shr ah,4
    aad
    ret
to_bcd:
    aam
    shl ah,4
    or al,ah
    ret
alarm_callback:
    mov byte [cs:observed],1
    iret
busy_restore:
    mov byte [code],'2'
    jmp policy_restore
rtc_bad_restore:
    mov byte [code],'3'
policy_restore:
    call rtc_policy
    sti
    jmp print
rtc_bad:
    mov byte [code],'3'
    call rtc_policy
    jmp print
busy:
    mov byte [code],'2'
    jmp print
invalid:
    mov byte [code],'1'
    jmp print
protected_dos:
    mov byte [code],'X'
print:
%ifdef IDLE_TRIAL
    cmp byte [idle_connected],0
    je .idle_disconnected
    mov ax,0x5304
    xor bx,bx
    int 0x15
.idle_disconnected:
%endif
    push word [entry_flags]
    popf
    mov dx,message
    mov ah,9
    int 0x21
    mov ax,0x4C01
    cmp byte [code],'0'
    jne .exit
    xor al,al
.exit:
    int 0x21

%ifdef IDLE_TRIAL
message: db 'T'
%elifdef CLOCK_TRIAL
message: db 'C'
%else
message: db 'W'
%endif
code: db '?',13,10,'$'
observed: db 0
rtc_b: db 0
alarm_second: db 0
alarm_minute: db 0
alarm_hour: db 0
master_mask: db 0
slave_mask: db 0
entry_flags: dw 0
target_cx: dw 0
target_dx: dw 0
old_vector: dd 0
start_ticks: dd 0
%ifdef CLOCK_TRIAL
clock_entry: dd 0
clock_result: db '6'
%endif
%ifdef IDLE_TRIAL
idle_connected: db 0
idle_keyboard: db 0
key_tail: dw 0
key_message: db 'Press a key within two seconds.',13,10,'$'
%endif
times 512 db 0
stack_top:
