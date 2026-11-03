<#
.SYNOPSIS
    Bring-Schuld: aktualisiert den Submodul-Pointer im Projekt "automatisierter Benchmark-Abgleich".

.DESCRIPTION
    Nach jedem Commit auf main in diesem Repository wird der Submodul-Pointer im
    Verbraucherprojekt auf den neuen main-Stand gehoben und dort committet. Der Verbraucher
    muss nichts selbst nachziehen ("Hole-Schuld"); die Lieferung ("Bring-Schuld") liegt hier.

    Der Hook ist nie blockierend: Fehler werden protokolliert und der Commit laeuft weiter.
    Ein fehlendes Verbraucherprojekt, ein anderer Branch oder ein bereits aktueller Pointer
    fuehren zu keiner Aenderung.

    Pfad zum Verbraucherprojekt: Umgebungsvariable BENCHMARK_ABGLEICH_REPO, sonst der
    Standardpfad unterhalb des Benutzerverzeichnisses (plattformunabhaengig ueber $HOME).
#>
param ()

$ErrorActionPreference = 'Stop'

$defaultConsumer = Join-Path (Join-Path $HOME 'Python-Projekte') 'automatisierter Benchmark-Abgleich'
$consumerRepo = if ($env:BENCHMARK_ABGLEICH_REPO) { $env:BENCHMARK_ABGLEICH_REPO } else { $defaultConsumer }
$logFile = Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\benchmark-abgleich-submodule.log'
$submodulePath = 'external/benchmarks'

function Write-Log([string]$Message) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    try { Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8 } catch { }
}

try {
    $benchRoot = (git rev-parse --show-toplevel).Trim()
    $branch = (git -C $benchRoot branch --show-current).Trim()
    if ($branch -ne 'main') { Write-Log "uebersprungen: Branch '$branch'"; exit 0 }
    if (-not (Test-Path -LiteralPath (Join-Path $consumerRepo '.git'))) {
        Write-Log "uebersprungen: Verbraucherprojekt nicht gefunden: $consumerRepo"
        exit 0
    }

    Push-Location -LiteralPath $consumerRepo
    try {
        $oldPointer = (git rev-parse "HEAD:$submodulePath" 2>$null)
        if (-not $oldPointer) { Write-Log 'uebersprungen: Submodul ist im Verbraucher nicht eingetragen.'; exit 0 }

        git -c protocol.file.allow=always submodule update --remote $submodulePath | Out-Null
        $newPointer = (git -C $submodulePath rev-parse HEAD).Trim()

        if ($newPointer -eq $oldPointer.Trim()) { Write-Log 'Pointer bereits aktuell.'; exit 0 }

        git add $submodulePath
        git commit -m ("chore(submodule): Benchmarks-Stand auf {0} aktualisieren" -f $newPointer.Substring(0, 7)) `
            -m 'Bring-Schuld aus dem Benchmarks-Projekt: der Submodul-Pointer folgt dem dortigen main-Stand. Der Verbraucher laedt die gemeinsame Identitaets- und Inventarlogik aus dieser gepinnten Fassung.'
        Write-Log ("Pointer aktualisiert: {0} -> {1}" -f $oldPointer.Trim().Substring(0, 7), $newPointer.Substring(0, 7))
    }
    finally { Pop-Location }
}
catch {
    Write-Log ("Fehler: {0}" -f $_.Exception.Message)
}
exit 0
