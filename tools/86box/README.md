# Shared 86Box resources

Keep the emulator source checkout in tools/86box/source and the stock ROM checkout in tools/86box/roms. Keep common downloaded drivers and IDE research inputs in tools/deps. These directories are ignored installed resources, not source copies maintained by bAIos.

The executable is installed system-wide by WinGet. Existing runners select it from PATH or the existing WinGet fallback. A source checkout is not a compiled emulator installation.

Provision missing checkouts from the repository root:

    git clone https://github.com/86Box/86Box.git tools/86box/source
    git clone https://github.com/86Box/roms.git tools/86box/roms

The relocated source checkout is at 6c935be21a0ebdb218cd668bb2263c7f1625e1a0. The relocated ROM checkout is at c761288ecddccb36d5664d33c0199e9d0b4e8454. These are recorded input identities, not selected firmware version defaults.

Use the shared collection as an input. Port builds must create private ROM adapters, configuration, NVRAM, and media beneath their own build directory. They must not write generated BIOS images into the shared collection.

Two pre-existing local collection modifications are retained at presario-800/reference/86box under their original relative paths. The Cirrus 5428 input remains selected by Presario build/capture code. The modified D824 input remains a port reference with unresolved provenance. Both original byte sequences are preserved. The shared collection uses its own upstream bytes for those files.

Use repository-root shared/tools for generic utility implementations. Keep system firmware identity and hardware configuration with each port.
