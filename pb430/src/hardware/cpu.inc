%include "pc/cpu.inc"
%include "pc/smm.inc"

board_cpu_detect_name:
    jmp cpu_detect_sl_name

board_cpu_sl_query:
    call cpu_detect_sl
    mov dx,0                 ; CPU evidence does not qualify board SL functions.
    ret

board_smm_prepare:
    call board_cpu_sl_query
    jmp smm_install
