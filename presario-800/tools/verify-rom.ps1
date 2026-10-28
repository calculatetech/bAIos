param(
    [string]$BuildDirectory = "build",
    [switch]$Vga141,
    [switch]$VgaBus07,
    [ValidateSet(50, 60)][int]$VgaClockMHz = 60,
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$release = $PSBoundParameters.ContainsKey('VgaClockMHz') -or (-not $Vga141 -and -not $VgaBus07)
if ($release) { $VgaBus07 = $true; $Vga141 = $true }
if ($VgaBus07 -and -not $release) {
    $Vga141 = $true
    if ($BuildDirectory -eq 'build') { $BuildDirectory = 'build/review/ram-presets' }
}
if ($Vga141 -and -not $release -and $BuildDirectory -eq 'build') { $BuildDirectory = 'build/review/vga141' }

$root = Split-Path -Parent $PSScriptRoot
$buildRoot = [IO.Path]::GetFullPath((Join-Path $root "build"))
$candidate = if ([IO.Path]::IsPathRooted($BuildDirectory)) { $BuildDirectory } else { Join-Path $root $BuildDirectory }
$out = [IO.Path]::GetFullPath($candidate)
$buildPrefix = $buildRoot.TrimEnd('\') + '\'
if ($out -ne $buildRoot -and -not $out.StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "BuildDirectory must resolve inside $buildRoot."
}
$reference = [IO.File]::ReadAllBytes((Join-Path $root "reference/COMPAQ_PROLINEA_MT_05-02-94.BIN"))
$system = [IO.File]::ReadAllBytes((Join-Path $out "baios-presario800-system.rom"))
$physicalName = if ($release) { "baios-presario800-vga$VgaClockMHz.bin" } elseif ($VgaBus07) { 'baios-presario800-vga141-bus07.bin' } else { 'baios-presario800-vga141.bin' }
$physical = [IO.File]::ReadAllBytes((Join-Path $out $physicalName))
$roms = Join-Path $out 'tests/86box/roms'
$genericRoms = $roms
if ($release) { $roms = Join-Path $out "tests/86box/vga$VgaClockMHz/roms" }
$wrapper = [IO.File]::ReadAllBytes((Join-Path $roms "machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin"))
$expectedRetainedHash = "BC30502F33C1EA19D29134B23BBBB04B3494F055B479DA954B367243A13CA030"

function Get-Sha256Hex([byte[]]$bytes) {
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha256.ComputeHash($bytes)).Replace('-', '') }
    finally { $sha256.Dispose() }
}

function Assert-RetainedReference([byte[]]$bytes) {
    if ($bytes.Length -lt 65536) { throw "Retained reference is too small." }
    $retained = [byte[]]::new(65536)
    [Array]::Copy($bytes, $retained, 65536)
    if ((Get-Sha256Hex $retained) -ne $expectedRetainedHash) { throw "Retained reference hash failed." }
}

function Assert-ResetVector([byte[]]$bytes) {
    $expected = [byte[]](0xEA, 0x00, 0x00, 0x00, 0xF0)
    for ($i = 0; $i -lt $expected.Length; $i++) {
        if ($bytes[0xFFF0 + $i] -ne $expected[$i]) { throw "Reset vector target failed." }
    }
}

function Assert-SystemChecksum([byte[]]$bytes) {
    $sum = 0
    foreach ($value in $bytes) { $sum = ($sum + $value) -band 0xFF }
    if ($sum -ne 0) { throw "System ROM checksum failed." }
}

function Assert-RomSize([byte[]]$bytes, [int]$required, [string]$name) {
    if ($bytes.Length -ne $required) { throw "$name ROM size failed." }
}

function Expect-Failure([scriptblock]$action, [string]$name) {
    $failed = $false
    try { & $action } catch { $failed = $true }
    if (-not $failed) { throw "Verifier self-test accepted $name." }
}

function Assert-PostLegend([string]$readme) {
    $expected = @('10', '20', '11', '30', '21', '22', '23', '24', '25', '26', '27', '28', '29', '2A', '2B', '2C', '2D', '2E', '18', '19', '1A', '1B', '1C', '1D', '1E', '12', '13', '14', '15', '16', '40', '48', '50', '60', '70', '80', '90', '91', '94', 'A1', 'A2', 'A4', 'A5', 'A6', 'A7', 'A8', 'AF', 'B0', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', 'BA', 'C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9', 'CA', 'D0', 'D1', 'D2', 'D3', 'D4', 'E0', 'E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7', 'E8', 'E9', 'EA', 'EB', 'EE', 'EF', 'FF')
    $actual = @([regex]::Matches($readme, '(?m)^\| `([0-9A-F]{2})h` \|') | ForEach-Object {
        $_.Groups[1].Value.ToUpperInvariant()
    })
    if ($actual.Count -ne $expected.Count -or (Compare-Object $expected $actual -SyncWindow 0)) {
        throw "README POST code inventory or order changed."
    }
}

function Assert-SystemShadow([string]$biosSource) {
    $shadow = [regex]::Match($biosSource, '(?s)shadow_system_bios:(.*?)validate_vga_image:').Groups[1].Value
    if ($biosSource -notmatch 'call shadow_system_bios\s+; Relocate the embedded lower ROM' -or
        $shadow -notmatch '(?s)mov ax, 0xF000\s+mov ds, ax.*?mov ax, 0x1000\s+mov es, ax.*?mov cx, 0x8000\s+rep movsw\s+jmp 0x1000:\.staged.*?mov al, SYSTEM_SHADOW_REG\s+out CHIPSET_INDEX, al\s+mov al, 0xFF\s+out CHIPSET_DATA, al\s+wbinvd.*?mov ax, 0x1000\s+mov ds, ax.*?mov ax, 0xF000\s+mov es, ax.*?mov cx, 0x8000\s+rep movsw.*?mov cx, 0x8000\s+repe cmpsw\s+jne \.failed.*?mov al, SYSTEM_SHADOW_REG\s+out CHIPSET_INDEX, al\s+mov al, 0xAA\s+out CHIPSET_DATA, al\s+wbinvd\s+jmp 0xF000:\.shadowed.*?\.failed:\s+post_code_early 0xE0') {
        throw "OEM system shadow copy, comparison, or protection changed."
    }
    if ($biosSource -notmatch '(?s)\.reset_classified:.*?mov dx, 0x03BA\s+in al, dx\s+mov dx, 0x03DA\s+in al, dx\s+mov dx, 0x03C0\s+xor al, al\s+out dx, al.*?post_code_early 0x30') {
        throw "OEM early video blanking changed."
    }
}

function Assert-NoTemporaryDiagnostics([string]$biosSource) {
    if ($biosSource -match 'KB_DEBUG_SCAN|\.bat_hex:|post_code 0x(?:29|2A|2B|2C|3[1-8]|CB|CC|CD|CF)\b') {
        throw "Temporary keyboard or shadow diagnostics remain."
    }
}

function Assert-NoFinalDrqGate([string]$biosSource) {
    $completion = [regex]::Match($biosSource, '(?s)ata_wait_complete:(.*?)ata_wait_drq:').Groups[1].Value
    if ($biosSource -match '(?m)^ata_wait_data_in_complete:' -or $completion -match 'test al, 0x08') {
        throw "ATA completion must not wait for DRQ to clear."
    }
}

function Assert-Keyboard([string]$boardSource, [string]$biosSource, [string]$guestSource) {
    if ($boardSource -notmatch '(?m)^%define KBC_DATA\s+0x0060\s*$' -or
        $boardSource -notmatch '(?m)^%define KBC_STATUS\s+0x0064\s*$' -or
        $boardSource -notmatch '(?m)^%define KBC_COMMAND\s+0x0064\s*$') {
        throw "Keyboard-controller ports changed."
    }
    if ($biosSource -notmatch '(?s)set_vector 0x08, int08\s+set_vector 0x02, chipset_nmi\s+set_vector 0x09, int09.*?set_vector 0x15, int15\s+set_vector 0x16, int16' -or
        $biosSource -notmatch '(?s)mov word \[0x041A\], KB_BUFFER_START\s+mov word \[0x041C\], KB_BUFFER_START') {
        throw "Keyboard vectors or BDA ring initialization changed."
    }

    $prerequisites = [regex]::Match($biosSource, '(?s)init_at_prerequisites:(.*?)init_superio:').Groups[1].Value
    if ($boardSource -notmatch '(?m)^%define KBC_PLATFORM_REG\s+0x1D\b' -or
        $boardSource -notmatch '(?m)^%define KBC_PLATFORM_VALUE\s+0xC5\b' -or
        $prerequisites -notmatch '(?s)out CHIPSET_CONFIG_ON, al.*?mov al, CLKCTL_REG\s+out CHIPSET_INDEX, al\s+mov al, CLKCTL_VALUE\s+out CHIPSET_DATA, al\s+mov al, DMACTL_REG\s+out CHIPSET_INDEX, al\s+mov al, DMACTL_VALUE\s+out CHIPSET_DATA, al\s+mov al, BUSCTL_REG\s+out CHIPSET_INDEX, al\s+mov al, BUSCTL_VALUE\s+out CHIPSET_DATA, al\s+mov al, KBC_PLATFORM_REG\s+out CHIPSET_INDEX, al\s+mov al, KBC_PLATFORM_VALUE\s+out CHIPSET_DATA, al\s+out CHIPSET_CONFIG_OFF, al.*?post_code 0xB0') {
        throw "OEM VL82C114 PS/2 mode prerequisite is missing."
    }
    if ($prerequisites -notmatch '(?s)post_code 0xB0\s+xor al, al\s+out DMA1_MASTER_CLEAR, al\s+out DMA2_MASTER_CLEAR, al\s+post_code 0xB1\s+mov dx, FDC_DOR\s+out dx, al\s+mov al, 0x0C\s+out SYSTEM_PORT_B, al\s+mov al, 0x54\s+out PIT_COMMAND, al\s+mov al, 0x12\s+out PIT_CHANNEL1, al\s+post_code 0xB9\s+ret') {
        throw "Reference-derived AT prerequisites changed."
    }

    $init = [regex]::Match($biosSource, '(?s)init_keyboard:(.*?)keyboard_halt:').Groups[1].Value
    if ($init -notmatch '(?s)^\s+;[^\n]*\n\s+cli\s' -or
        $init -match 'mov al, 0x7[CD]' -or
        $guestSource -notmatch '(?s)test dl, 0x20\s+mov al, 0x27\s+jnz fail') {
        throw "Keyboard polling must own responses and use AT, not XT, protocol."
    }
    if ($init -match '(?m)^\s*(?:mov al, 0xF5|mov al, 0xF4|mov al, 0xED|keyboard_write_ack:)' -or
        $biosSource -notmatch '(?s)kbc_wait_input_clear_mr:\s+push cx\s+xor cx, cx\s+\.wait:\s+in al, KBC_STATUS\s+test al, 0x02\s+loopne \.wait\s+jnz \.timeout\s+clc\s+pop cx\s+ret\s+\.timeout:\s+stc\s+pop cx\s+ret' -or
        $init -notmatch '(?s)post_code 0xB4\s+mov cx, 1000\s+\.power_on_settle:\s+in al, KBC_DATA\s+call kbc_delay_2ms\s+loop \.power_on_settle\s+mov al, 0xAD\s+call kbc_command\s+jc \.pre_b4_failed\s+call kbc_wait_input_clear\s+jc \.pre_b4_failed\s+post_code 0xB5\s+mov al, 0xA7\s+call kbc_command\s+jc \.pre_b5_failed\s+call kbc_wait_input_clear\s+jc \.pre_b5_failed\s+post_code 0xB6\s+call kbc_drain\s+jc \.pre_b6_failed\s+post_code 0xC0' -or
        $init -notmatch '(?s)post_code 0xC0.*?mov al, 0xAD\s+call kbc_command\s+jc \.input_failed\s+call kbc_drain.*?post_code 0xC1.*?mov al, 0xAA\s+call kbc_command.*?cmp al, 0x55.*?post_code 0xC2\s+.*?post_code 0xB7\s+mov al, 0xD1\s+out KBC_COMMAND, al\s+call kbc_wait_input_clear_mr\s+jc \.pre_b7_failed\s+post_code 0xB8\s+mov al, 0xCF\s+out KBC_DATA, al\s+call kbc_wait_input_clear_mr\s+jc \.pre_b8_failed\s+post_code 0xBA\s+mov al, 0x60\s+call kbc_command.*?mov al, 0x5C\s+call kbc_write_data.*?call kbc_wait_input_clear.*?post_code 0xC3.*?mov al, 0xAE\s+call kbc_command.*?mov cx, 10\s+\.settle_keyboard:\s+call kbc_read_data\s+loop \.settle_keyboard\s+post_code 0xC4.*?mov bl, 2\s+\.reset_keyboard:\s+post_code 0xC5\s+mov al, 0xFF\s+call kbc_write_data\s+jc \.reset_write_failed\s+mov cx, 12\s+\.wait_reset_ack:.*?cmp al, 0xFA\s+je \.wait_bat\s+cmp al, 0xFE\s+je \.reset_resend.*?\.wait_bat:\s+post_code 0xC6\s+mov cx, 50\s+\.wait_bat_response:.*?post_code 0xC8\s+dec bl\s+jnz \.reset_keyboard\s+mov al, 0xD2\s+jmp keyboard_halt\s+\.bat_reply:\s+cmp al, 0xAA\s+jne \.bat_failed\s+post_code 0xC7\s+mov al, 0xAE\s+call kbc_command.*?post_code 0xC9\s+ret') {
        throw "OEM keyboard initialization order changed."
    }
    foreach ($code in @('B4', 'B5', 'B6', 'B7', 'B8', 'BA', 'C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9', 'D0', 'D1', 'D2', 'D3', 'D4', 'E7', 'E8', 'E9', 'EA', 'EB')) {
        if ($init -notmatch "(?:post_code|mov (?:al|bh),) 0x$code") { throw "Keyboard initialization POST code $code is missing." }
    }

    $irq = [regex]::Match($biosSource, '(?s)int09:(.*?)keyboard_enqueue:').Groups[1].Value
    if ($irq -notmatch '(?s)in al, KBC_STATUS.*?and al, 0x21\s+cmp al, 0x21\s+je \.eoi.*?mov al, 0xAD\s+call kbc_command.*?in al, KBC_DATA' -or
        $irq -notmatch '(?s)cmp bl, 0xE1.*?mov byte \[KB_E1_REMAIN\], 5.*?cmp bl, 0xE0.*?or byte \[KB_EXT_FLAGS\], 0x02' -or
        $irq -notmatch '(?s)\.left_shift:.*?test dl, 0x80\s+jnz \.left_shift_up.*?\.left_shift_up:\s+and byte \[KB_FLAGS\], 0xFD' -or
        $irq -notmatch '(?s)\.combine_control:.*?test byte \[KB_FLAGS2\], 1.*?test byte \[KB_EXT_FLAGS\], 4.*?\.combine_alt:.*?test byte \[KB_FLAGS2\], 2.*?test byte \[KB_EXT_FLAGS\], 8' -or
        $irq -notmatch '(?s)\.alt_text:.*?test byte \[KB_FLAGS\], 0x08\s+jz \.text_ready\s+xor al, al\s+mov ah, bl\s+cmp bl, 2\s+jb \.alt_queue\s+cmp bl, 0x0D\s+ja \.alt_queue\s+add ah, 0x76[^\n]*\n\.alt_queue:\s+call keyboard_enqueue' -or
        $irq -notmatch '(?s)cmp bl, 0x53\s+jne \.queue_extended\s+mov al, \[KB_FLAGS\]\s+and al, 0x0C\s+cmp al, 0x0C\s+je warm_reset' -or
        $irq -notmatch '(?s)\.reenable:\s+mov al, 0xAE\s+call kbc_command\s+jc \.controller_failed\s+\.eoi:\s+mov al, 0x61[^\n]*\n\s+out 0x20, al') {
        throw "IRQ1 decoding, modifier, reset, re-enable, or EOI behavior changed."
    }
    if ($irq -match 'cmp bl, 0xAA') { throw "Runtime AAh must remain left-Shift break, not a BAT filter." }
    if ($biosSource -notmatch '(?s)call init_keyboard\s+post_code 0x48\s+call arm_keyboard_runtime\s+jc keyboard_runtime_failed\s+mov byte \[0x0400 \+ KB_POST_STATE\], 1\s+sti' -or
        ([regex]::Matches($biosSource, '(?m)^\s*call arm_keyboard_runtime\s*$')).Count -ne 1 -or
        $biosSource -notmatch '(?s)call init_mouse\s+(?:%ifdef EMULATOR_PORTS_TEST\s+call ports_test_observe\s+%endif\s+)?in al, 0x21\s+and al, 0xF9\s+out 0x21, al\s+cli\s+call init_fpu\s+(?:;[^\n]*\n\s*)*post_code 0xCA.*?call post_keyboard_wait.*?call setup_post_gate\s+call chipset_late_cache\s+call post_success_tone\s+mov byte \[fs:P_PHASE\], 5\s+call post_ui_cache\s+call post_ui_roms\s+call option_rom_discovery\s+(?:%ifdef EMULATOR_CHIPSET_POST_UI\s+call post_ui_capture\s+%endif\s+)?call post_debug_summary\s+call presario_post_complete\s+(?:%ifdef EMULATOR_SETUP_TEST\s+call setup_test_end\s+%endif\s+)?(?:%ifdef EMULATOR_BOOT_POLICY_TEST\s+call boot_policy_ready\s+%endif\s+)?mov byte \[0x0400 \+ KB_POST_STATE\], 0\s+sti\s+int 0x19' -or
        $biosSource -notmatch '(?s)init_pic_pit:\s+mov al, 0x11\s+out 0x20, al\s+out 0x84, al\s+out 0xA0, al\s+out 0x84, al.*?mov al, 0xFC\s+out 0x21, al\s+out 0x84, al\s+mov al, 0xFF\s+out 0xA1, al\s+out 0x84, al' -or
        $biosSource -notmatch '(?s)arm_keyboard_runtime:.*?mov al, 0x20\s+call kbc_command.*?call kbc_read_data.*?or al, 0x41\s+and al, 0xCF.*?mov al, 0x60\s+call kbc_command.*?call kbc_write_data.*?mov al, 0xAE\s+call kbc_command' -or
        $biosSource -notmatch '(?s)keyboard_runtime_failed:\s+mov al, 0xEF\s+jmp keyboard_halt' -or
        $biosSource -notmatch '(?s)int16:.*?\.read_wait:\s+call keyboard_poll.*?\.status:\s+add sp, 2\s+cli\s+(?:;[^\n]*\n\s*)*or word \[ss:bp \+ 6\], 0x0240\s+and word \[ss:bp \+ 6\], 0xFFFE\s+call keyboard_poll.*?\.available:.*?and word \[ss:bp \+ 6\], 0xFFBF\s+or word \[ss:bp \+ 6\], 1.*?keyboard_poll:\s+in al, KBC_STATUS\s+(?:;[^\n]*\n\s*)*and al, 0x21\s+cmp al, 0x01\s+jne \.done.*?mov al, 0x0A\s+out 0x20, al\s+in al, 0x20\s+test al, 2\s+jnz \.done\s+mov al, 0x0B\s+out 0x20, al\s+in al, 0x20\s+test al, 2\s+mov al, 0x0A[^\n]*\n\s+out 0x20, al\s+jnz \.done\s+int 0x09') {
        throw "Keyboard IRQ arming or INT 16h polling fallback changed."
    }
    if ($biosSource -notmatch '(?s)int08:.*?mov al, 0x60[^\n]*\n\s+out 0x20, al.*?call keyboard_poll') {
        throw "IRQ0 keyboard polling fallback changed."
    }

    $queue = [regex]::Match($biosSource, '(?s)keyboard_enqueue:(.*?)warm_reset:').Groups[1].Value
    if ($queue -notmatch '(?s)mov bx, \[KB_TAIL\].*?add dx, 2\s+cmp dx, KB_BUFFER_END\s+jb \.not_wrapped\s+mov dx, KB_BUFFER_START.*?cmp dx, \[KB_HEAD\]\s+je \.full\s+mov \[bx\], ax\s+mov \[KB_TAIL\], dx') {
        throw "Keyboard FIFO wrap or full-drop behavior changed."
    }

    $service = [regex]::Match($biosSource, '(?s)int16:(.*?)keyboard_normal:').Groups[1].Value
    if ($service -notmatch '(?s)cmp bl, 0x00\s+je \.read\s+cmp bl, 0x10\s+je \.read\s+cmp bl, 0x01\s+je \.status\s+cmp bl, 0x11\s+je \.status\s+cmp bl, 0x02\s+je \.shift_status' -or
        $service -notmatch '(?s)\.read_wait:.*?sti\s+hlt\s+cli\s+jmp \.read_wait' -or
        $service -notmatch '(?s)\.status:.*?or word \[ss:bp \+ 6\], 0x0240\s+and word \[ss:bp \+ 6\], 0xFFFE.*?\.available:.*?and word \[ss:bp \+ 6\], 0xFFBF\s+or word \[ss:bp \+ 6\], 1' -or
        $service -notmatch '(?s)\.shift_status:\s+add sp, 2\s+mov al, \[KB_FLAGS\]\s+xor ah, ah') {
        throw "INT 16h read, status, alias, or returned-ZF behavior changed."
    }
    $statusService = [regex]::Match($service, '(?s)\.status:(.*?)\.shift_status:').Groups[1].Value
    if ($statusService -match 'mov \[KB_HEAD\]') { throw "INT 16h status must not consume a key." }

    $reset = [regex]::Match($biosSource, '(?s)warm_reset:(.*?)int16:').Groups[1].Value
    if ($reset -notmatch '(?s)mov al, 0xAD\s+call kbc_command\s+jc \.failed\s+call kbc_wait_input_clear_mr\s+jc \.failed\s+call kbc_drain\s+jc \.failed\s+mov word \[KB_HEAD\], KB_BUFFER_START\s+mov word \[KB_TAIL\], KB_BUFFER_START.*?mov al, 0xAE') {
        throw "Warm reset must discard controller data and the BIOS key queue before releasing the keyboard."
    }
    if ($reset -notmatch '(?s)cli\s+in al, 0x61\s+and al, 0xFC\s+out 0x61, al[^\n]*\n\s+mov word \[0x0072\], 0x1234\s+post_code 0x90.*?mov al, 0xAE\s+call kbc_command.*?call kbc_wait_input_clear_mr.*?out CHIPSET_CONFIG_ON, al\s+mov al, SYSTEM_SHADOW_REG\s+out CHIPSET_INDEX, al\s+xor al, al\s+out CHIPSET_DATA, al\s+mov al, VGA_SHADOW_REG\s+out CHIPSET_INDEX, al\s+xor al, al\s+out CHIPSET_DATA, al\s+wbinvd\s+out CHIPSET_CONFIG_OFF, al\s+post_code 0x91\s+jmp 0xF000:startup\.warm_start' -or
        $reset -notmatch '(?s)\.failed:\s+mov al, 0xEE\s+jmp keyboard_halt' -or
        $reset -match '(?i)int\s+0x19|mov al, 0xFE') {
        throw "OEM warm re-entry, shadow invalidation, or keyboard release changed."
    }

    if ($biosSource -notmatch '(?s)\.normal_reset:.*?xor bp, bp\s+test bh, 0x04\s+jz \.cold_classified\s+cmp word \[0x0472\], 0x1234\s+jne \.cold_classified\s+inc bp\s+\.cold_classified:.*?mov al, RAMSET_REG' -or
        $biosSource -notmatch '(?s)\.classify_reset:.*?cmp si, 1\s+jne \.warm_marker_captured\s+xor bp, bp\s+in al, KBC_STATUS\s+test al, 0x04\s+jz \.warm_marker_captured\s+cmp word \[0x0472\], 0x1234\s+jne \.warm_marker_captured\s+inc bp\s+\.warm_marker_captured:\s+test bp, bp\s+jz \.reset_classified\s+post_code_early 0x11' -or
        $biosSource -notmatch '(?s)mov byte \[es:0\], 1\s+mov \[es:S_EXTENDED_KIB\], dx\s+mov \[es:S_INSTALLED_KIB\], dx\s+mov eax, ebp\s+shr eax, 16\s+mov \[es:S_CPU_SIGNATURE\], ax\s+mov ax, bp\s+mov \[es:S_WARM_BOOT\], al') {
        throw "Warm classification is not the required pre-clear AND predicate."
    }

    if ($guestSource -notmatch '(?s)mov al, 0xD2\s+out dx, al.*?out KBC_DATA, al' -or
        $guestSource -notmatch '(?s)or al, 0x03\s+out 0x21, al\s+mov al, 0xD2\s+call guest_command\s+mov al, 0x30\s+call guest_data\s+call wait_controller_output\s+mov ah, 0x01\s+int 0x16.*?cmp ax, 0x3062.*?mov ah, 0x00\s+int 0x16\s+cmp ax, 0x3062' -or
        $guestSource -notmatch '(?s)mov al, 0x2E\s+call guest_data\s+mov cx, 4\s+\.timer_poll_wait:\s+sti\s+hlt.*?cmp bx, \[0x041C\]\s+jne \.timer_poll_ready.*?\.timer_poll_ready:\s+mov ah, 0x00\s+int 0x16\s+cmp ax, 0x2E63' -or
        $guestSource -match '(?i)call\s+int09|call\s+keyboard_enqueue' -or
        $guestSource -notmatch '(?s)phase1:.*?xor bx, bx\s+call raw_reset.*?phase2:.*?mov bx, 0x0100\s+call raw_reset.*?phase3:.*?mov bx, 0x0001\s+call raw_reset.*?phase4:.*?mov bx, 0x0101\s+call raw_reset' -or
        $guestSource -notmatch '(?s)lidt \[cs:idtr_07ff\].*?jmp 0xF000:0x0000' -or
        $guestSource -notmatch '(?s)cmp ax, 0x07FF.*?cmp ax, 0x03FF') {
        throw "Keyboard guest no longer proves real IRQ1 delivery or reset discrimination."
    }
}

function Assert-PostTrace([string]$boardSource, [string]$biosSource) {
    if ($boardSource -notmatch '(?m)^%define POST_PORT\s+0x0080\s*$') {
        throw "POST port is not the Presario port 80h."
    }
    if ($biosSource -notmatch '(?s)%macro post_code_early 1\s+mov al, %1\s+out POST_PORT, al\s+%endmacro') {
        throw "Early POST output is not inline and stack-free."
    }
    if ($biosSource -notmatch '(?s)%macro post_code 1\s+push ax\s+post_code_early %1\s+pop ax\s+%endmacro') {
        throw "Later POST output does not preserve AX."
    }
    if ($biosSource -match '(?m)^\s*mov dx,\s*0x008[04]\s*$') {
        throw "BIOS POST output bypasses the board-owned port."
    }

    $startupMatch = [regex]::Match($biosSource, '(?s)startup:(.*?)\.ram_failed:')
    if (-not $startupMatch.Success) { throw "Startup POST path was not found." }
    $startupPath = $startupMatch.Groups[1].Value
    $actual = @([regex]::Matches($startupPath, '(?m)^\s*(post_code(?:_early)?)\s+(0x[0-9A-Fa-f]+)\s*$') | ForEach-Object {
        "$($_.Groups[1].Value) $($_.Groups[2].Value.ToUpperInvariant())"
    })
    $expected = @(
        'post_code_early 0X10',
        'post_code_early 0X20', 'post_code_early 0X94',
        'post_code_early 0X11',
        'post_code_early 0X30',
        'post_code 0X40',
        'post_code 0X50',
        'post_code 0X60',
        'post_code 0X48',
        'post_code 0X70',
        'post_code 0X80',
        'post_code 0XCA'
    )
    if ($actual.Count -ne $expected.Count -or (Compare-Object $expected $actual -SyncWindow 0)) {
        throw "Startup POST code inventory or order changed."
    }

    $anchors = @(
        '(?s)startup:\s+cli\s+post_code_early 0x10\s+cld\s+jmp 0xF000:\.normalized',
        '(?s)out CHIPSET_CONFIG_ON, al.*?mov al, ROMSET_VALUE\s+out dx, al\s+out CHIPSET_CONFIG_OFF, al\s+post_code_early 0x20\s+; Test RAM',
        '(?s)loop \.ram_check_a\s+xor si, si[^\r\n]*\s+jmp \.classify_reset.*?\.classify_reset:.*?wbinvd\s+mov eax, cr0\s+or eax, 0x60000000\s+mov cr0, eax\s+wbinvd.*?and al, ~PRIMARY_CACHE_EN.*?cmp si, 1\s+jne \.warm_marker_captured.*?in al, KBC_STATUS\s+test al, 0x04.*?cmp word \[0x0472\], 0x1234.*?\.warm_marker_captured:\s+test bp, bp\s+jz \.reset_classified\s+post_code_early 0x11\s+\.reset_classified:.*?post_code_early 0x30\s+mov di, 0x0600\s+mov cx, 128\s+xor ax, ax\s+rep stosw\s+mov ss, ax',
        '(?s)\.normal_reset:.*?cmp word \[0x0472\], 0x1234.*?mov al, RAMSET_REG.*?mov al, RAMSET_VALUE.*?mov al, RAMCFG0_REG',
        '(?s)call init_memory.*?mov dx, \[es:S_EXTENDED_KIB\].*?call memory_interleave_options.*?mov al, RAMSET_REG\s+out CHIPSET_INDEX, al\s+mov al, cl\s+out CHIPSET_DATA, al\s+out CHIPSET_CONFIG_OFF, al.*?\.memory_map_ready:.*?rep stosw.*?mov \[es:S_EXTENDED_KIB\], dx.*?call shadow_system_bios',
        '(?s)pop es\s+pop ds\s+post_code 0x40\s+; Start with harmless handlers',
        '(?s)call init_pic_pit\s+call init_rtc\s+call init_superio\s+call init_at_prerequisites\s+post_code 0x50\s+; This retained component owns the Cirrus video initialization and INT 10h\.\s+call VGA_SEGMENT:VGA_ENTRY',
        '(?s)call VGA_SEGMENT:VGA_ENTRY.*?cmp word \[es:0x0042\], VGA_SEGMENT\s+jne video_failed\s+post_code 0x60\s+mov ax, 0x0003\s+int 0x10\s+%ifdef VGA_BIOS_141\s+(?:;[^\n]*\n\s*)*pushad\s+push ds\s+push es\s+mov ax, 0x1203\s+mov bx, 0x10A4\s+xor cx, cx\s+xor dx, dx\s+int 0x10\s+pop es\s+pop ds\s+popad\s+%endif\s+; Video is available for failure diagnostics, not a keyboard prerequisite\.\s+call init_keyboard\s+post_code 0x48.*?call arm_keyboard_runtime.*?sti\s+;[^\n]*\n\s+call load_bios_state\s+mov byte \[fs:P_PHASE\], 0\s+mov byte \[fs:P_ROM_COUNT\], 0[^\n]*\n\s+call post_ui_begin',
        '(?s)\.initialization_verified:\s+%endif\s+%endif\s+call init_floppy\s+mov byte \[fs:P_PHASE\], 3\s+call post_ui_floppy\s+call post_early_setup\s+call post_floppy_seek\s+call post_early_setup\s+%ifdef FLOPPY_DIAGNOSTIC\s+call floppy_diagnostics\s+%endif.*?call post_keyboard_wait.*?post_code 0x70\s+call ata_detect_primary',
        '(?s)call ata_detect_primary\s+call post_keyboard_wait\s+mov byte \[fs:P_PHASE\], 4\s+call post_ui_disks\s+call post_early_setup\s+cmp byte \[0x0475\], 0\s+je \.common_post\s+post_code 0x80',
        '(?s)\.common_post:.*?call init_mouse.*?call init_fpu.*?call setup_post_gate\s+call chipset_late_cache\s+call post_success_tone\s+mov byte \[fs:P_PHASE\], 5\s+call post_ui_cache\s+call post_ui_roms\s+call option_rom_discovery\s+(?:%ifdef EMULATOR_CHIPSET_POST_UI\s+call post_ui_capture\s+%endif\s+)?call post_debug_summary\s+call presario_post_complete.*?int 0x19'
    )
    if ($biosSource -notmatch '(?s)presario_post_complete:\s+post_code 0xFF\s+jmp rtc_sync_ticks') {
        throw "POST completion must emit FFh once before the RTC handoff."
    }
    foreach ($anchor in $anchors) {
        if ($biosSource -notmatch $anchor) { throw "A POST code moved away from its startup stage." }
    }

    $beforeRamPass = [regex]::Match($startupPath, '(?s)^(.*?)loop \.ram_check_a').Groups[1].Value
    if ($beforeRamPass -match '(?m)^\s*(call|push)\b') {
        throw "Pre-RAM POST output added a call or push."
    }
    if ($beforeRamPass -notmatch '(?s)in al, KBC_STATUS\s+mov bh, al.*?mov bl, al\s+xor al, al\s+out 0x71, al\s+test bh, 0x04\s+jz \.normal_reset\s+cmp bl, 0x05\s+je \.resume_eoi\s+cmp bl, 0x0A\s+jne \.normal_reset.*?\.resume_eoi:\s+mov al, 0x20\s+out 0x20, al\s+\.resume:\s+(?:;[^\n]*\n\s*)*mov eax, cr0\s+and eax, 0x9FFFFFFF\s+mov cr0, eax\s+mov ax, 0x0040\s+mov ds, ax\s+jmp far \[0x0067\]') {
        throw "CPU-reset shutdown continuation changed."
    }
    if (($beforeRamPass -replace 'jmp far \[0x0067\]|cmp word \[0x0472\], 0x1234', '') -match '\[') {
        throw "Pre-RAM POST output added retained memory state."
    }

    $terminalPatterns = @(
        '(?s)\.ram_failed:\s+mov dx, POST_PORT\s+mov al, 0xE1\s+out dx, al\s+jmp hard_halt',
        '(?s)video_failed:\s+mov dx, POST_PORT\s+mov al, 0xE2\s+out dx, al\s+jmp hard_halt',
        '(?s)\.vga_mapping_failed:\s+pop es\s+pop ds\s+mov dx, POST_PORT\s+mov al, 0xE5\s+out dx, al\s+jmp hard_halt',
        '(?s)\.vga_shadow_failed:\s+pop es\s+pop ds\s+mov dx, POST_PORT\s+mov al, 0xE6\s+out dx, al\s+jmp hard_halt',
        '(?s)no_disk:.*?mov dx, POST_PORT\s+mov al, 0xE3\s+out dx, al.*?jmp halt_forever',
        '(?s)boot_retry:\s+boot_context\s+mov byte \[0x0400\+KB_POST_STATE\], 2.*?\.flush:\s+sti[^\r\n]*\s+nop\s+cli\s+call keyboard_poll.*?mov \[0x041A\], ax\s+mov si, msg_boot_unavailable\s+call print_string\s+mov si, msg_boot_retry\s+call print_string\s+post_code 0xE4\s+%ifdef EMULATOR_BOOT_RETRY_EXIT\s+%ifdef BOARD_BOOT_RETRY_TEST_SOURCE\s+call core_boot_retry_observe\s+%else\s+mov al, EMULATOR_BOOT_RETRY_EXIT\s+call emulator_exit[^\r\n]*\s+%endif\s+%endif\s+\.wait:.*?sti\s+hlt\s+cli\s+jmp \.wait\s+\.key:.*?int 0x16.*?boot_context.*?sti\s+int 0x19[^\r\n]*\s+jmp boot_retry'
    )
    foreach ($terminal in $terminalPatterns) {
        if ($biosSource -notmatch $terminal) { throw "A terminal POST code or halt owner changed." }
    }
}

Assert-RomSize $system 65536 'System'
Assert-RomSize $physical 131072 'Physical'
Assert-RomSize $wrapper 131072 '86Box'
Assert-RetainedReference $reference
if ($Vga141) {
    $vga = [IO.File]::ReadAllBytes((Join-Path $root 'reference/gd5428_1-41.bin'))
    if ($vga.Length -ne 32768 -or (Get-Sha256Hex $vga) -ne '72873E0BB9EFDA71D0B5819CE7B4201D8771C75473CD1170DCC6D2DFB794E0B6') {
        throw 'VGA 1.41 input identity changed.'
    }
    [Array]::Copy($vga, 0, $reference, 0, 32768)
}
if ($VgaBus07) {
    $bus07 = [IO.File]::ReadAllBytes((Join-Path $root 'reference/baios-presario800-vga141-bus07.bin'))
    if ($bus07.Length -ne 131072 -or (Get-Sha256Hex $bus07) -ne '98716A7CEFC742047806C70A8CBEA04A89648C5BF84859FA1CEA269D791633B7') {
        throw 'The frozen bus07 input identity or layout changed.'
    }
    [Array]::Copy($bus07, 0, $reference, 0, 32768)
}
Assert-ResetVector $system
if ($release) {
    if ($VgaClockMHz -eq 50) {
        $reference[0x08E7] = 0x1C
        $vgaSum = 0
        for ($i = 0; $i -lt 32767; $i++) { $vgaSum = ($vgaSum + $reference[$i]) -band 255 }
        $reference[32767] = (-$vgaSum) -band 255
    }
    $alias = [IO.File]::ReadAllBytes((Join-Path $out 'baios-presario800.bin'))
    $aliasHash = Get-Sha256Hex $alias
    $matchesVariant = $false
    foreach ($clock in @(50, 60)) {
        $variant = Join-Path $out "baios-presario800-vga$clock.bin"
        if ((Test-Path -LiteralPath $variant) -and
            $aliasHash -eq (Get-Sha256Hex ([IO.File]::ReadAllBytes($variant)))) { $matchesVariant = $true }
    }
    if (-not $matchesVariant) { throw 'The main alias differs from both available VGA releases.' }
    $genericWrapper = [IO.File]::ReadAllBytes((Join-Path $genericRoms 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'))
    if ($aliasHash -ne (Get-Sha256Hex $genericWrapper)) { throw 'The generic 86Box wrapper differs from the main alias.' }
}
for ($i = 0; $i -lt 65536; $i++) {
    if ($physical[$i] -ne $reference[$i]) { throw "Retained region differs at 0x$($i.ToString('X5'))." }
    if ($wrapper[$i] -ne $reference[$i]) { throw "86Box VGA region differs at 0x$($i.ToString('X5'))." }
    if ($physical[$i + 65536] -ne $system[$i]) { throw "System region differs at 0x$($i.ToString('X4'))." }
    if ($wrapper[$i + 65536] -ne $system[$i]) { throw "86Box system region differs at 0x$($i.ToString('X4'))." }
}
$int42 = [byte[]](
    0x80, 0xFC, 0x1D, 0x73, 0x05,
    0xEA, 0xB7, 0x27, 0x00, 0xC0, 0xCF
)
if ($Vga141) { $int42[6] = 0x97; $int42[7] = 0x28 }
for ($i = 0; $i -lt $int42.Length; $i++) {
    if ($system[0xF065 + $i] -ne $int42[$i]) { throw "INT 42h compatibility entry changed." }
}
Assert-SystemChecksum $system

$source = Get-Content -Raw (Join-Path $root "src/boards/presario800.inc")
if ($source -notmatch '(?m)^%define RAMTMG_VALUE\s+0xBF\s+') { throw "Conservative RAM timing default changed." }
if ($source -notmatch '(?m)^%define RAMCFG0_VALUE\s+0x8C\s+') { throw "Bank 0 candidate changed." }
if ($source -notmatch '(?m)^%define RAMCFG1_VALUE\s+0x88\s+') { throw "Banks 2 and 3 are not disabled." }
if ($source -notmatch '(?m)^%define RAMSET_VALUE\s+0x16\s+') { throw "Non-interleaved OEM RAMSET candidate changed." }
if ($source -notmatch '(?m)^%define CHIPSET_CONFIG_OFF\s+0x00F9\s*$') { throw "Chipset configuration-disable port changed." }
if ($source -notmatch '(?m)^%define CHIPSET_CONFIG_ON\s+0x00FB\s*$') { throw "Chipset configuration-enable port changed." }
if ($source -notmatch '(?m)^%define ROMSET_VALUE\s+0x18\s+') { throw "OEM startup ROM setting changed." }
if ($source -notmatch '(?m)^%define VGA_ROMSET_VALUE\s+0x28\s+') { throw "MR BIOS VGA relocation setting changed." }
if ($source -notmatch '(?m)^%define VGA_SHADOW_CLEAR\s+0x0F\s+') { throw "VGA shadow-clear mode changed." }
if ($source -notmatch '(?m)^%define VGA_SHADOW_FILL\s+0x05\s+') { throw "VGA shadow-copy mode changed." }
if ($source -notmatch '(?m)^%define VGA_SHADOW_RUN\s+0x0A\s+') { throw "VGA shadow-run mode changed." }
if ($source -notmatch '(?m)^%define VGA_ROM_WORDS\s+0x4000\s+') { throw "VGA ROM size changed." }

function Assert-MouseExclusion([string]$mouseSource) {
    if ($mouseSource -notmatch '(?m)^mouse_int15:\s+cli\s*(?:;[^\r\n]*)?\r?\n\s+push si') {
        throw "Mouse INT15 entry must clear IF before claiming the controller."
    }
}
$mouse = Get-Content -Raw (Join-Path $root "../shared/src/firmware/mouse.inc")
Assert-MouseExclusion $mouse
$bios = Get-Content -Raw (Join-Path $root "src/bios.asm")
# Expand maintained owners in assembly order for the source invariants.
$bios = $bios.Replace('%include "boot.inc"', (Get-Content -Raw (Join-Path $root "../shared/src/firmware/boot.inc")))
foreach ($include in [regex]::Matches($bios, '(?m)^presario_shared "([^"]+)"')) {
    $bios = $bios.Replace($include.Value, (Get-Content -Raw (Join-Path $root "../shared/src/$($include.Groups[1].Value)")))
}
$bios += "`n" + (Get-Content -Raw (Join-Path $root "src/hardware/adapters.inc"))
$bios = $bios.Replace("`r`n", "`n")
foreach ($constant in @('KBC_OUTPUT_PORT_VALUE', 'KBC_INITIAL_COMMAND_BYTE')) {
    $value = [regex]::Match($source, "(?m)^%define $constant\s+(0x[0-9A-Fa-f]+)\b").Groups[1].Value
    if (-not $value) { throw "Board constant $constant was not found." }
    $bios = $bios.Replace($constant, $value)
}
if ($source -notmatch '(?m)^%define FAST_CPU_PORT\s+0x00F5\s+' -or
    $bios -notmatch '(?s)enable_cpu_full_speed:.*?out CHIPSET_CONFIG_ON, al\s+out FAST_CPU_PORT, al\s+mov al, NTBREF_REG.*?and al, 0x1F') {
    throw "OEM fast-CPU command or non-turbo wait removal changed."
}
$readme = Get-Content -Raw (Join-Path $root "README.md")
$keyboardGuest = Get-Content -Raw (Join-Path $root "tests/keyboard-test.asm")
Assert-PostTrace $source $bios
Assert-PostLegend $readme
Assert-NoFinalDrqGate $bios
Assert-Keyboard $source $bios $keyboardGuest
$geometryPath = [regex]::Match($bios, '(?s)get_chs_geometry:(.*?)ata_reset:').Groups[1].Value
if ($geometryPath -notmatch '(?s)mov ax, 0x3F20.*?0x001F8000.*?mov al, 64.*?0x003F0000.*?mov al, 128.*?0x007E0000.*?mov al, 255.*?mov ds, ax.*?cmp byte \[0x7C00\], 0xEB') {
    throw "LARGE-mode CHS geometry changed."
}
if ($geometryPath -notmatch '(?s)0x7C00.*?0x7C0B\], 512.*?0x7C18\], 63.*?0x7C1A\], 255.*?0x7DFE\], 0xAA55.*?mov ah, \[0x7C18\].*?mov al, \[0x7C1A\].*?pop ds') {
    throw "FAT BPB geometry learning changed."
}
if ($bios -notmatch '(?s)prepare_chs:.*?call get_chs_geometry.*?mov bx, ax.*?cmp al, bh.*?cmp dh, bl.*?movzx edx, bl.*?imul eax, edx.*?movzx edx, bh.*?imul eax, edx') {
    throw "Legacy CHS conversion does not use the selected geometry."
}
if ($bios -notmatch '(?s)ata_identify:.*?rep insw.*?call ata_wait_complete' -or $bios -notmatch '(?s)ata_transfer:.*?call ata_select_ready\s+jc \.error\s+call ide_program_address\s+mov dx, ATA_COUNT.*?mov cx, 256.*?pushf\s+cli\s+rep insw\s+cmp byte \[fs:S_COMMAND\], CMD_READ_LONG\s+jne \.read_data_done\s+mov cx, 4[^\n]*\n\s*rep insb\s+\.read_data_done:\s+popf.*?call ata_wait_complete.*?pushf\s+cli\s+rep outsw\s+cmp byte \[fs:S_COMMAND\], CMD_WRITE_LONG\s+jne \.write_data_done\s+mov cx, 4[^\n]*\n\s*rep outsb\s+\.write_data_done:\s+popf.*?call ata_wait_complete' -or $bios -notmatch '(?s)ata_wait_ready:.*?test al, 0x80.*?test al, 0x40.*?ata_wait_complete:.*?test al, 0x80.*?test al, 0x21') {
    throw "ATA command phasing changed."
}
if ($bios -notmatch '(?s)\.geometry:.*?call get_chs_geometry.*?imul ecx, edx.*?mov cl, ah.*?mov dh, al.*?\.type:' -or $bios -notmatch '(?s)fill_edd_parameters:.*?call get_chs_geometry.*?imul ecx, edx.*?mov \[ds:si \+ 8\], ecx.*?mov \[ds:si \+ 12\], ecx.*?ata_identify:') {
    throw "Reported disk geometry does not use the selected geometry."
}
if ($bios -notmatch '(?m)^%define STATE_END\s+STATE_BASE \+ 29\s*$' -or $bios -match 'S_CHS_HEADS|S_CHS_SPT') {
    throw "CHS geometry must not expand the BIOS-private state boundary."
}
if ($source -notmatch '(?m)^%define STATE_SEG\s+0x9FC0\s*$' -or
    $bios -notmatch '(?s)mov ax, STATE_SEG\s+mov es, ax.*?mov cx, 1024 / 2\s+rep stosw\s+mov byte \[es:0\], 1' -or
    $bios -notmatch '(?s)mov word \[0x040E\], STATE_SEG\s+mov word \[0x0413\], 639' -or
    $bios -notmatch '(?s)int12:.*?mov ax, \[0x13\].*?iret' -or
    $bios -notmatch '(?s)load_bios_state:.*?mov fs, \[fs:0x040E\]' -or
    $bios -notmatch '(?s)check_disk_buffer:.*?mov bx, fs.*?cmp edx, ebx.*?add ebx, 1024.*?cmp eax, ebx' -or
    $bios -notmatch '(?s)validate_request:.*?call check_disk_buffer\s+jc \.bad' -or
    $bios -notmatch '(?s)fill_edd_parameters:.*?call check_disk_buffer\s+jc \.bad') {
    throw "EBDA reservation or conventional-memory transfer boundary changed."
}
$bufferCheck = [regex]::Match($bios, '(?s)check_disk_buffer:(.*?)validate_request:').Groups[1].Value
if ($bufferCheck -match '0xA0000|0x100000') {
    throw "Disk buffers must accept EMM386 upper-memory mappings and the HMA."
}
if ($bios -notmatch '(?s)\.legacy:.*?or al, 0xA0\s+out POST_PORT, al.*?\.legacy_chs_error:.*?post_code 0xB2.*?\.legacy_io_error:.*?post_code 0xB3') {
    throw "Legacy boot-read diagnostics changed."
}
$shadowPath = [regex]::Match($bios, '(?s); Relocate the embedded lower ROM(.*?)post_code 0x40').Groups[1].Value
Assert-SystemShadow $bios
Assert-NoTemporaryDiagnostics $bios
if ($shadowPath -notmatch '(?s)out CHIPSET_CONFIG_ON, al\s+mov dx, CHIPSET_INDEX\s+mov al, ROMSET_REG\s+out dx, al\s+inc dx\s+mov al, VGA_ROMSET_VALUE\s+out dx, al\s+wbinvd.*?mov al, VGA_SHADOW_CLEAR\s+out dx, al\s+wbinvd.*?mov cx, VGA_ROM_WORDS\s+rep stosw.*?mov al, VGA_SHADOW_FILL\s+out dx, al\s+wbinvd.*?call validate_vga_image\s+jc \.vga_mapping_failed.*?mov cx, VGA_ROM_WORDS\s+rep movsw.*?mov al, VGA_SHADOW_RUN\s+out dx, al\s+wbinvd\s+call validate_vga_image\s+jc \.vga_shadow_failed\s+out CHIPSET_CONFIG_OFF, al') {
    throw "OEM VGA ROM mapping and shadow sequence changed."
}
if ($bios -notmatch '(?s)ata_detect_primary:.*?call ata_reset_bus.*?ata_identify_selected:.*?or al, \[fs:S_ATA_DEVICE\].*?call ata_delay.*?mov cx, 15000.*?test al, 0x80\s+jz \.identify\s+call kbc_delay_2ms\s+loop \.not_busy.*?\.identify:.*?call ata_packet_signature\s+jnc \.packet_identify') {
    throw "POST IDENTIFY must reset the channel, wait for BSY with the PIT, and retain the packet reset signature."
}
$resetPath = [regex]::Match($bios, '(?s)ata_reset:(.*?)ata_transfer:').Groups[1].Value
$delayPath = [regex]::Match($bios, '(?s)ata_delay:(.*?)int19:').Groups[1].Value
if ($resetPath -notmatch '(?s)^\s+push dx\s+call ata_reset_bus\s+call ata_select_ready\s+jc \.done' -or
    $resetPath -notmatch '(?s)pop fs\s+call ata_select_ready\s+\.done:\s+pop dx\s+ret' -or
    $resetPath -notmatch '(?s)ata_reset_bus:\s+push cx\s+push dx\s+mov dx, ATA_CONTROL\s+mov al, 4\s+out dx, al\s+mov cx, 16\s+\.hold_srst:\s+call ata_delay\s+loop \.hold_srst\s+xor al, al\s+out dx, al\s+mov cx, 5000\s+\.settle:\s+call ata_delay\s+loop \.settle\s+pop dx\s+pop cx\s+ret') {
    throw "ATA reset timing or ordering changed."
}
if ($delayPath -notmatch '(?s)mov dx, ATA_CONTROL\s+mov cx, 4\s+\.again:\s+in al, dx\s+loop \.again') {
    throw "ATA four-read delay changed."
}
$readyPolling = [regex]::Match($bios, '(?s)ata_wait_ready:(.*?)ata_wait_complete:').Groups[1].Value
$completePolling = [regex]::Match($bios, '(?s)ata_wait_complete:(.*?)ata_wait_drq:').Groups[1].Value
$drqPolling = [regex]::Match($bios, '(?s)ata_wait_drq:(.*?)ata_read_status:').Groups[1].Value
if ($readyPolling -notmatch '(?s)test al, 0x80\s+jnz \.next\s+test al, 0x40\s+jnz \.ok.*?dec ecx\s+jnz \.loop') {
    throw "ATA ready polling order or 32-bit timeout changed."
}
if ($completePolling -notmatch '(?s)test al, 0x80\s+jnz \.next\s+test al, 0x21\s+jnz \.controller.*?dec ecx\s+jnz \.loop') {
    throw "ATA completion polling order or 32-bit timeout changed."
}
if ($drqPolling -notmatch '(?s)test al, 0x80\s+jnz \.next\s+test al, 0x21.*?dec ecx\s+jnz \.loop') {
    throw "ATA data polling order or 32-bit timeout changed."
}

if ($SelfTest) {
    foreach ($delta in @(-1, 1)) {
        Expect-Failure { Assert-RomSize ([byte[]]::new(65536 + $delta)) 65536 'System' } "wrong system size"
        Expect-Failure { Assert-RomSize ([byte[]]::new(131072 + $delta)) 131072 'Physical' } "wrong physical size"
    }
    $changedChecksum = [byte[]]$system.Clone()
    $changedChecksum[65535] = $changedChecksum[65535] -bxor 1
    Expect-Failure { Assert-SystemChecksum $changedChecksum } "a changed checksum byte"
    Expect-Failure { Assert-MouseExclusion ($mouse -replace '(?m)^    cli[^\r\n]*\r?\n', '') } "missing mouse transaction CLI"
    # Self-tests exercise the original retained-reference identity, even for a variant.
    $referenceOriginal = [IO.File]::ReadAllBytes((Join-Path $root 'reference/COMPAQ_PROLINEA_MT_05-02-94.BIN'))
    $changedRetained = [byte[]]$referenceOriginal.Clone()
    $changedRetained[17] = $changedRetained[17] -bxor 1
    Expect-Failure { Assert-RetainedReference $changedRetained } "a changed retained byte"

    $changedUpper = [byte[]]$referenceOriginal.Clone()
    $changedUpper[65536] = $changedUpper[65536] -bxor 1
    Assert-RetainedReference $changedUpper

    foreach ($offset in 1..4) {
        $changedReset = [byte[]]$system.Clone()
        $changedReset[0xFFF0 + $offset] = $changedReset[0xFFF0 + $offset] -bxor 1
        Expect-Failure { Assert-ResetVector $changedReset } "a changed reset target byte"
    }

    $wrongPort = $source.Replace('%define POST_PORT           0x0080', '%define POST_PORT           0x0084')
    Expect-Failure { Assert-PostTrace $wrongPort $bios } "POST port 84h"

    $missingPost = [regex]::Replace($bios, '(?m)^\s*post_code 0x60\s*\r?\n', '', 1)
    Expect-Failure { Assert-PostTrace $source $missingPost } "a missing POST checkpoint"

    $duplicatePattern = [regex]::new('(?m)^(\s*post_code_early 0x20\s*)$')
    $duplicatePost = $duplicatePattern.Replace($bios, '$1' + [Environment]::NewLine + '    post_code_early 0x20', 1)
    Expect-Failure { Assert-PostTrace $source $duplicatePost } "a duplicate POST checkpoint"

    $reorderedPost = $bios.Replace('post_code 0x40', 'post_code 0xFE').Replace('post_code 0x50', 'post_code 0x40').Replace('post_code 0xFE', 'post_code 0x50')
    Expect-Failure { Assert-PostTrace $source $reorderedPost } "reordered POST checkpoints"

    $movedVgaPost = [regex]::Replace($bios, '(?m)^\s*post_code 0x60\s*\r?\n', '', 1)
    $vgaCallPattern = [regex]::new('(?m)^(\s*call VGA_SEGMENT:VGA_ENTRY\s*)$')
    $movedVgaPost = $vgaCallPattern.Replace($movedVgaPost, '    post_code 0x60' + [Environment]::NewLine + '$1', 1)
    Expect-Failure { Assert-PostTrace $source $movedVgaPost } "60h before retained VGA returns"

    $movedRamPost = [regex]::Replace($bios, '(?m)^\s*post_code_early 0x30\s*\r?\n', '', 1)
    $ramClearPattern = [regex]::new('(?m)^(\s*rep stosw\s*)$')
    $movedRamPost = $ramClearPattern.Replace($movedRamPost, '$1' + [Environment]::NewLine + '    post_code_early 0x30', 1)
    Expect-Failure { Assert-PostTrace $source $movedRamPost } "30h after the AX reset"

    foreach ($instruction in @('call post_helper', 'push ax', 'mov [0x0500], al')) {
        $unsafePreRam = $bios.Replace('    post_code_early 0x20', "    $instruction" + [Environment]::NewLine + '    post_code_early 0x20')
        Expect-Failure { Assert-PostTrace $source $unsafePreRam } "pre-RAM $instruction"
    }

    $emptyTrace = [regex]::Replace($bios, '(?m)^\s*post_code(?:_early)? 0x[1-8]0\s*\r?\n', '')
    Expect-Failure { Assert-PostTrace $source $emptyTrace } "an empty POST trace"

    $finalOnlyTrace = [regex]::Replace($bios, '(?m)^\s*post_code(?:_early)? 0x[1-7]0\s*\r?\n', '')
    Expect-Failure { Assert-PostTrace $source $finalOnlyTrace } "a final-only POST trace"

    $postMacroPattern = [regex]::new('(?m)^\s*push ax\s*\r?\n\s*post_code_early %1\s*\r?\n\s*pop ax\s*$')
    $clobberedAx = $postMacroPattern.Replace($bios, '    post_code_early %1', 1)
    Expect-Failure { Assert-PostTrace $source $clobberedAx } "a later POST macro that clobbers AX"

    $flagMacroPattern = [regex]::new('(?m)^(\s*post_code_early %1\s*)$')
    $clobberedFlags = $flagMacroPattern.Replace($bios, '$1' + [Environment]::NewLine + '    or al, al', 1)
    Expect-Failure { Assert-PostTrace $source $clobberedFlags } "a later POST macro that clobbers flags"

    foreach ($code in @('E1', 'E2', 'E3', 'E4')) {
        $changedTerminalCode = if ($code -eq 'E4') { $bios.Replace('post_code 0xE4', 'post_code 0xD0') } else { $bios.Replace("mov al, 0x$code", 'mov al, 0xD0') }
        Expect-Failure { Assert-PostTrace $source $changedTerminalCode } "changed terminal code $code"
    }

    foreach ($change in @(
        @('jmp hard_halt', 'jmp halt_forever'),
        @('jmp halt_forever', 'jmp hard_halt')
    )) {
        $changedTerminalOwner = $bios.Replace($change[0], $change[1])
        Expect-Failure { Assert-PostTrace $source $changedTerminalOwner } "changed terminal owner $($change[0])"
    }

    Expect-Failure { Assert-PostTrace $source ($bios.Replace('jmp boot_retry', 'jmp hard_halt')) } "retry replaced by a fatal halt"
    $earlyTone = $bios.Replace("    call chipset_late_cache`n    call post_success_tone", "    call post_success_tone`n    call chipset_late_cache")
    Expect-Failure { Assert-PostTrace $source $earlyTone } "success tone before late cache qualification"
    Expect-Failure { Assert-PostTrace $source ($bios.Replace("    post_code 0xFF", "    post_code 0xFE")) } "missing late POST completion"
    Expect-Failure { Assert-NoTemporaryDiagnostics ($bios + "`n    post_code 0xCB") } "runtime IRQ tracing"
    $missingLegendCode = [regex]::Replace($readme, '(?m)^\| `E6h`.*\r?\n', '', 1)
    Expect-Failure { Assert-SystemShadow ($bios.Replace('repe cmpsw', 'rep movsw')) } "a missing system shadow comparison"
    Expect-Failure { Assert-SystemShadow ($bios.Replace('jmp 0x1000:.staged', 'jmp 0xF000:.staged')) } "execution from ROM while remapping it"
    Expect-Failure { Assert-SystemShadow ($bios.Replace('mov dx, 0x03DA', 'mov dx, 0x03DB')) } "a missing attribute flip-flop reset"
    Expect-Failure { Assert-PostLegend $missingLegendCode } "a missing README POST code"

    $extraLegendCode = $readme + [Environment]::NewLine + '| `FEh` | Unexpected code. |' + [Environment]::NewLine
    Expect-Failure { Assert-PostLegend $extraLegendCode } "an extra README POST code"

    $drqCompletion = $bios.Replace("    test al, 0x21`n    jnz .controller`n    clc", "    test al, 0x21`n    jnz .controller`n    test al, 0x08`n    jnz .next`n    clc")
    Expect-Failure { Assert-NoFinalDrqGate $drqCompletion } "a final DRQ-clear completion gate"

    $warmOr = $bios.Replace("    test al, 0x04`n    jz .warm_marker_captured", "    test al, 0x04`n    nop")
    Expect-Failure { Assert-Keyboard $source $warmOr $keyboardGuest } "a BDA-only warm predicate"
    $missingRetainedMarker = $bios.Replace('cmp word [0x0472], 0x1234', 'cmp ax, 0x1234')
    Expect-Failure { Assert-Keyboard $source $missingRetainedMarker $keyboardGuest } "a missing retained-map warm marker"

    $missingAtPrerequisite = $bios.Replace("    mov al, 0x0C`n    out SYSTEM_PORT_B, al", "    xor al, al`n    out SYSTEM_PORT_B, al")
    Expect-Failure { Assert-Keyboard $source $missingAtPrerequisite $keyboardGuest } "a missing Port 61h prerequisite"

    $noEnable = [regex]::Replace($bios, '(?s)(mov al, 0x5C\s+call kbc_write_data\s+jc \.command_failed.*?)mov al, 0xAE', '${1}mov al, 0xAD', 1)
    Expect-Failure { Assert-Keyboard $source $noEnable $keyboardGuest } "a keyboard interface left disabled"
    $xtMode = $bios.Replace('mov al, 0x5C', 'mov al, 0x7D')
    Expect-Failure { Assert-Keyboard $source $xtMode $keyboardGuest } "XT protocol during AT keyboard reset"
    $pollRace = $bios.Replace("    ; Polling owns every controller response until runtime is armed.`n    cli", "    ; Polling owns every controller response until runtime is armed.`n    sti")
    Expect-Failure { Assert-Keyboard $source $pollRace $keyboardGuest } "interrupts consuming reset replies"

    $shortBatWait = $bios.Replace("    mov cx, 50`n.wait_bat_response:", "    mov cx, 9`n.wait_bat_response:")
    Expect-Failure { Assert-Keyboard $source $shortBatWait $keyboardGuest } "the shortened non-OEM BAT wait"

    $wrongOutputPort = $bios.Replace("    mov al, 0xCF`n    out KBC_DATA, al", "    mov al, 0xDF`n    out KBC_DATA, al")
    Expect-Failure { Assert-Keyboard $source $wrongOutputPort $keyboardGuest } "the wrong OEM 8042 output-port value"

    $shortOutputPortWait = $bios.Replace("    xor cx, cx`n.wait:", "    mov cx, 100`n.wait:")
    Expect-Failure { Assert-Keyboard $source $shortOutputPortWait $keyboardGuest } "the shortened MR BIOS output-port wait"

    $batFiltered = $bios.Replace("    cmp bl, 0xFE`n    je .led_resend", "    cmp bl, 0xFE`n    je .led_resend`n    cmp bl, 0xAA`n    je .led_resend")
    Expect-Failure { Assert-Keyboard $source $batFiltered $keyboardGuest } "runtime AAh BAT filtering"

    $overwriteFull = $bios.Replace("    cmp dx, [KB_HEAD]`n    je .full", "    cmp dx, [KB_HEAD]`n    jne .full")
    Expect-Failure { Assert-Keyboard $source $overwriteFull $keyboardGuest } "FIFO overwrite on full"

    $peekConsumes = [regex]::Replace($bios, '(?s)(\.available:\s+mov ax, \[bx\])', '${1}' + [Environment]::NewLine + '    mov [KB_HEAD], dx', 1)
    Expect-Failure { Assert-Keyboard $source $peekConsumes $keyboardGuest } "a consuming INT 16h status call"

    $lostWarmEntry = $bios.Replace('jmp 0xF000:startup.warm_start', 'jmp 0xF000:startup')
    Expect-Failure { Assert-Keyboard $source $lostWarmEntry $keyboardGuest } "Ctrl+Alt+Delete entering cold startup"
}

"ROM verification passed."
