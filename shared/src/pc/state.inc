%define STATE_BASE          0x0020
%define B_DRIVE             0x004A ; Donor router's current physical BIOS boot drive.
%define S_PRESENT           STATE_BASE + 0
%define S_STATUS            STATE_BASE + 1
%define S_COMMAND           STATE_BASE + 2
%define S_COUNT             STATE_BASE + 3
%define S_DONE              STATE_BASE + 4
%define S_ATA_DEVICE        STATE_BASE + 5 ; 00 master,10 slave; second record +200h.
%define S_BUFFER_OFF        STATE_BASE + 6
%define S_BUFFER_SEG        STATE_BASE + 8
%define S_LBA               STATE_BASE + 10
%define S_CAPACITY          STATE_BASE + 14
%define S_DAP_OFF           STATE_BASE + 18
%define S_DAP_SEG           STATE_BASE + 20
%define S_TEST_ATA          STATE_BASE + 22
%define S_TEST_AFTER_STATUS STATE_BASE + 23
%define S_TEST_AFTER_COUNT  STATE_BASE + 24
%define S_TEST_PHASE        STATE_BASE + 25
%define S_WARM_BOOT         STATE_BASE + 26
%define S_RESET_IDT_LIMIT   STATE_BASE + 27
%define STATE_END           STATE_BASE + 29
%define IDENTIFY_BUFFER     0x0800
%define S_EXTENDED_KIB      0x00D0 ; Detected count, follows the relocated EBDA.
%define F_TYPES             0x0080 ; Effective logical floppy types (0..5).
%define S_CPU_SIGNATURE     0x00D4 ; Reset EDX family/model/stepping, not CMOS.
%define S_RTC_REPAIRED      0x00D2 ; Explicit time/date repairs after RTC power loss.
%define S_FDPT              0x00E0 ; Standard 16-byte fixed disk parameter table.
%define S_BLOCK_SIZE        0x00F0 ; 512 bytes, or 516 for legacy ECC long I/O.
%define S_NATIVE_HEADS      0x00F2
%define S_NATIVE_SECTORS    0x00F3
%define S_SETUP_REQUEST     0x00F4 ; Spare EBDA, never a keyboard BDA extension.
%define P_RAM_FLAGS         0x0050 ; Transient POST: active1, skipped2, passed4.
%define P_PHASE             0x0051 ; RAM1, RAM done2, floppy3, IDE4, late cache5.
%define P_ROM_COUNT         0x0052 ; Display count only; not the scanner extent.
%define S_MODEL             0x0140 ; 40 IDENTIFY ASCII bytes plus terminator.
%define S_ATAPI             0x0169 ; Identified packet device, not an INT13 disk.
%define S_PACKET_BYTES      0x013E ; IDENTIFY PACKET command size,12 or16 bytes.
%define S_PACKET_CD         0x013F ; Packet device type5, CD/DVD only.
%define S_IDENTIFY_TRACE    0x016A ; Stage,status,error,count,LBA1,LBA2 (six bytes).
%define C_TYPES             0x0170 ; Loaded policy, separate from UI drafts.
%define C_HDD               0x0171
%define C_BOOT              0x0172
%define C_SEEK              0x0173
%define C_VALID             0x0174
%define C_ERROR             0x0175 ; Sticky causes: clock1,floppy2,settings4,keyboard8,ROM16.
%define C_THEME             0x013C ; Saved Setup color theme, outside clock scratch.
%define C_CLOCK24           0x013D ; Saved presentation, separate from floppy seek scratch176h.
%define C_SLAVE             0x0177
%define C_BASE_VALID        0x017C ; Base policy remains trusted if an extension fails.
%define C_NUMLOCK           0x017D
%define C_SWAP              0x017E
%define C_HALT              0x017F ; 0 All,1 No Errors,2 All Except Keyboard.
%define U_TYPES             0x0180
%define U_HDD               0x0181
%define U_BOOT              0x0182
%define U_SEEK              0x0183
%define U_SLAVE             0x0184
%define U_IDE_DEVICE        0x0188 ; FF channel page, 0 master, 1 slave.
%define C_BOOT_SECOND       0x0189
%define C_BOOT_THIRD        0x018A
%define U_NUMLOCK           0x018B
%define U_SWAP              0x018C
%define U_HALT              0x018D
%define U_BOOT_SECOND       0x018E
%define U_BOOT_THIRD        0x018F
%define C_IDE               0x0190 ; Controller + two12-byte policy records.
%define U_IDE               0x01B0 ; Draft of the same25-byte record.
%define S_IDE               0x01D0 ; Selected physical disk's12-byte policy.
%define S_GEOMETRY          0x01DC ; Explicit BIOS heads/sectors; zero = proven Auto.
%define S_MULTIPLE_MAX      0x01E0
%define S_MULTIPLE          0x01E1
%define S_CHS_ONLY          0x01E2 ; 0 LBA,1 native CHS transport.
%define S_CONTROLLER        0x01E3
%define S_NATIVE_CYLINDERS  0x01E4
%define IDE_TYPE            0
%define IDE_TRANSLATION     1
%define IDE_BLOCK           2
%define IDE_EDD_OFF         3
%define IDE_CYLINDERS       4
%define IDE_HEADS           6
%define IDE_SECTORS         7
%define IDE_PRECOMP         8
%define IDE_LANDING         10
%define IDE_RECORD_SIZE     12
%define IDE_SETTINGS_SIZE   25
%define C_PORTS             0x01E6 ; Eight active device selectors.
%define U_PORTS             0x01EE ; Eight draft selectors, ends before200h.
%define C_BOOT_FOURTH       0x01F6 ; Free gap after the device selectors.
%define U_BOOT_FOURTH       0x01F7
%define P_FLOPPY            5
%define P_MOUSE             6
%define C_CHIP              0x0060 ;24-byte chipset policy in unused EBDA gaps.
%define S_INSTALLED_KIB     0x0078 ; Physical count before optional ISA holes.
%define S_L2_PROBE          0x007A ; Last L2 probe POST result: 14/15/16, zero if skipped.
%define U_CHIP              0x0260
%define CHIP_SIZE           24
%define U_CHIP_SCREEN       0x0278
%define U_CHIP_VALUE        0x0279
%define S_RAM_TEST_BUFFER   0x1800 ; Excluded EBDA scratch for nondestructive RAM bursts.
%define RAM_TEST_BLOCK_SIZE 0x0800

%define KB_FLAGS            0x0017
%define KB_FLAGS2           0x0018
%define KB_HEAD             0x001A
%define KB_TAIL             0x001C
%define KB_BUFFER_START     0x001E
%define KB_BUFFER_END       0x003E
%define KB_EXT_FLAGS        0x0096
%define KB_PAUSE_OWNER      0x00A6 ; IRQ1 wait owner; nested IRQs only decode.
%define KB_PAUSED           0x00A7 ; Pause also suspends Setup and BIOS/DOS callers.
%define KB_LED_FLAGS        0x0097 ; Standard enhanced-keyboard LED state.
%define KB_E1_REMAIN        0x00AC ; Reserved BDA byte, beyond VGA pointer A8..AB.
%define KB_LED_PHASE        0x0099 ; 0 idle, 1/3 send, 2/4 ACK, FF failed
%define KB_LED_SENT         0x009A
%define KB_LED_APPLIED      0x009B
%define KB_LED_WAIT         0x009C
%define KB_LED_RETRIES      0x009D
%define KB_POST_STATE       0x009E ; 0 runtime,1 detection,2 closed;3/4 paused1/2.
%define KB_ABSENT           0x009F ; Controller works; keyboard reset did not reply.

%define CMD_READ            0x20
%define CMD_WRITE           0x30
%define CMD_VERIFY          0x40
%define CMD_FORMAT          0x50
%define CMD_SEEK            0x70
%define CMD_READ_LONG       0x22
%define CMD_WRITE_LONG      0x32

%define ERR_BAD_COMMAND     0x01
%define ERR_BAD_ADDRESS     0x04
%define ERR_CONTROLLER      0x20
%define ERR_TIMEOUT         0x80

; Wide counts are optional until a port adopts wide RAM publication.
%ifndef BOARD_POST_RAM_ROW
%define BOARD_POST_RAM_ROW 5
%endif
%ifdef BOARD_WIDE_MEMORY_COUNTS
%define MEMORY_COUNT_DIGITS 6
%else
%define MEMORY_COUNT_DIGITS 5
%endif
%define S_INSTALLED_KIB32 0x00D8
%define S_EXTENDED_KIB32 0x00DC
%macro memory_extended_kib 1
%ifdef BOARD_WIDE_MEMORY_COUNTS
    mov %1,[fs:S_EXTENDED_KIB32]
%else
    movzx %1,word [fs:S_EXTENDED_KIB]
%endif
%endmacro
%macro memory_installed_kib 1
%ifdef BOARD_WIDE_MEMORY_COUNTS
    mov %1,[fs:S_INSTALLED_KIB32]
%else
    movzx %1,word [fs:S_INSTALLED_KIB]
%endif
%endmacro
