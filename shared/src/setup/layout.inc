; Native text setup. Retained VGA, keyboard and RTC services own hardware.
%define U_PAGE       0x00F5
%define U_FOCUS      0x00F6 ; 0 sidebar, 1 page fields
%define U_FIELD      0x00F7 ; Standard:date=0,time=1,format=2.
%define U_EDIT       0x00F8 ; 0 normal, 1 date, 2 time
%define U_POSITION   0x00F9
%define U_CONFIRMED  0x00FA ; Confirmed clock values awaiting complete RTC repair.
%define U_CLOCK24    0x00FB ; Draft display preference:0=12-hour,1=24-hour.
%define U_THEME      0x00FC ; Draft color theme0..8.
%define U_THEME_ACTIVE 0x00FD ; Shared renderers map colors only inside Setup.
%define U_BUFFER     0x0100 ; Up to11 visible ASCII bytes and terminator.
%define U_DATE       0x0120
%define U_TIME       0x012C
%define U_DST        0x0138
%define U_HOUR       0x0139 ; Canonical24-hour BCD, including partial RTC repairs.
%define U_MINUTE     0x013A
%define U_SECOND     0x013B
%define U_SAVE_TRACE 0x0185 ; Last verified CMOS index, expected byte, read byte.
; 80-column layout: sidebar 0..20, labels 24..47, values 49..76.
%define UI_LABEL_COL 24
%define UI_LABEL_WIDTH 24
%define UI_VALUE_COL (UI_LABEL_COL + UI_LABEL_WIDTH + 1)
%define UI_VALUE_WIDTH 28
%define UI_POPUP_COL 24
%define UI_POPUP_WIDTH 54
%define UI_POPUP_TEXT 26
%define UI_TYPE_WIDTH 16
%define UI_GEOMETRY_WIDTH 8

%macro ui_text 4
    mov di, ((%1) * 80 + (%2)) * 2
    mov si, %3
    mov bh, %4
    call setup_text
%endmacro
