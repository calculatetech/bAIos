; The unmodified Presario VGA installer calls F000:F065 before returning.
times 0xF065-($-$$) db 0xFF
vga_int42_compat:
    cmp ah,0x1D
    jae .unsupported
    jmp 0xC000:0x2897
.unsupported:
    iret
