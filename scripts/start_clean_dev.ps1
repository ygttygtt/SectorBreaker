param(
    [int]$BackendPort = 8030,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

function Stop-PortListeners {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    $pids = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($processId in $pids) {
        if ($processId -and $processId -ne 0) {
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "Stopping process $processId on port $Port ($($process.ProcessName))"
                Stop-Process -Id $processId -Force
            }
        }
    }
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    Stop-PortListeners -Port $BackendPort
    Stop-PortListeners -Port $FrontendPort
    Start-Sleep -Seconds 1

    $backendCmd = "uvicorn backend.app.api.app:app --host 127.0.0.1 --port $BackendPort"
    $frontendCmd = "cd frontend; npm run dev -- --host 127.0.0.1 --port $FrontendPort"

    Write-Host "Starting backend: $backendCmd"
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $backendCmd -WorkingDirectory (Get-Location) -WindowStyle Hidden

    Write-Host "Starting frontend: $frontendCmd"
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $frontendCmd -WorkingDirectory (Get-Location) -WindowStyle Hidden

    Write-Host "Backend:  http://127.0.0.1:$BackendPort"
    Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
    Write-Host "Clean dev stack started. Use Get-NetTCPConnection to verify single listeners."
}
finally {
    Pop-Location
}
