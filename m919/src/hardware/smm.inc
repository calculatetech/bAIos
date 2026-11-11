; UMC Intel-compatible software SMI; reference control fields are request-local.
; Intel ICU uses a 16-bit byte length, so each reservation must be below 64 KiB.
db 0x55,0xAA,0x04,0xCB
times 8-($-$$) db 0xFF
db 'BAICLK1',0
dw board_clock_command,CFG_ROM_CODE_SEGMENT
db 'BAISMM1',0
db 0                         ; Visible E-bank checksum is refreshed after shadowing.
%include "hardware/rom-identity.inc"
%include "pc/smm.inc"
; Pre-install qualification is independent of final readiness. No enable writes.
m919_smm_qualify:
    pushfd
    pushad
    call CFG_ROM_CODE_SEGMENT:board_smm_cpu_query
    mov edi,eax
    xor ebp,ebp
    test ax,ax
    jz .result
    mov dx,0xCF8
    in eax,dx
    mov esi,eax
    mov eax,SMM_HB
    out dx,eax
    mov dx,0xCFC
    in eax,dx
    cmp eax,0x88811060
    jne .restore
    mov eax,SMM_SB
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC
    in eax,dx
    cmp eax,0x886A1060
    je .supported
    cmp eax,0x888A1060
    jne .restore
.supported:
    inc bp
.restore:
    mov eax,esi
    mov dx,0xCF8
    out dx,eax
.result:
    mov eax,edi
    mov dx,bp
    mov bp,sp
    mov [ss:bp+28],ax
    mov [ss:bp+20],dx
    popad
    popfd
    ret

; Startup owns bootstrap RAM before RAM tests; PM control is not left enabled.
m919_smm_initialize:
    pushfd
    cli
    pushad
    push ds
    push es
    mov byte [fs:HW_SMM_STATUS],0
    mov byte [fs:HW_SMM_ERROR],0
    mov word [fs:HW_SMM_BOOT_TRACE],0
    mov byte [fs:HW_SMM_TRACE_VALID],0
    mov dx,0xCF8
    in eax,dx
    push eax
    smm_read SMM_HB,0
    in eax,dx
    cmp eax,0x88811060
    jne .restore
    ; APM also lives in E; retain it before any later shadow policy, on all CPUs.
    smm_read SMM_HB,0x55
    push ax
    and al,0xBF
    out dx,al
    push cs
    pop ds
    push cs
    pop es
    xor si,si
    xor di,di
    mov cx,0x8000
    cld
    rep movsw
    pop ax
    out dx,al
    call m919_smm_qualify
    test dx,1
    jz .restore
    call m919_smm_quiesce
    smm_read SMM_SB,0x46
    and al,0xBF
    out dx,al
    smm_read SMM_SB,0x76
    and al,0xCF
    out dx,al
    smm_write SMM_HB,0x5C,0
    smm_read SMM_HB,0x5D
    and al,0xF0
    out dx,al
    smm_read SMM_HB,0x60
    and al,0xDE
    or al,1
    out dx,al
    mov byte [fs:HW_SMM_STATUS],2
    push cs
    pop ds
    mov ax,0xA000
    mov es,ax
    mov si,board_smm_image
    mov di,0x8000
    mov cx,board_smm_image_end-board_smm_image
    call m919_smm_prepare
    jc .failed
    mov ax,0x3000
    mov es,ax
    mov si,board_smm_image
    mov di,0x8000
    mov cx,board_smm_image_end-board_smm_image
    call m919_smm_prepare
    jc .failed
    call m919_smm_close
    jc .failed
    smm_read SMM_HB,0x5C
    test al,al
    jnz .failed
    smm_read SMM_HB,0x5D
    test al,15
    jnz .failed
    mov byte [fs:HW_SMM_STATUS],3
    mov ax,1
    call m919_smm_command
    jc .failed
    mov byte [fs:HW_SMM_STATUS],4
    xor ax,ax
    call m919_smm_command
    jc .failed
    mov byte [fs:HW_SMM_STATUS],1
    jmp .restore
.failed:
    mov [fs:HW_SMM_ERROR],al
    call m919_smm_quiesce
    cmp byte [fs:HW_SMM_STATUS],3
    jb .close_failed
    ; Early POST only: sources are masked and neither VGA nor DMA has started.
    mov ax,0x3000
    mov es,ax
    mov al,[es:0x8000+board_smm_trace-board_smm_image]
    mov [fs:HW_SMM_BOOT_TRACE],al
    smm_read SMM_HB,0x60
    or al,1
    out dx,al
    in al,dx
    test al,1
    jz .trace_unavailable
    mov ax,0xA000
    mov es,ax
    mov al,[es:0x8000+board_smm_trace-board_smm_image]
    mov [fs:HW_SMM_FINAL_TRACE],al
    jmp .close_failed
.trace_unavailable:
    mov byte [fs:HW_SMM_FINAL_TRACE],15
.close_failed:
    call m919_smm_close
    cmp byte [fs:HW_SMM_STATUS],3
    jb .restore
    mov byte [fs:HW_SMM_TRACE_VALID],0xA5
.restore:
    pop eax
    mov dx,0xCF8
    out dx,eax
.done:
    pop es
    pop ds
    popad
    popfd
    retf

m919_smm_prepare:
    call m919_smm_qualify
    jmp smm_install

m919_smm_prepare_entry:
    call m919_smm_prepare
    retf

m919_smm_command_entry:
    pushfd
    push fs
    call CFG_ROM_CODE_SEGMENT:board_smm_state_loader
    cmp byte [fs:HW_SMM_STATUS],1
    jne .unavailable
    cmp ax,2
    jne .qualified
    push ax
    push dx
    call m919_smm_qualify
    test dx,1
    pop dx
    pop ax
    jz .unavailable
    push eax
    push ebx
    push edx
    mov dx,0xCF8
    in eax,dx
    mov ebx,eax
    smm_read SMM_SB,0x76
    test al,0x30
    mov eax,ebx
    mov dx,0xCF8
    out dx,eax
    pop edx
    pop ebx
    pop eax
    jnz .unavailable
.qualified:
    pop fs
    call m919_smm_command
    push ax
    mov al,RTC_NMI_SELECT_MASK | 0x0D
    out 0x70,al
    pop ax
    jc .error
    popfd
    clc
    retf
.unavailable:
    pop fs
    mov ax,1
.error:
    popfd
    stc
    retf

m919_smm_close:
    smm_read SMM_HB,0x60
    and al,0xFE
    out dx,al
    in al,dx
    shr al,1
    ret                         ; CF is the manual-open readback bit.

; Firmware reset paths mask both software requests and all PM monitors.
%macro smm_quiesce_code 0
    pushfd
    pushad
    mov dx,0xCF8
    in eax,dx
    mov ebp,eax
    smm_write SMM_SB,0xA0,0
    smm_read SMM_SB,0xA3
    and al,0x3F
    out dx,al
    mov eax,ebp
    mov dx,0xCF8
    out dx,eax
    popad
    popfd
%endmacro

m919_smm_quiesce:
    smm_quiesce_code
    ret

; AX=ping(0)/relocate(1)/private clock trial(2). AX=status, CF=error.
; Keep ordinary RAM unchanged while caches are off; only SMRAM receives writes.
m919_smm_command:
    m919_smm_command_code
    ret

%macro board_smm_ack 0
    mov byte [cs:0x8000+board_smm_trace-board_smm_image],4
    cmp dword [cs:0xFFDC],SMM_REQUEST
    jne %%cookie_done
    or byte [cs:0x8000+board_smm_trace-board_smm_image],2
%%cookie_done:
    mov dx,0xCF8
    in eax,dx
    mov ebp,eax
    smm_read SMM_SB,0xA3
    mov bl,al
    test al,0x40
    jz %%source_done
    or byte [cs:0x8000+board_smm_trace-board_smm_image],1
%%source_done:
    smm_write SMM_SB,0xA2,0
    smm_read SMM_SB,0xA3
    or al,0x20
    out dx,al
    and al,0x9F
    out dx,al
    mov eax,ebp
    mov dx,0xCF8
    out dx,eax
    mov al,bl
    shr al,6
    and al,1
    cmp al,1
    jne %%done
    cmp dword [cs:0xFFDC],SMM_REQUEST
    jne %%done
    cmp word [cs:0xFFD4],2
    je board_clock_smm_entry
    cmp word [cs:0xFFD4],3
    je board_clock_smm_entry
    cmp word [cs:0xFFD4],4
    je board_escd_smm_entry
    cmp word [cs:0xFFD4],5
    je board_escd_smm_entry
%%done:
%endmacro
board_smm_image:
    smm_handler board_smm_entry,0xA0000
; Both headers stay in read-only firmware; together they also reserve ESCD NVS.
times 0x800-($-$$) db 0xFF
rom_reservation_tail:
    db 0x55,0xAA,0x7C,0xCB
    times 0x1C-($-rom_reservation_tail) db 0
rom_reservation_tail_checksum:
    db 0
    times 0x20-($-rom_reservation_tail) db 0
%include "hardware/clock-trial.inc"
%include "hardware/escd-smm.inc"
board_smm_trace:
    db 0
board_smm_image_end:
times -((0x8000+($-board_smm_image)) > SMM_ESCD_BUFFER) db 0

m919_idle_command:
    mov ax,3
    m919_smm_command_code 1
    mov [ds:HW_SMM_IDLE_STATUS],al
    ret
m919_idle_pm32:
    call m919_idle_command
    retf

%define apm_int15 m919_apm_int15
m919_apm_entry:
%include "firmware/apm.inc"
%undef apm_int15
