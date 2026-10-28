# SPDX-License-Identifier: AGPL-3.0-only
param(
    [Parameter(Mandatory=$true)][string]$DataDir,
    [Parameter(Mandatory=$true)][string]$EnvFile,
    [string]$CredentialsEnvFile,
    [switch]$Check,
    [switch]$UseAmountOnlyBudget,
    [string]$BudgetAuthorization,
    [string]$BudgetPolicy
)
$ErrorActionPreference = 'Stop'
if ($Check -and $UseAmountOnlyBudget) { throw 'Choose Check or UseAmountOnlyBudget, not both.' }
if (([bool]$BudgetAuthorization -ne [bool]$BudgetPolicy) -or ($BudgetAuthorization -and ($Check -or $UseAmountOnlyBudget))) { throw 'BudgetAuthorization and BudgetPolicy must be supplied together, separately from Check/UseAmountOnlyBudget.' }
$budgetArgs = @()
if ($BudgetAuthorization) { $budgetArgs = @('--authorization', (Resolve-Path -LiteralPath $BudgetAuthorization).Path, '--policy', (Resolve-Path -LiteralPath $BudgetPolicy).Path) }
$backendPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../backend'))
$runtimeDataPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DataDir)
if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw 'Runtime EnvFile is missing. Keep the /.env path segment; prepare a new installation only on first use.'
}
$runtimeEnvPath = (Resolve-Path -LiteralPath $EnvFile).Path
$credentialArgs = @()
if ($CredentialsEnvFile) { $credentialArgs = @('--credentials-env-file', (Resolve-Path -LiteralPath $CredentialsEnvFile).Path) }
Push-Location -LiteralPath $backendPath
try {
    # Foreground; prompt only if the selected provider has no configured credential.
    $action = 'start'
    $promptArgs = @('--prompt-missing-key')
    if ($Check) { $action = 'check'; $promptArgs = @() }
    if ($UseAmountOnlyBudget) { $action = 'use-amount-only-budget'; $promptArgs = @() }
    if ($BudgetAuthorization) { $action = 'authorize-budget'; $promptArgs = @() }
    python -m app.controlled_runtime $action --data-dir $runtimeDataPath --env-file $runtimeEnvPath @credentialArgs @promptArgs @budgetArgs
    if ($LASTEXITCODE -ne 0) { throw 'Controlled runtime failed; run check and inspect private configuration.' }
} finally { Pop-Location }
