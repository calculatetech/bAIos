%ifndef PC_ROM_STATE_INCLUDED
%define PC_ROM_STATE_INCLUDED
; Existing boot/returning-ROM state ABI, shared by early static reports.
%define R_SCANNED 0x3D
%define R_NEXT    0x3E
%define R_ENTRY   0x40
%define R_SS      0x44
%define R_SP      0x46
%define B_CURSOR  0x48
%define B_ACTIVE  0x49
%define B_DRIVE   0x4A
%define B_ROM19   0x4C
%endif
