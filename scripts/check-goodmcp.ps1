param([switch]$LocalOnly)
$ErrorActionPreference = 'Stop'
$goodmcpRoot = Split-Path -Parent $PSScriptRoot
$goodmcpExit = 1
Push-Location $goodmcpRoot
try {
    $goodmcpArguments = @('run', '--frozen', 'python', '-m', 'blender_mcp.goodmcp', 'check')
    if ($LocalOnly) { $goodmcpArguments += '--local-only' }
    & uv @goodmcpArguments
    $goodmcpExit = $LASTEXITCODE
} finally { Pop-Location }
exit $goodmcpExit
