; Static SMBIOS2.2 identification. No PnP interface or device inventory.
%define ID_TABLE_LENGTH (identity_table_end - identity_table)
%define ID_TABLE_ADDRESS (0xF0000 + identity_table - $$)
%define ID_MAX_SIZE (identity_system_end - identity_system)
%define ID_SUM16(x) (((x) & 255) + (((x) >> 8) & 255))
%define ID_SUM32(x) (ID_SUM16(x) + ID_SUM16((x) >> 16))

align 16, db 0xFF
identity_entry:
    db '_SM_'
    db -(350 + 0x1F + 2 + 2 + ID_SUM16(ID_MAX_SIZE)) & 255
    db 0x1F, 2, 2
    dw ID_MAX_SIZE
    db 0                       ; Entry point revision.
    times 5 db 0
    db '_DMI_'
    db -(408 + ID_SUM16(ID_TABLE_LENGTH) + ID_SUM32(ID_TABLE_ADDRESS) + 3 + 0x22) & 255
    dw ID_TABLE_LENGTH
    dd ID_TABLE_ADDRESS
    dw 3
    db 0x22
identity_table:
    db 0, 0x13
    dw 0
    db 1, 2
    dw 0xF000
    db 3, (CFG_ROM_SIZE / 65536)-1 ; Date index, configured physical ROM size.
    dq 8                       ; Characteristics unspecified.
    db 0                       ; 2.2 extension byte.
bios_vendor db 'bAIos',0
bios_version db BIOS_VERSION,0
bios_release_date db BIOS_RELEASE_DATE,0,0
identity_system:
    db 1, 0x19
    dw 1
    db 1, 2, 0, 0              ; Manufacturer/product; version/serial unknown.
    times 16 db 0              ; UUID not present.
    db 2                       ; Wake-up type unknown.
    db BOARD_VENDOR,0,BOARD_PRODUCT,0,0
identity_system_end:
    db 127, 4
    dw 2
    dw 0
identity_table_end:
