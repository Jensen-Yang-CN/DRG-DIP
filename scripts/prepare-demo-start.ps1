$ErrorActionPreference = 'Stop'

$ProgressPreference = 'SilentlyContinue'
$port = 8765
$baseUrl = 'http://127.0.0.1:8765'
$catalog = $null
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/api/catalog" -UseBasicParsing -TimeoutSec 2
    if ($response.StatusCode -eq 200) {
        $catalog = $response.Content | ConvertFrom-Json
    }
} catch {
    # No usable demo endpoint is listening; check the port below.
}

if ($catalog) {
    if (-not $catalog.coreCount -or -not $catalog.edition -or $catalog.edition -notmatch 'DIP') {
        throw '端口 8765 已被其他服务占用，请先关闭该服务。'
    }

    $demoProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object {
            $_.CommandLine -match '(^|[\\/\s])server\.py(\s|$)' -and
            $_.CommandLine -match '(--port\s+8765|--port=8765)'
        })
    if (-not $demoProcesses) {
        throw '检测到旧版 DIP 服务，但无法定位其进程。请关闭占用 8765 端口的旧服务后重试。'
    }

    foreach ($demoProcess in $demoProcesses) {
        Write-Output "正在关闭旧版 Demo 服务（PID $($demoProcess.ProcessId)）..."
        Stop-Process -Id $demoProcess.ProcessId -Force
    }
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 250
        try {
            $null = Invoke-WebRequest -Uri "$baseUrl/api/catalog" -UseBasicParsing -TimeoutSec 1
        } catch {
            break
        }
    }
}

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw '端口 8765 仍被占用，未启动新服务。请关闭原有服务后重试。'
}
