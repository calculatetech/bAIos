; Leave the ROM header, diagnostic signatures and callback before the banner.
; Sixteen-byte rows form a readable banner in a hex viewer's ASCII column.
times 0x20-($-$$) db ' '
rom_identification:
    db 'bAIos ',CFG_IDENTITY_MODEL
    times 16-($-rom_identification) db ' '
.version:
    db 'v',CFG_IDENTITY_VERSION
    times 16-($-.version) db ' '
    db '    [o_o]       '
    db '    /|_|\       '
rom_identification_end:
