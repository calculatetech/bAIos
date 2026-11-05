%ifndef PNP_RUNTIME_STATE_INCLUDED
%define PNP_RUNTIME_STATE_INCLUDED
%include "pc/pnp-post-state.inc"
; During POST these existing control fields own the linked provider list.
; After promotion PNP_RUNTIME is an EBDA-relative offset, never an arena pointer.
PNP_PROVIDERS equ PNP_JOURNAL_FLAGS
PNP_PROVIDER_COUNT equ PNP_JOURNAL_COUNT
PNP_RUNTIME equ PNP_JOURNAL_FLAGS
PNP_PROVIDER_SIZE equ 28
P_V_NEXT equ 0
P_V_SEG equ 4
P_V_HEADER equ 6
P_V_BCV equ 8
P_V_DISCONNECT equ 10
P_V_BEV equ 12
P_V_STATUS equ 14
P_V_INDICATORS equ 16
P_V_FLAGS equ 17
P_V_BDF equ 18
P_V_CSN equ 20
P_V_PORT equ 22
P_V_UNITS equ 24
P_V_LDN equ 26
PNP_PROVIDER_BYTES equ PNP_PROVIDER_SIZE-4
; The runtime header precedes contiguous packed payloads, not POST link records.
P_T_MAGIC equ 0
P_T_COUNT equ 4
P_T_CURSOR equ 8
P_T_ACTIVE equ 12
P_T_FLAGS equ 16
P_T_DRIVE equ 17
P_T_HDD equ 18
P_T_PREFIX_KIB equ 19
P_T_OLD13 equ 20
P_T_OLD18 equ 24
P_T_OLD19 equ 28
P_T_FDPT0 equ 32
P_T_FDPT1 equ 36
P_T_ORIGINAL_KIB equ 40
P_T_EXTERNAL_KIB equ 42
P_T_DEST_SEG equ 44
P_T_TOTAL_KIB equ 46
P_T_EQUIPMENT equ 48
P_T_BASE_SEG equ 50
P_T_HOOK18 equ 52
P_T_HOOK19 equ 56
P_T_SIZE equ 60
PNP_RUNTIME_MAGIC equ 0x33504E50
%endif
