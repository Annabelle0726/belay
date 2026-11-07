# SPDX-License-Identifier: AGPL-3.0-only
[CmdletBinding()]
param([string]$DataDir = (Join-Path $PSScriptRoot 'deployment/local/controlled-runtime'))
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'deployment/controls/stop-controlled-runtime.ps1') -DataDir $DataDir
