# Safe fictional operator journey. This script simulates a trusted local operator.
$ErrorActionPreference = 'Stop'
$manualRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ((Get-Location).Path -ne $manualRoot) { throw 'Run this script from the repository root.' }
$runtime = (& py -3.11 -c 'import json,sys,sqlite3; print(json.dumps(dict(executable=sys.executable, python=sys.version.split()[0], sqlite=sqlite3.sqlite_version)))') | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $runtime.python -ne '3.11.9') { throw 'Select Python 3.11.9 with py -3.11.' }
$manualWorkspace = Join-Path $manualRoot ('work/manual-m3-' + [guid]::NewGuid().ToString('N'))
$manualLogs = Join-Path $manualWorkspace 'commands'
$manualCommands = [System.Collections.Generic.List[object]]::new()
$manualHashes = [ordered]@{}
foreach ($manualFolder in @('agent_tool_authority', 'tests', 'scripts', 'examples', 'docs', '.github')) {
    Get-ChildItem -LiteralPath (Join-Path $manualRoot $manualFolder) -Recurse -File |
        Where-Object { $_.FullName -notmatch '__pycache__' -and $_.Extension -ne '.pyc' } |
        ForEach-Object { $manualHashes[$_.FullName.Substring($manualRoot.Length + 1).Replace('\', '/')] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}

function Invoke-Authority([string]$Label, [int]$ExpectedExit, [string[]]$Arguments) {
    # Init must see an empty workspace; its logs are saved after the command.
    $manualErrorFile = Join-Path $manualRoot ('work/manual-stderr-' + [guid]::NewGuid().ToString('N') + '.txt')
    New-Item -ItemType Directory -Force -Path (Join-Path $manualRoot 'work') | Out-Null
    $manualOut = & py -3.11 -m agent_tool_authority @Arguments 2> $manualErrorFile
    $manualExit = $LASTEXITCODE
    New-Item -ItemType Directory -Force -Path $manualLogs | Out-Null
    $manualStdout = ($manualOut -join "`n") + "`n"
    $manualStderr = [System.IO.File]::ReadAllText($manualErrorFile)
    $manualOutPath = Join-Path $manualLogs ($Label + '.stdout.txt')
    $manualErrPath = Join-Path $manualLogs ($Label + '.stderr.txt')
    [System.IO.File]::WriteAllText($manualOutPath, $manualStdout)
    [System.IO.File]::WriteAllText($manualErrPath, $manualStderr)
    Remove-Item -LiteralPath $manualErrorFile
    $manualCommands.Add([ordered]@{label=$Label; argv=@('py','-3.11','-m','agent_tool_authority') + $Arguments; cwd=$manualRoot; interpreter=$runtime.executable; expected_exit=$ExpectedExit; exit_code=$manualExit; stdout=$manualOutPath; stderr=$manualErrPath})
    $manualCommands | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $manualWorkspace 'commands.json') -Encoding utf8
    if ($manualExit -ne $ExpectedExit) { throw "$Label expected $ExpectedExit, got $manualExit" }
    Write-Host "$Label native exit $manualExit"
    if ($Label -eq 'audit') { return $manualStdout }
    return $manualStdout | ConvertFrom-Json
}

$init = Invoke-Authority 'init' 0 @('init','--workspace',$manualWorkspace)
$read = Invoke-Authority 'read' 0 @('submit','--workspace',$manualWorkspace,'--session','support-agent','--request','examples/requests/read.json')
$close = Invoke-Authority 'close' 4 @('submit','--workspace',$manualWorkspace,'--session','support-agent','--request','examples/requests/close.json')
$pendingAction = Invoke-Authority 'resolve' 3 @('submit','--workspace',$manualWorkspace,'--session','support-agent','--request','examples/requests/resolve.json')
$reviewedAction = Invoke-Authority 'review' 0 @('pending','--workspace',$manualWorkspace,'--request-id',$pendingAction.request_id)
$reviewedAction.review | ConvertTo-Json -Depth 10 | Write-Host
if ($read.execution -ne 'EXECUTED' -or $close.execution -ne 'NOT_EXECUTED' -or $pendingAction.execution -ne 'NOT_EXECUTED') { throw 'Unexpected pre-approval execution.' }
if ($reviewedAction.review.state -ne 'PENDING' -or $reviewedAction.review.fingerprint -ne $pendingAction.fingerprint -or $reviewedAction.review.action.call.arguments.status -ne 'resolved' -or $reviewedAction.review.action.call.arguments.expected_version -ne 1) { throw 'Unexpected reviewed action.' }

# Explicit operator approval of the actual stored action just printed, then immediate resume.
$approved = Invoke-Authority 'approve' 0 @('approve','--workspace',$manualWorkspace,'--request-id',$pendingAction.request_id,'--fingerprint',$reviewedAction.review.fingerprint,'--ttl-seconds','60')
$resumed = Invoke-Authority 'resume' 0 @('resume','--workspace',$manualWorkspace,'--session','support-agent','--request-id',$pendingAction.request_id)
$replay = Invoke-Authority 'replay' 4 @('resume','--workspace',$manualWorkspace,'--session','support-agent','--request-id',$pendingAction.request_id)
$audit = Invoke-Authority 'audit' 0 @('audit','--workspace',$manualWorkspace,'--format','jsonl')
if ($approved.code -ne 'APPROVED' -or $resumed.output.status -ne 'resolved' -or $resumed.output.version -ne 2 -or $replay.code -ne 'APPROVAL_CONSUMED') { throw 'Unexpected approval/resume/replay outcome.' }
$manualReceipt = [ordered]@{schema='ata-manual-verification/v1'; finished_at_utc=[DateTime]::UtcNow.ToString('o'); runtime=$runtime; cwd=$manualRoot; source_sha256=$manualHashes; mode='scripted_local_operator_journey'; model_execution='none'; workspace=$manualWorkspace; commands=$manualCommands; assertions='passed'; resumed=$resumed; replay=$replay}
$manualReceipt | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $manualWorkspace 'receipt.json') -Encoding utf8
Write-Host "receipt: $manualWorkspace/receipt.json"
