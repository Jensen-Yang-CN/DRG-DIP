$ErrorActionPreference = 'Stop'

& "$PSScriptRoot\scripts\prepare-demo-start.ps1"

$python = (Get-Command python).Source
$process = Start-Process -FilePath $python -ArgumentList @('server.py', '--host', '127.0.0.1', '--port', '8765') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
if ($process.HasExited) {
    throw 'Demo 服务启动失败。请在项目目录运行 python server.py 查看错误。'
}
$response = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/catalog?mode=drg' -UseBasicParsing -TimeoutSec 5
if ($response.StatusCode -ne 200 -or ($response.Content | ConvertFrom-Json).scheme -ne 'drg') {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw '新版 DRG 接口未能正常响应。'
}
Write-Output "Demo 已重启：PID $($process.Id)"
Write-Output '本地入口：http://127.0.0.1:8765/'
