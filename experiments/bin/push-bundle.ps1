<#
.SYNOPSIS
  把 A100 上打好的 git bundle 快进推到 GitHub（Windows 侧一键执行）。

.DESCRIPTION
  工作流：
    A100 开发提交 → experiments/bin/git-bundle.sh 生成 bundle（放在 exports/，被 .gitignore 忽略）
    → 同步到本机 → 本脚本校验并 push 到 origin。

  三道保护：
    1) bundle 必须通过 git bundle verify（完整历史）；
    2) 只允许 fast-forward，非快进直接中止（不会强推）；
    3) -DryRun 可先预演，什么都不改。

.PARAMETER Bundle
  bundle 路径。默认 $env:USERPROFILE\.dsh\remote-workspaces\wmv4mdfl29ql5\exports\nasctime-repo.bundle

.PARAMETER Repo
  本机 git 仓库根。默认按脚本位置推断（experiments/bin 的上两级），再退回当前目录。

.PARAMETER Remote
  远端名，默认 origin。

.PARAMETER Branch
  分支名，默认 main。

.PARAMETER NoSync
  只推远端，不把本地分支快进到 bundle 内容。

.PARAMETER DryRun
  只做校验和 git push --dry-run。

.EXAMPLE
  push-bundle.cmd -DryRun

.EXAMPLE
  push-bundle.cmd -Bundle D:\tmp\nasctime-repo.bundle
#>
[CmdletBinding()]
param(
    [string]$Bundle = "$env:USERPROFILE\.dsh\remote-workspaces\wmv4mdfl29ql5\exports\nasctime-repo.bundle",
    [string]$Repo   = '',
    [string]$Remote = 'origin',
    [string]$Branch = 'main',
    [switch]$NoSync,
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'

function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Info($m) { Write-Host "    $m" }
function Warn($m) { Write-Host "!!! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "`n[失败] $m" -ForegroundColor Red; exit 1 }

# 调 git：stderr 一并收进 Lines，用 Code 判断成败，避免 PowerShell 的 NativeCommandError 噪音
function Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
    $lines = & git @GitArgs 2>&1 | ForEach-Object { "$_" }
    [pscustomobject]@{ Code = $LASTEXITCODE; Lines = @($lines) }
}

function Show($lines) { foreach ($l in $lines) { if ("$l" -ne '') { Info $l } } }

# ---------- 1. 定位仓库 ----------
if ([string]::IsNullOrWhiteSpace($Repo)) {
    $cand = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if (Test-Path (Join-Path $cand '.git')) { $Repo = $cand }
    elseif (Test-Path (Join-Path (Get-Location).Path '.git')) { $Repo = (Get-Location).Path }
    else { Die "找不到 git 仓库：请用 -Repo 指定（脚本放在 experiments/bin 时会自动推断仓库根）" }
}
if (-not (Test-Path (Join-Path $Repo '.git'))) { Die "$Repo 不是 git 仓库" }
Write-Host "仓库  : $Repo"

# ---------- 2. 检查 bundle ----------
if (-not [System.IO.Path]::IsPathRooted($Bundle)) { $Bundle = Join-Path (Get-Location).Path $Bundle }
if (-not (Test-Path $Bundle)) {
    Die ("bundle 不存在：$Bundle`n" +
         "      先在 A100 上跑 experiments/bin/git-bundle.sh，再把 exports/ 同步到本机")
}
$f = Get-Item $Bundle
Write-Host "bundle: $($f.FullName)"
Info ("生成时间 {0}   大小 {1:N1} MB" -f $f.LastWriteTime, ($f.Length / 1MB))

Step "校验 bundle 完整性"
$r = Git bundle verify $Bundle
Show $r.Lines
if ($r.Code -ne 0) { Die "bundle 校验失败（若报缺少前置提交，请用 git bundle create --all 生成完整 bundle）" }

Step "确认 bundle 里有 refs/heads/$Branch"
$r = Git bundle list-heads $Bundle
Show $r.Lines
$sha = $null
$pat = '^([0-9a-f]{40,64})\s+refs/heads/' + [regex]::Escape($Branch) + '$'
foreach ($l in $r.Lines) { if ("$l" -match $pat) { $sha = $Matches[1] } }
if (-not $sha) { Die "bundle 里没有 refs/heads/$Branch；分支名不对就用 -Branch 指定（git bundle list-heads 可看全部）" }
Info "目标提交 $sha"

Set-Location $Repo
$curBranch = (Git rev-parse --abbrev-ref HEAD).Lines[0]
if ($LASTEXITCODE -ne 0) { Die "$Repo 不是有效的 git 工作区" }

# ---------- 3. 读 bundle + 刷新远端 ----------
Step "从 bundle 读取 refs/remotes/bundle/$Branch"
$r = Git fetch $Bundle "+refs/heads/$Branch:refs/remotes/bundle/$Branch"
Show $r.Lines
if ($r.Code -ne 0) { Die "从 bundle fetch 失败" }

Step "刷新远端 $Remote"
$r = Git fetch $Remote --prune
Show $r.Lines
if ($r.Code -ne 0) { Die "连不上远端 $Remote（网络或 SSH 凭据问题）" }

$remoteRef = "refs/remotes/$Remote/$Branch"
$r = Git rev-parse --verify --quiet $remoteRef
$hasRemote = ($r.Code -eq 0)
if ($hasRemote) { Info "远端 $Remote/$Branch 当前 = $($r.Lines[0])" }
else { Warn "远端还没有 $Remote/$Branch，将作为新分支推送" }

# ---------- 4. 快进检查 ----------
Step "快进检查（只允许 fast-forward）"
if ($hasRemote) {
    $r = Git merge-base --is-ancestor $remoteRef "refs/remotes/bundle/$Branch"
    if ($r.Code -eq 1) {
        Die ("不是快进：$Remote/$Branch 上有 bundle 里没有的提交。`n" +
             "      本脚本不会强推。处理办法：先在 A100 上把 GitHub 的改动并进来，再重新打 bundle。`n" +
             "      确实要覆盖就手工执行：git push --force-with-lease $Remote refs/remotes/bundle/$Branch`:refs/heads/$Branch")
    }
    if ($r.Code -ne 0) { Die "merge-base 检查出错：$($r.Lines -join ' ')" }
    Info "OK：$Remote/$Branch 是目标提交的祖先，可安全快进"
}

# ---------- 5. 列出将推送的提交 ----------
if ($hasRemote) { $r = Git log --oneline "$remoteRef..refs/remotes/bundle/$Branch" }
else { $r = Git log --oneline -20 "refs/remotes/bundle/$Branch" }
$n = @($r.Lines | Where-Object { "$_" -ne '' }).Count
Step "将推送 $n 个提交"
Show $r.Lines

# ---------- 6. 推送 ----------
$refspec = "refs/remotes/bundle/${Branch}:refs/heads/${Branch}"
if ($DryRun) {
    Step "预演（git push --dry-run，不实际推送）"
    $r = Git push --dry-run $Remote $refspec
} else {
    Step "推送"
    $r = Git push $Remote $refspec
}
Show $r.Lines
if ($r.Code -ne 0) {
    if ("$($r.Lines -join ' ')" -match 'couldn''t find remote ref|cannot open|Permission denied') {
        Die ("推送失败。若提示 `couldn't find remote ref`：检查参数末尾是否混入了分号——`n" +
             "      cmd.exe 不把 ; 当分隔符，会把它拼进 refspec。多条命令请用 && 或分行写。")
    }
    Die "推送失败（见上面 git 输出）"
}

# ---------- 7. 同步本地分支 ----------
if ($DryRun) {
    Warn "预演结束，未推送任何东西"
} elseif (-not $NoSync) {
    Step "同步本地分支 $Branch"
    if ($curBranch -ne $Branch) {
        Warn "当前分支是 $curBranch，不是 $Branch，跳过本地同步（用 -NoSync 可静默）"
    } else {
        $r = Git merge --ff-only "refs/remotes/bundle/$Branch"
        Show $r.Lines
        if ($r.Code -ne 0) { Warn "本地快进失败（工作区可能有未提交改动）。远端已推送成功，处理完在本地再 git merge --ff-only $Remote/$Branch" }
    }
}

# ---------- 8. 汇总 ----------
Step "完成"
$r = Git log -1 --pretty=format:'%h  %ci  %s' "refs/remotes/bundle/$Branch"
Show $r.Lines
Info "注意：GitHub 页面显示的「x 小时前」是提交时间（committer date），不是推送时间。"
Info "      你在 A100 上提交后隔了几小时才推，页面就会显示几小时前——内容不受影响。"
