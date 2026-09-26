# mdbindery installer for Windows (PowerShell 5.1 or 7+). Needs nothing else.
#
#   irm https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.ps1 | iex
#   .\install\install.ps1 -Local .              # from a checkout of the repository
#
# Parameters:
#   -Local PATH     install mdbindery from a local folder instead of GitHub
#   -Ref REF        branch, tag, or commit on GitHub (default: main)
#   -NoNode         skip Node.js, mermaid-cli, and Ace
#   -Java MODE      auto (default), always, never
#   -NoTools        install the mdbindery command only
#   -Uninstall      remove mdbindery, its tools, and its Python
#
# Environment: MDBINDERY_HOME (tool home, default %LOCALAPPDATA%\mdbindery),
#              MDBINDERY_BIN (command folder, default %USERPROFILE%\.local\bin)
[CmdletBinding()]
param(
  [string]$Local = '',
  [string]$Ref = 'main',
  [switch]$NoNode,
  [ValidateSet('auto', 'always', 'never')][string]$Java = 'auto',
  [switch]$NoTools,
  [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$UvVersion = '0.12.19'
$Repo = 'https://github.com/sagol/mdbindery'
$Arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
$UvAssets = @{
  'x64'   = @('uv-x86_64-pc-windows-msvc.zip', '6dbb02d79e419522f1c500f0adb1cddcff0cda7d59b0d66ea7f5e3b4a1b2f5f0')
  'arm64' = @('uv-aarch64-pc-windows-msvc.zip', '115b54cb823bc48260670f5782001add6067ac8d98d18c8263a833704e287de9')
}

$DefaultHome = Join-Path $env:LOCALAPPDATA 'mdbindery'
$Home_ = if ($env:MDBINDERY_HOME) { $env:MDBINDERY_HOME } else { $DefaultHome }
$env:MDBINDERY_HOME = $Home_
$BinDir = if ($env:MDBINDERY_BIN) { $env:MDBINDERY_BIN } else { Join-Path $env:USERPROFILE '.local\bin' }
New-Item -ItemType Directory -Force -Path $Home_, $BinDir | Out-Null

$env:UV_TOOL_DIR = Join-Path $Home_ 'uv-tools'
$env:UV_TOOL_BIN_DIR = $BinDir
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Home_ 'python'

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
$localUv = Join-Path $Home_ 'uv\uv.exe'
if (-not $uv -and (Test-Path $localUv)) { $uv = $localUv }

# the user PATH is read and written unexpanded (REG_EXPAND_SZ), so %USERPROFILE%-style entries survive
function Get-UserPath {
  $key = Get-Item -Path 'HKCU:\Environment'
  $key.GetValue('Path', '', 'DoNotExpandEnvironmentNames')
}
function Set-UserPath([string]$value) {
  Set-ItemProperty -Path 'HKCU:\Environment' -Name 'Path' -Value $value -Type ExpandString
  # tell other programs that the environment changed (new terminals pick it up)
  [Environment]::SetEnvironmentVariable('MDBINDERY_PATH_REFRESH', '1', 'User')
  [Environment]::SetEnvironmentVariable('MDBINDERY_PATH_REFRESH', $null, 'User')
}
function Invoke-Native([scriptblock]$block) {
  # Windows PowerShell 5.1 turns native stderr into errors under 'Stop'
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & $block 2>&1 | Out-Null } finally { $ErrorActionPreference = $old }
}

if ($Uninstall) {
  if ($uv) { Invoke-Native { & $uv tool uninstall mdbindery } }
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $BinDir 'mdbindery.exe')
  foreach ($d in 'tools', 'uv', 'uv-tools', 'python') {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $Home_ $d)
  }
  if (-not (Get-ChildItem $Home_ -Force -ErrorAction SilentlyContinue)) { Remove-Item -Force -ErrorAction SilentlyContinue $Home_ }
  $userPath = Get-UserPath
  if ($userPath -and (($userPath -split ';') -contains $BinDir) -and -not (Get-ChildItem $BinDir -ErrorAction SilentlyContinue)) {
    Set-UserPath (($userPath -split ';' | Where-Object { $_ -and $_ -ne $BinDir }) -join ';')
  }
  Write-Host "mdbindery removed from $Home_"
  return
}

if (-not $uv) {
  $asset, $sha = $UvAssets[$Arch]
  Write-Host "getting uv $UvVersion ($asset)"
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("mdbindery-" + [guid]::NewGuid())
  New-Item -ItemType Directory -Path $tmp | Out-Null
  $zip = Join-Path $tmp $asset
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/$asset" -OutFile $zip
  $got = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
  if ($got -ne $sha) { throw "checksum mismatch for $asset" }
  Expand-Archive -Path $zip -DestinationPath $tmp -Force
  New-Item -ItemType Directory -Force -Path (Split-Path $localUv) | Out-Null
  Copy-Item (Get-ChildItem -Path $tmp -Recurse -Filter uv.exe | Select-Object -First 1).FullName $localUv -Force
  Remove-Item -Recurse -Force $tmp
  $uv = $localUv
}

if ($Local) { $spec = (Resolve-Path $Local).Path } else { $spec = "mdbindery @ $Repo/archive/$Ref.zip" }
Write-Host "installing mdbindery from $(if ($Local) { $Local } else { "$Repo@$Ref" })"
$old = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$uvOut = & $uv tool install --force --python 3.12 $spec 2>&1
$uvCode = $LASTEXITCODE
$ErrorActionPreference = $old
if ($uvCode -ne 0) { $uvOut | ForEach-Object { Write-Host $_ }; throw 'uv could not install mdbindery' }
$mdb = Join-Path $BinDir 'mdbindery.exe'
if (-not (Test-Path $mdb)) { throw "mdbindery was not installed into $BinDir" }

$userPath = Get-UserPath
if (-not $userPath) { $userPath = '' }
if (($userPath -split ';') -notcontains $BinDir) {
  Set-UserPath ((@($userPath.TrimEnd(';')) + $BinDir | Where-Object { $_ }) -join ';')
  Write-Host "added $BinDir to your user PATH (open a new terminal to use it)"
}
$env:Path = "$BinDir;$env:Path"

if (-not $NoTools) {
  $toolArgs = @('install-tools', '--java', $Java)
  if ($NoNode) { $toolArgs += '--no-node' }
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  & $mdb @toolArgs
  $code = $LASTEXITCODE
  $ErrorActionPreference = $old
  if ($code -ne 0) { throw 'mdbindery install-tools failed' }
}
if ($Home_ -ne $DefaultHome) {
  Write-Host ''
  Write-Host "the tools are in $Home_; mdbindery finds them only with MDBINDERY_HOME set, e.g.:"
  Write-Host "  [Environment]::SetEnvironmentVariable('MDBINDERY_HOME', '$Home_', 'User')"
}
Write-Host ''
Write-Host "done: run 'mdbindery doctor' to confirm, then 'mdbindery check <book-folder-or-repo-url>'"
