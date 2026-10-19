bits 16
org 0x7C00
%include "test-configuration.inc"
cmp dl,TEST_EXPECT_BOOT_UNIT
jne bad
mov al,0x6B
jmp terminal
bad:
mov al,0x7B
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
