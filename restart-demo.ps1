$ErrorActionPreference = 'Stop'

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if (-not $current -or $current.CommandLine -notmatch '(^|[\\/\s])server\.py(\s|$)') {
        throw "端口 8765 正由其他程序使用（PID $($listener.OwningProcess)），未重启。"
    }
    Stop-Process -Id $listener.OwningProcess
    Start-Sleep -Seconds 1
}

$python = (Get-Command python).Source
$process = Start-Process -FilePath $python -ArgumentList @('server.py', '--host', '127.0.0.1', '--port', '8765') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
if ($process.HasExited) {
    throw 'Demo 服务启动失败。请在项目目录运行 python server.py 查看错误。'
}
$response = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/catalog' -UseBasicParsing -TimeoutSec 5
if ($response.StatusCode -ne 200) {
    throw 'Demo 服务未能正常响应。'
}
Write-Output "Demo 已重启：PID $($process.Id)"
Write-Output '公网入口：https://medicineai.taildeb29a.ts.net/'
