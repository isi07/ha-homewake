# Startet scripts/dev.sh in WSL, damit man die Entwicklungsbefehle bequem aus
# Windows-PowerShell aufrufen kann.
#
# Beispiele:
#   .\scripts\dev.ps1 check      # ruff + mypy + pytest
#   .\scripts\dev.ps1 test -v    # nur Tests, ausführlich
#   .\scripts\dev.ps1 setup      # Umgebung anlegen / aktualisieren

$repo = Split-Path -Parent $PSScriptRoot
$wslRepo = (wsl -e wslpath -a ($repo -replace '\\', '/')).Trim()
wsl -e bash "$wslRepo/scripts/dev.sh" @args
exit $LASTEXITCODE
