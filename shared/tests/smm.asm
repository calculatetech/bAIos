bits 16
org 0

%ifndef SMM_TARGET
%define SMM_TARGET 0xA0000
%endif

db 'SMM1'
dw smm_install, handler_image, handler_end-handler_image

; The external source latch acknowledges either source, but only 1 is a command.
%macro board_smm_ack 0
    mov dx,0xB2
    in al,dx
    out dx,al
    cmp al,1
    sete al
%endmacro

%include "shared/src/pc/smm.inc"
handler_image:
    smm_handler installed_handler,SMM_TARGET
handler_end:
