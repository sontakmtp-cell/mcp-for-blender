param([switch]$LocalTest, [switch]$NoTunnel)
$ErrorActionPreference = 'Stop'
$goodmcpRoot = Split-Path -Parent $PSScriptRoot
$goodmcpExit = 1
Push-Location $goodmcpRoot
try {
    $goodmcpArguments = @('run', '--frozen', 'python', '-m', 'blender_mcp.goodmcp', 'start')
    if ($LocalTest) { $goodmcpArguments += '--local-test' }
    if ($NoTunnel) { $goodmcpArguments += '--no-tunnel' }
    & uv @goodmcpArguments
    $goodmcpExit = $LASTEXITCODE
} finally { Pop-Location }
exit $goodmcpExit
