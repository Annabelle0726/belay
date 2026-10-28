# SPDX-License-Identifier: AGPL-3.0-only
[CmdletBinding()]
param(
    [string]$DataDir = (Join-Path $PSScriptRoot 'deployment/local/controlled-runtime'),
    [string]$EnvFile = (Join-Path $PSScriptRoot 'deployment/local/controlled-config/.env'),
    [string]$CredentialsEnvFile,
    [switch]$Check,
    [switch]$UseAmountOnlyBudget,
    [string]$BudgetAuthorization,
    [string]$BudgetPolicy
)
$ErrorActionPreference = 'Stop'
# Defaults are checkout-relative. Explicit paths remain caller-relative.
if (-not $PSBoundParameters.ContainsKey('CredentialsEnvFile')) {
    $defaultCredentials = Join-Path $PSScriptRoot 'backend/.env'
    if (Test-Path -LiteralPath $defaultCredentials -PathType Leaf) {
        $CredentialsEnvFile = $defaultCredentials
    }
}
& (Join-Path $PSScriptRoot 'deployment/controls/start-controlled-runtime.ps1') `
    -DataDir $DataDir -EnvFile $EnvFile -CredentialsEnvFile $CredentialsEnvFile -Check:$Check -UseAmountOnlyBudget:$UseAmountOnlyBudget -BudgetAuthorization $BudgetAuthorization -BudgetPolicy $BudgetPolicy
