# Public source and private inputs

The public repository contains original bAIos source and documentation. It excludes vendor ROMs, manuals, operating-system media, personal configuration, private history and generated build output.

The MIT license covers original bAIos work. It does not grant rights to external firmware, documents or software. An image that contains retained vendor firmware remains subject to that firmware's terms.

## Supply build inputs

Read the selected port manual before building. Its developer documentation describes required reference files and media. The [input catalogue](private-inputs.json) records file identities without distributing their contents.

Place inputs at their documented locations. Build scripts compare their identities before using them. A matching checksum identifies a file. It does not grant permission to distribute it.

Keep original inputs unchanged. Local paths in development records describe private files and are not instructions to download an arbitrary replacement.

## Prepare public source

Run this command from the repository root:

```powershell
python -B tools/check-public-source.py
```

The guard checks tracked paths, common credential formats, personal paths and source syntax. It cannot detect every possible secret. Review the exact files selected for publication.

Do not force-add ignored ROMs, extracted firmware, photographs, media or logs. Never publish private development history as another branch or tag. Build and hardware results stay separate from the source-publication check.
