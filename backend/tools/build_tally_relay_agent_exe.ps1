# build_tally_relay_agent_exe.ps1 — packages tally_relay_agent.py into a
# standalone Windows .exe so an accountant's machine needs no Python install
# at all. Verified working end-to-end (2026-08-06): built exe correctly
# pairs against a real backend, persists its config next to the .exe (not
# into PyInstaller's ephemeral extraction temp dir — see IS_FROZEN /
# PROGRAM_DIR in tally_relay_agent.py, which this build depends on), and
# shows "online" in the Tally Sync UI after polling.
#
# Usage (from backend/tools/):
#     .\build_tally_relay_agent_exe.ps1
#
# Output: dist\AuditOSTallyRelayAgent.exe — copy this single file onto the
# accountant's machine. No tally_connector.py needed alongside it; PyInstaller
# bundles it into the exe (see the temporary copy step below).

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

python -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..."
    python -m pip install pyinstaller
}

# tally_relay_agent.py imports tally_connector.py via a bare `import
# tally_connector` when run unfrozen from this directory — PyInstaller's
# static analysis needs the file physically present here to discover and
# bundle it (see the module docstring's IS_FROZEN section). Copied
# temporarily, removed after the build so the repo doesn't carry a
# duplicate of services/tally_connector.py.
$connectorSrc = Join-Path $ScriptDir "..\services\tally_connector.py"
$connectorDst = Join-Path $ScriptDir "tally_connector.py"
Copy-Item $connectorSrc $connectorDst -Force

try {
    # PyInstaller logs its normal INFO output to stderr — under
    # $ErrorActionPreference = "Stop" that gets misread as a terminating
    # error (confirmed live: the build actually succeeds but the script
    # aborts on PyInstaller's first INFO line). Relax it for just this call.
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    python -m PyInstaller --onefile --name AuditOSTallyRelayAgent --clean tally_relay_agent.py
    $buildExitCode = $LASTEXITCODE
    $ErrorActionPreference = $prevPref
    if ($buildExitCode -ne 0) {
        throw "PyInstaller exited with code $buildExitCode"
    }
} finally {
    Remove-Item $connectorDst -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $ScriptDir "build") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $ScriptDir "AuditOSTallyRelayAgent.spec") -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Built: $(Join-Path $ScriptDir 'dist\AuditOSTallyRelayAgent.exe')"
Write-Host "Copy this one file to the accountant's machine. First run there:"
Write-Host "  AuditOSTallyRelayAgent.exe --pair CODE --backend-url https://auditos-backend.onrender.com"
Write-Host "  AuditOSTallyRelayAgent.exe --install-startup   (optional: launch automatically at login)"
