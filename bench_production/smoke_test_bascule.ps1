# Smoke test pour la bascule par défaut Solr V2 + Typesense (2026-05-22)
#
# Stratégie :
# - PHASE pre  : capture snapshot des 3 modes AVANT la bascule
#     default  → actuellement Milvus
#     ?legacy=1 → param ignoré (même résultat que default)
#     ?ajax=1  → mode hybride explicite
# - PHASE post : capture snapshot des 3 modes APRÈS la bascule
#     default  → doit matcher pre.ajax (hybride devient défaut)
#     ?legacy=1 → doit matcher pre.default (rollback fonctionne)
#     ?ajax=1  → doit matcher post.default
#
# Usage :
#   .\smoke_test_bascule.ps1 -Phase pre
#   .\smoke_test_bascule.ps1 -Phase post -CompareWith pre
#
# Output : bench_production/smoke_test/<phase>_<timestamp>.json
#          + smoke_test_report.html (si comparaison demandée)

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("pre", "post")]
    [string]$Phase,

    [string]$CompareWith = $null,

    [string]$BaseUrl = "https://www.hellopro.fr/moteur_recherche/recherche_resultat.php",

    [string]$KeywordsFile = "C:\RIJA\CLAUDE_CODE\opti_moteur\RAG-HP-PUB\bench_production\smoke_keywords.txt"
)

# === Mots-clés du smoke test (24 audit v4 + cas critiques) ===
$DefaultKeywords = @(
    # Audit Hellopro v4 (24 mots-cles Elena)
    "armoire medicale",
    "soudure ritmo",
    "ritmo",
    "urinoir delabie",
    "melangeur conique",
    "e-crane",
    "lockers bagagerie",
    "barre laser a led",
    "fraiseuse",
    "perceuse colonne",
    "defibrillateur",
    "distributeur automatique",
    "compresseur",
    "nettoyage",
    "robot de nettoyage",
    "aspirateur",
    "bras aspirant",
    "erp",
    "rectifieuse cylindrique",
    "sennebogen",
    # Cas representatifs nouveaux (couverture toutes categories)
    "chambre froide",
    "tracteur agricole",
    "container maritime",
    "drone"
)

if (Test-Path $KeywordsFile) {
    $keywords = Get-Content $KeywordsFile | Where-Object { $_ -and -not $_.StartsWith("#") }
    Write-Host "Loaded $($keywords.Count) keywords from $KeywordsFile" -ForegroundColor Cyan
} else {
    $keywords = $DefaultKeywords
    Write-Host "Using $($keywords.Count) default keywords (no file at $KeywordsFile)" -ForegroundColor Yellow
}

# === Setup output ===
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$outDir = "C:\RIJA\CLAUDE_CODE\opti_moteur\RAG-HP-PUB\bench_production\smoke_test"
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}
$outFile = Join-Path $outDir "${Phase}_${timestamp}.json"

# === Modes à tester ===
$modes = @(
    @{ name = "default";   suffix = "" },
    @{ name = "legacy";    suffix = "&legacy=1" },
    @{ name = "ajax";      suffix = "&ajax=1" }
)

# === Helpers ===
function Get-HtmlMarkers {
    param([string]$html)
    $markers = @{}
    # Detection rapide : regime PHP (cf hp_decide_p1_regime)
    if ($html -match "HP_QUALITY_P1:\s*regime=(\w+)") {
        $markers["regime"] = $Matches[1]
    }
    # Detection : type backend utilise
    if ($html -match '<div style="display:none">###(.*?)</div>') {
        $rawJson = $Matches[1]
        if ($rawJson -like "*matches*produits_3*") {
            $markers["backend_signature"] = "milvus_rag"
        } elseif ($rawJson -like "*typesense*") {
            $markers["backend_signature"] = "typesense_hybrid"
        }
    }
    # Solr signature (page 1 hybride)
    if ($html -match 'data-mode="hybrid"') {
        $markers["render_mode"] = "hybrid"
    } elseif ($html -match 'data-mode="products"') {
        $markers["render_mode"] = "products"
    }
    # Nb produits affiches (heuristique : compter les cartouches)
    $cartouches = ([regex]::Matches($html, 'class="cartouche-produit')).Count
    $markers["nb_cartouches"] = $cartouches
    # Top product (premier h3 dans cartouche)
    if ($html -match 'class="cartouche-produit[^"]*"[^>]*>[\s\S]*?<h\d[^>]*>([^<]+)</h\d>') {
        $markers["top1_name"] = ($Matches[1] -replace '\s+', ' ').Trim()
    }
    return $markers
}

# === Run ===
$results = @()
$idx = 0
$total = $keywords.Count * $modes.Count

foreach ($kw in $keywords) {
    $encoded = [uri]::EscapeDataString($kw)
    $bust = [int](Get-Date -UFormat %s) + (Get-Random -Min 0 -Max 1000)

    foreach ($mode in $modes) {
        $idx++
        $url = "${BaseUrl}?type_recherche=produit&recherche_active=1&mot_cles=$encoded&_=$bust$($mode.suffix)"
        Write-Host "[$idx/$total] $($mode.name) : $kw" -ForegroundColor Cyan

        $result = [ordered]@{
            keyword = $kw
            mode    = $mode.name
            url     = $url
            ts      = (Get-Date).ToString("o")
        }

        try {
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15
            $sw.Stop()
            $result["http_status"] = [int]$resp.StatusCode
            $result["latency_ms"] = [int]$sw.ElapsedMilliseconds
            $result["html_bytes"] = $resp.Content.Length
            $markers = Get-HtmlMarkers -html $resp.Content
            foreach ($k in $markers.Keys) { $result[$k] = $markers[$k] }
            Write-Host "  OK $($result.latency_ms)ms regime=$($result.regime) cartouches=$($result.nb_cartouches) top1=$($result.top1_name)" -ForegroundColor Green
        } catch {
            $result["http_status"] = -1
            $result["latency_ms"] = -1
            $result["error"] = $_.Exception.Message
            Write-Host "  KO $($_.Exception.Message)" -ForegroundColor Red
        }
        $results += [PSCustomObject]$result
        Start-Sleep -Milliseconds 200
    }
}

# === Save snapshot ===
$results | ConvertTo-Json -Depth 5 | Out-File -FilePath $outFile -Encoding utf8
Write-Host "`nSnapshot saved : $outFile" -ForegroundColor Green
Write-Host "  $($results.Count) requests"

# === Comparison (si demande) ===
if ($CompareWith) {
    $compareGlob = Join-Path $outDir "${CompareWith}_*.json"
    $compareFile = Get-ChildItem $compareGlob | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $compareFile) {
        Write-Host "Aucun snapshot ${CompareWith}_*.json a comparer (cherche dans $outDir)" -ForegroundColor Yellow
        exit
    }
    Write-Host "`nComparaison vs $($compareFile.Name)..." -ForegroundColor Cyan
    $oldData = Get-Content $compareFile.FullName -Raw | ConvertFrom-Json

    # Critere : verifier les invariants
    #   1. pre.default ~= post.legacy (Milvus inchange via ?legacy=1)
    #   2. pre.ajax    ~= post.default (hybride devient default)
    $invariants = @(
        @{ name = "pre.default ~= post.legacy (rollback Milvus)";    old = "default"; new = "legacy" }
        @{ name = "pre.ajax    ~= post.default (hybride par defaut)"; old = "ajax";    new = "default" }
    )

    $reportLines = @("# Smoke test report — ${Phase} vs ${CompareWith}`n")
    $reportLines += "Generated : $(Get-Date)`n"

    foreach ($inv in $invariants) {
        $reportLines += "## $($inv.name)`n"
        $mismatch = 0
        $total = 0
        foreach ($kw in $keywords) {
            $oldRow = $oldData | Where-Object { $_.keyword -eq $kw -and $_.mode -eq $inv.old } | Select-Object -First 1
            $newRow = $results | Where-Object { $_.keyword -eq $kw -and $_.mode -eq $inv.new } | Select-Object -First 1
            $total++
            if (-not $oldRow -or -not $newRow) {
                $reportLines += "- ?? **$kw** : pas de match"
                $mismatch++
                continue
            }
            if ($oldRow.top1_name -ne $newRow.top1_name) {
                $reportLines += "- !! **$kw** : top1 differe '$($oldRow.top1_name)' vs '$($newRow.top1_name)'"
                $mismatch++
            } else {
                $reportLines += "- OK **$kw** : top1 stable"
            }
        }
        $reportLines += "`n→ $mismatch / $total écarts`n"
    }

    $reportFile = Join-Path $outDir "smoke_report_${timestamp}.md"
    $reportLines -join "`n" | Out-File -FilePath $reportFile -Encoding utf8
    Write-Host "Rapport : $reportFile" -ForegroundColor Green
}
