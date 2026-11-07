# SPDX-License-Identifier: AGPL-3.0-only
# Run with the backend dependencies installed in the active Python environment.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$configDir = Join-Path $root 'deployment/local/controlled-config'
$dataDir = Join-Path $root 'deployment/local/controlled-runtime'
if ((Test-Path -LiteralPath $configDir) -or (Test-Path -LiteralPath $dataDir)) {
    throw 'Local configuration or data already exists. Use the check/start commands for a prepared installation.'
}

New-Item -ItemType Directory -Path $configDir | Out-Null
$envFile = Join-Path $configDir '.env'
$policy = Join-Path $configDir 'policy.json'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'controlled-runtime.env.example') -Destination $envFile
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'controlled-runtime-policy.example.json') -Destination $policy
Push-Location -LiteralPath (Join-Path $root 'backend')
try {
    python -m app.controlled_runtime prepare --data-dir $dataDir --env-file $envFile --policy $policy --api-port 8004 --frontend-port 5177
    if ($LASTEXITCODE -ne 0) { throw 'Preparation failed. Inspect the local configuration before retrying.' }
    python -m app.controlled_runtime check --data-dir $dataDir --env-file $envFile
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed. Inspect the local configuration.' }
} finally {
    Pop-Location
}
