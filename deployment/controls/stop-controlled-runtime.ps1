# SPDX-License-Identifier: AGPL-3.0-only
param([Parameter(Mandatory=$true)][string]$DataDir)
$ErrorActionPreference = 'Stop'
$backendPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../backend'))
$runtimeDataPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DataDir)
Push-Location -LiteralPath $backendPath
try {
    python -m app.controlled_runtime stop --data-dir $runtimeDataPath
    if ($LASTEXITCODE -ne 0) { throw 'No matching runtime receipt; do not stop processes by port.' }
} finally { Pop-Location }
