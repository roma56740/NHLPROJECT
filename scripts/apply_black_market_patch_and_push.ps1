<#
.SYNOPSIS
    Применяет патч BLACK MARKET к локальному клону приватного репозитория
    roma56740/TESTBOTEL и пушит изменения в main.

.DESCRIPTION
    Это ДЕСТРУКТИВНЫЙ и ВИДИМЫЙ ДРУГИМ скрипт (прямой push в main приватного
    репозитория) — он НЕ выполняется автоматически никаким AI-агентом и требует,
    чтобы вы явно запустили его сами, имея настроенный доступ к репозиторию
    (git credentials / SSH-ключ / GitHub CLI `gh auth login`).

    Скрипт:
      1. Клонирует roma56740/TESTBOTEL в -RepoPath, если его там ещё нет
         (иначе использует существующий локальный клон).
      2. Проверяет, что рабочее дерево чистое (нет незакоммиченных изменений) —
         если нет, останавливается, чтобы не потерять ваши локальные правки.
      3. Переключается на -Branch (по умолчанию main) и подтягивает свежий origin.
      4. Распаковывает -PatchZip поверх рабочего дерева (перезаписывает только
         файлы, входящие в патч — остальной репозиторий не трогает).
      5. Показывает `git status` и `git diff --stat` для ручной проверки.
      6. Требует явного подтверждения (ввод "PUSH") перед коммитом и push —
         без него скрипт останавливается на этапе предпросмотра.
      7. Коммитит и пушит в -Branch на origin.

.PARAMETER RepoPath
    Локальный путь, где будет находиться клон репозитория (создаётся, если не существует).

.PARAMETER PatchZip
    Путь к ZIP-архиву патча (см. BLACK_MARKET_PATCH.zip из отчёта аудита).

.PARAMETER RemoteUrl
    URL репозитория. По умолчанию https — для SSH передайте git@github.com:roma56740/TESTBOTEL.git.

.PARAMETER Branch
    Целевая ветка. По умолчанию main.

.PARAMETER CommitMessage
    Сообщение коммита.

.EXAMPLE
    .\apply_black_market_patch_and_push.ps1 `
        -RepoPath "C:\repos\TESTBOTEL" `
        -PatchZip "C:\Users\Eric\Downloads\BLACK_MARKET_PATCH.zip"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoPath,

    [Parameter(Mandatory = $true)]
    [string]$PatchZip,

    [string]$RemoteUrl = "https://github.com/roma56740/TESTBOTEL.git",

    [string]$Branch = "main",

    [string]$CommitMessage = "Add Black Market: personal daily rotation shop (audit + fixes)"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PatchZip)) {
    Write-Error "Patch ZIP not found: $PatchZip"
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "git не найден в PATH. Установите Git for Windows и повторите."
    exit 1
}

if (Test-Path (Join-Path $RepoPath ".git")) {
    Write-Host "Использую существующий локальный клон: $RepoPath" -ForegroundColor Cyan
    Set-Location $RepoPath
    git fetch origin
    if ($?) { } else { Write-Error "git fetch не удался — проверьте доступ к репозиторию."; exit 1 }
} else {
    Write-Host "Клонирую $RemoteUrl в $RepoPath ..." -ForegroundColor Cyan
    git clone $RemoteUrl $RepoPath
    if (-not $?) { Write-Error "git clone не удался — проверьте URL и доступ (private repo требует auth)."; exit 1 }
    Set-Location $RepoPath
}

$dirty = git status --porcelain
if ($dirty) {
    Write-Error "Рабочее дерево не чистое — есть незакоммиченные изменения. Закоммитьте/застэшьте их вручную и повторите, чтобы патч случайно не смешался с вашей работой:`n$dirty"
    exit 1
}

git checkout $Branch
if (-not $?) { Write-Error "Не удалось переключиться на ветку $Branch."; exit 1 }

git pull origin $Branch
if (-not $?) { Write-Error "git pull не удался."; exit 1 }

Write-Host "Распаковываю патч поверх рабочего дерева..." -ForegroundColor Cyan
Expand-Archive -Path $PatchZip -DestinationPath $RepoPath -Force

Write-Host "`n=== git status после применения патча ===" -ForegroundColor Yellow
git status

Write-Host "`n=== git diff --stat ===" -ForegroundColor Yellow
git diff --stat

Write-Host "`nПроверьте изменения выше. Это ПРЯМОЙ PUSH В MAIN приватного репозитория roma56740/TESTBOTEL." -ForegroundColor Red
$confirmation = Read-Host "Введите PUSH заглавными буквами, чтобы закоммитить и запушить, либо любой другой ввод для отмены"

if ($confirmation -ne "PUSH") {
    Write-Host "Отменено пользователем. Изменения остались в рабочем дереве незакоммиченными — можно проверить `git diff` вручную." -ForegroundColor Yellow
    exit 0
}

git add -A
git commit -m $CommitMessage
if (-not $?) { Write-Error "git commit не удался (возможно, нечего коммитить)."; exit 1 }

git push origin $Branch
if (-not $?) {
    Write-Error "git push не удался — проверьте права доступа/токен. Коммит остался локально, ничего не потеряно."
    exit 1
}

Write-Host "`nГотово: изменения запушены в $RemoteUrl ($Branch)." -ForegroundColor Green
Write-Host "Не забудьте задать BLACK_MARKET_SEED_SECRET в Railway Variables перед следующим деплоем (см. RAILWAY_ENV_VARS_BLACK_MARKET.md)." -ForegroundColor Yellow
