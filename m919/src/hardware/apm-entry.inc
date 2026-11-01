; Preserve the common INT15 BP frame; E's shared owner returns directly by IRET.
board_apm_int15:
apm_int15:
    jmp 0xE000:m919_apm_entry
