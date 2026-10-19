# Loki Branch Merge Script (Windows PowerShell)
# Integrates multiple branches with Loki content prioritization

$ErrorActionPreference = "Stop"

# Configuration
$TARGET_BRANCH = "main"
$BACKUP_BRANCH = "backup/before-unify-$(Get-Date -Format 'yyyy-MM-dd')"
$MERGE_BRANCH = "merge/unify-loki-main-$(Get-Date -Format 'yyyy-MM-dd')"
$REMOTE = "origin"
$PUSH_REMOTE = $true
$ARCHIVE_DIR = "archive/removed-by-merge-$(Get-Date -Format 'yyyy-MM-dd')"

# Branches to merge (Loki branch first)
$BRANCHES_TO_MERGE = @(
    "codex/loki-research-copilot-upgrade",
    "improve/next-level-strategy",
    "codex/dashboard-council-research",
    "codex/ci-reliability-and-portfolio-foundation",
    "codex/paper-risk-planner",
    "feature/live-paper-candles",
    "vercel-dashboard",
    "fix/vercel-compatibility",
    "cleanup/remove-duplicates"
)

Write-Host "=== Loki Branch Merge Script ===" -ForegroundColor Cyan
Write-Host "Target Branch: $TARGET_BRANCH"
Write-Host "Backup Branch: $BACKUP_BRANCH"
Write-Host "Merge Branch: $MERGE_BRANCH"
Write-Host ""

# Check if working tree is clean
$status = git status --porcelain
if ($status) {
    Write-Host "ERROR: Working tree not clean. Commit or stash changes first." -ForegroundColor Red
    git status --porcelain
    exit 1
}

Write-Host "Fetching latest from remote $REMOTE..." -ForegroundColor Yellow
git fetch $REMOTE --prune

Write-Host "Checking out target branch $TARGET_BRANCH and creating backup..." -ForegroundColor Yellow
git checkout "$REMOTE/$TARGET_BRANCH"
git checkout -b $BACKUP_BRANCH
git push $REMOTE $BACKUP_BRANCH

Write-Host "Creating merge working branch $MERGE_BRANCH..." -ForegroundColor Yellow
git checkout -b $MERGE_BRANCH "$REMOTE/$TARGET_BRANCH"

# Function to check if content contains Loki markers
function Contains-Loki {
    param([string]$filePath)
    
    if (-not (Test-Path $filePath)) {
        return $false
    }
    
    $content = Get-Content $filePath -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) {
        return $false
    }
    
    # Case-insensitive search for Loki markers
    return $content -match "(?i)loki|loki quantum terminal|loki_quantum"
}

# Merge function
function Merge-Branch {
    param([string]$branch)
    
    Write-Host ""
    Write-Host "---- Merging $branch into $MERGE_BRANCH ----" -ForegroundColor Yellow
    
    $mergeExit = 0
    try {
        git merge --no-commit --no-ff "$REMOTE/$branch" 2>&1 | Out-Null
    } catch {
        $mergeExit = 1
    }
    
    if ($mergeExit -eq 0) {
        git commit -m "Merge $branch into $MERGE_BRANCH (auto-merged)"
        Write-Host "Merged $branch cleanly." -ForegroundColor Green
        return
    }
    
    Write-Host "Merge had conflicts. Auto-resolving..." -ForegroundColor Yellow
    
    # Get conflicted files
    $conflictedFiles = git ls-files -u | ForEach-Object { ($_ -split '\s+')[3] } | Sort-Object -Unique
    
    if ([string]::IsNullOrEmpty($conflictedFiles)) {
        git commit -m "Merge $branch into $MERGE_BRANCH (no conflicted files)"
        return
    }
    
    foreach ($file in $conflictedFiles) {
        if ([string]::IsNullOrEmpty($file)) { continue }
        
        Write-Host "Resolving: $file"
        
        # Check if theirs contains Loki
        $theirsTmp = [System.IO.Path]::GetTempFileName()
        $oursTmp = [System.IO.Path]::GetTempFileName()
        
        $theirsHasLoki = $false
        $oursHasLoki = $false
        
        try {
            git show ":3:$file" | Out-File -FilePath $theirsTmp -Encoding UTF8 -ErrorAction SilentlyContinue
            if (Test-Path $theirsTmp) {
                $theirsHasLoki = Contains-Loki -filePath $theirsTmp
            }
        } catch {}
        
        try {
            git show ":2:$file" | Out-File -FilePath $oursTmp -Encoding UTF8 -ErrorAction SilentlyContinue
            if (Test-Path $oursTmp) {
                $oursHasLoki = Contains-Loki -filePath $oursTmp
            }
        } catch {}
        
        if ($theirsHasLoki) {
            Write-Host "  -> Incoming contains Loki marker; accepting theirs" -ForegroundColor Cyan
            git checkout --theirs -- $file
            git add $file
        } elseif ($oursHasLoki) {
            Write-Host "  -> Current contains Loki marker; keeping ours" -ForegroundColor Cyan
            git checkout --ours -- $file
            git add $file
        } else {
            Write-Host "  -> No Loki marker; preferring ours (current merge branch)"
            git checkout --ours -- $file
            git add $file
        }
        
        Remove-Item $theirsTmp -ErrorAction SilentlyContinue
        Remove-Item $oursTmp -ErrorAction SilentlyContinue
    }
    
    git commit -m "Merge $branch into $MERGE_BRANCH (auto-resolved conflicts preferring Loki)"
    Write-Host "Conflicts resolved and committed for $branch." -ForegroundColor Green
}

# Start merges
$first = $true
foreach ($branch in $BRANCHES_TO_MERGE) {
    if ($first) {
        Write-Host ""
        Write-Host "Merging first branch (Loki-first): $branch" -ForegroundColor Yellow
        
        $mergeExit = 0
        try {
            git merge --no-commit --no-ff "$REMOTE/$branch" 2>&1 | Out-Null
        } catch {
            $mergeExit = 1
        }
        
        if ($mergeExit -eq 0) {
            git commit -m "Merge $branch into $MERGE_BRANCH (initial Loki-first merge)"
            Write-Host "Merged $branch cleanly." -ForegroundColor Green
        } else {
            Write-Host "Initial merge had conflicts. Preferring incoming (theirs)..." -ForegroundColor Yellow
            $conflictedFiles = git ls-files -u | ForEach-Object { ($_ -split '\s+')[3] } | Sort-Object -Unique
            
            if ($conflictedFiles) {
                foreach ($file in $conflictedFiles) {
                    if ([string]::IsNullOrEmpty($file)) { continue }
                    Write-Host "  -> Accepting incoming for $file"
                    git checkout --theirs -- $file
                    git add $file
                }
            }
            git commit -m "Merge $branch into $MERGE_BRANCH (initial merge, incoming preferred)"
        }
        
        $first = $false
        continue
    }
    
    Merge-Branch -branch $branch
}

Write-Host ""
Write-Host "All merges complete." -ForegroundColor Green

# Archive legacy files
if (Test-Path $ARCHIVE_DIR) {
    Remove-Item $ARCHIVE_DIR -Recurse -Force
}
New-Item -ItemType Directory -Path $ARCHIVE_DIR -Force | Out-Null

$legacyFiles = git ls-files | Select-String -Pattern "legacy|old|backup|_backup|\.bak$" -CaseSensitive:$false

if ($legacyFiles) {
    Write-Host "Archiving $($legacyFiles.Count) legacy files..." -ForegroundColor Yellow
    foreach ($file in $legacyFiles) {
        $target = "$ARCHIVE_DIR/$file"
        $targetDir = Split-Path $target
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }
        git mv $file $target 2>&1 | Out-Null
    }
    git commit -m "Archive legacy/old/backup files to $ARCHIVE_DIR"
} else {
    Write-Host "No legacy files found."
}

# Push branch
if ($PUSH_REMOTE) {
    Write-Host "Pushing merge branch $MERGE_BRANCH to $REMOTE..." -ForegroundColor Yellow
    git push -u $REMOTE $MERGE_BRANCH
    Write-Host "Branch pushed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Create a PR manually from $MERGE_BRANCH -> $TARGET_BRANCH" -ForegroundColor Cyan
} else {
    Write-Host "PUSH_REMOTE is false - branch not pushed. Inspect locally: $MERGE_BRANCH"
}

Write-Host ""
Write-Host "=== Merge Script Completed ===" -ForegroundColor Green
Write-Host "Inspect branch $MERGE_BRANCH before merging to $TARGET_BRANCH"
