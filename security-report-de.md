# Codex Security Report

## Deutsche Fassung

**Scan-ID:** `0907d45e-324f-4275-b9f8-1950108f4f3d`  
**Scan-Typ:** Standard Security Scan  
**Ziel:** `Benchmarks`  
**Revision:** `52adeba68549f918cfa7305ff52e3ba9849adef5`  
**Status:** Abgeschlossen  
**Abgeschlossen am:** 17. August 2026, 13:53:15 UTC  
**Ergebnis:** 2 meldepflichtige Befunde: 1 hoch, 1 mittel

## Zusammenfassung

Der Scan war ein repositoryweiter statischer Quelltext-Audit des aktuellen Benchmarks-Worktrees. 
Geprüft wurden insbesondere ausführbarer Python-Code, der optionale lokale LM-Eval-HTTP-Proxy, Prozessgrenzen, Konfigurationslader, Registry-Pflege, Tests und CI-Konfiguration.

Es wurden zwei meldepflichtige Sicherheitsbefunde festgestellt:

| Schweregrad | Befund                                                                                      | Regel                                        | CWE              |
|-------------|---------------------------------------------------------------------------------------------|----------------------------------------------|------------------|
| Hoch        | Vom Modell erzeugtes Python kann aus der eingeschränkten Sandbox ausbrechen                 | `sandbox-escape.model-generated-python`      | CWE-94, CWE-693  |
| Mittel      | Konfigurierbares Proxy-Binding kann nicht authentifizierte LM-Studio-Operationen offenlegen | `authorization.proxy-management-passthrough` | CWE-306, CWE-284 |

Die Bewertung basiert auf statischer Quelltextanalyse. Es wurden keine Laufzeit- oder Netzwerk-Exploitationstests durchgeführt. 
Die Abdeckung ist daher als **teilweise** einzustufen.

## Bedrohungsmodell

### Zu schützende Werte

- Das Dateisystem und die Prozessberechtigungen des lokalen Benchmark-Benutzers
- Lokale Model-Serving-Endpunkte und der Zustand geladener Modelle
- Benchmark-Ergebnisse und Model-Konfigurationsdateien
- GPU-/CPU-Ressourcen und die Verfügbarkeit der Dienste

### Angenommene Angreiferfähigkeiten

- Modell-Output bereitstellen oder beeinflussen, wenn ein Modell oder eine vorgelagerte Antwort nicht vertrauenswürdig oder kompromittiert ist
- Den Proxy über die konfigurierte Bind-Adresse erreichen, wenn er über Loopback hinaus gebunden wird
- Fehlerhafte Benchmark- oder API-Eingaben innerhalb des vorgesehenen lokalen Ausführungsablaufs bereitstellen

### Sicherheitsziele

- Verhindern, dass vom Modell oder Benchmark kontrollierter Code seine Ausführungsgrenze verlässt
- Autorisierung verlangen, bevor Inferenz- oder Modellverwaltungsoperationen offengelegt werden
- Unkontrollierten Ressourcenverbrauch verhindern und die Verfügbarkeit von Host und Diensten erhalten
- Lokale Konfiguration und Benchmark-Artefakte innerhalb ihrer vorgesehenen Vertrauensgrenzen halten

### Vertrauensgrenzen

- Modell-/API-Antworten, die in die Pipeline zur Codeextraktion und -ausführung gelangen
- HTTP-Clients, die den optionalen LM-Eval-Proxy erreichen
- Repository-Datensätze, YAML-/JSON-Konfigurationen und Umgebungsvariablen, die von den Tools verarbeitet werden
- Benchmark-Subprozesse sowie lokale LM-Studio-/TabbyAPI-Dienste

Ein lokaler Benchmark-Betreiber führt modellgesteuerte Auswertungen und einen optionalen LM-Eval-HTTP-Proxy gegen lokale LM-Studio- oder TabbyAPI-Dienste aus. 
Die Sicherheit hängt davon ab, dass vom Modell erzeugter Code eingeschlossen bleibt, lokale Modellverwaltungs-APIs privat bleiben und nicht vertrauenswürdige 
Repository- oder Konfigurationsdaten nicht unkontrolliert in Datei-, Prozess- oder Netzwerkoperationen gelangen.

## Befund 1: Hoher Schweregrad

### Vom Modell erzeugtes Python kann aus der eingeschränkten Sandbox ausbrechen

**Regel:** `sandbox-escape.model-generated-python`  
**CWE:** CWE-94, CWE-693  
**CVSS 3.1:** 8.1 (hoch)  
**Befund-ID:** `csf_d62fd893157d9ed8d5ccf4f9`

#### Beschreibung

Der Custom-Benchmark führt vom Modell erzeugtes Python in einem Subprozess mit einem gefilterten Builtins-Dictionary aus. 
Der ersetzte Import-Hook erlaubt jedoch alle Module, die nicht auf einer endlichen Sperrliste stehen, darunter `warnings`. 
Über dieses Modul kann der Code die echten Interpreter-Builtins wiedererlangen, Importe rekonstruieren und Operationen mit den Berechtigungen des Host-Benutzers ausführen.

#### Angriffspfad

```text
Model response -> extract_code() -> evaluate_code() -> _build_sandbox_script()
-> allow-by-default _safe_import() -> normal Python subprocess
```

Ein bösartiges oder kompromittiertes Modell beziehungsweise ein Angreifer, der die ausgewertete Aufgaben- oder Modellantwort kontrolliert, 
kann diesen Pfad erreichen, sobald die Antwort als Code akzeptiert wird. Die Auswirkung ist beliebige Codeausführung und Zugriff auf die Ressourcen, 
die dem Benchmark-Subprozess auf dem Host zur Verfügung stehen.

#### Belege

**Unvollständige Modulsperrliste** in [src/custom_benchmark.py](C:\Users\pskra\Python-Projekte\Benchmarks\src\custom_benchmark.py), Zeilen 1193–1200:

```python
_SANDBOX_BLOCKED_MODULES = frozenset({
    "subprocess", "shutil", "ctypes", "socket",
    "http", "urllib", "ftplib", "smtplib", "telnetlib",
    "multiprocessing", "threading", "webbrowser",
    "signal", "asyncio", "code", "codeop", "pdb",
    "traceback", "inspect", "antigravity", "tkinter",
    "platform", "sysconfig", "distutils",
})
```

Die Richtlinie ist eine endliche Denylist. Module außerhalb dieser Liste bleiben importierbar.

**Import-Hook mit Erlaubnisstandard** in `src/custom_benchmark.py`, Zeilen 1232–1239:

```python
def _safe_import(name, *args, **kwargs):
    top = name.split(".")[0]
    if top in _BLOCKED:
        raise ImportError(f"Module {name!r} is blocked")
    if _orig_imp is not None:
        return _orig_imp(name, *args, **kwargs)
    return __import__(name, *args, **kwargs)
_bd['__import__'] = _safe_import
```

Der Hook blockiert nur aufgelistete Top-Level-Module und delegiert jeden anderen Import an den Interpreter.

**Ausführung als normaler Host-Subprozess** in `src/custom_benchmark.py`, Zeilen 1300–1305:

```python
result = _subprocess.run(
    [sys.executable, tmppath],
    capture_output=True, text=True, timeout=timeout,
    encoding="utf-8", errors="replace",
    env={**_os.environ, "PYTHONIOENCODING": "utf-8"}
)
```

Das erzeugte Programm läuft als normaler Python-Subprozess mit der Umgebung des Host-Benutzers. Das Timeout ist keine Isolation auf Betriebssystemebene.

**Modellantwort zur Auswertung** in `src/custom_benchmark.py`, Zeilen 1809–1820:

```python
code = extract_code(response, is_structured=is_structured) if response else ""
if not code and response:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL)
    if m:
        code = m.group(1).strip()
struct = classify_output(code, response or "", is_structured, entry_point)
score, detail = evaluate_code(code, entry_point, tests_field, reference_code, setup_code=setup_code)
```

Die Modellantwort wird in ausführbaren Code umgewandelt und ohne Vertrauens- oder Richtlinienentscheidung an den Evaluator übergeben.

#### Ursache

Die Sandbox stützt sich auf einen Denylist-Import-Hook und Python-Namespace-Filterung statt auf eine Isolation auf Betriebssystemebene. 
Da der Hook Module außerhalb der Liste erlaubt, kann erzeugter Code über erlaubte Laufzeitmodule Interpreter-Funktionen wiederherstellen.

#### Bewertung und Unsicherheit

Der Befund ist mit hoher Sicherheit nachvollziehbar, weil sowohl die anfällige Kontrolle als auch der Ausführungssink direkt im Quelltext sichtbar sind. 
Die Pipeline ist standardmäßig lokal und die Modellquelle wird normalerweise vom Betreiber ausgewählt. Das Repository belegt daher keinen direkten Remote-Angreifer; der Befund bleibt jedoch für bösartige, kompromittierte oder extern gehostete Modelle relevant.

#### Empfehlung

Python-Namespace-Filterung sollte nicht als Sicherheits-Sandbox behandelt werden. Der erzeugte Code sollte in einem separat isolierten Worker ausgeführt werden, mit:

- Isolation durch Betriebssystem, Container oder Windows Job Object/Restricted Token
- minimaler Umgebung
- keinem Zugriff auf das Host-Dateisystem und Netzwerk
- expliziten Ressourcenlimits

Falls zusätzlich eine In-Process-Richtlinie bestehen bleibt, sollte sie eine strikte Allowlist unveränderlicher Operationen verwenden und nur als 
Korrektheitsfilter, nicht als Sicherheitsgrenze, betrachtet werden.

#### Empfohlene Tests

- Regressionstest, der belegt, dass erzeugter Code keine Fähigkeit importieren kann, mit der sich echte Builtins wiederherstellen oder Datei-, Prozess- und Netzwerk-APIs erreichen lassen.
- Windows-Integrationstest im gehärteten Worker, der den Zugriff auf Dateisystem, Prozesserzeugung, Netzwerk und Umgebung überprüft.
- Verifikation, dass Timeout-, Speicher-, CPU- und Kindprozesslimits außerhalb des Python-Interpreters durchgesetzt werden.

## Befund 2: Mittlerer Schweregrad

### Konfigurierbares Proxy-Binding kann nicht authentifizierte LM-Studio-Operationen offenlegen

**Regel:** `authorization.proxy-management-passthrough`  
**CWE:** CWE-306, CWE-284  
**CVSS 3.1:** 6.5 (mittel)  
**Befund-ID:** `csf_6674d496abb12b716fca6b61`

#### Beschreibung

Der optionale LM-Eval-Proxy akzeptiert eine beliebige Bind-Adresse, fügt keine Authentifizierung hinzu, leitet jeden POST-Pfad außerhalb 
von `/v1/chat/completions` an den konfigurierten Upstream weiter und sendet Wildcard-CORS-Header. 
Bei einer Bindung außerhalb von Loopback können dadurch lokale Inferenz- und Modellverwaltungsoperationen für nicht authentifizierte Netzwerk-Clients erreichbar werden.

#### Angriffspfad

```text
Network client -> ThreadingHTTPServer -> do_POST() -> arbitrary path branch
-> _proxy_upstream() -> local LM Studio/TabbyAPI endpoint
```

Der Angriff ist direkt erreichbar, wenn der Proxy über eine nicht lokale Schnittstelle veröffentlicht wird. Voraussetzung ist außerdem, 
dass der Upstream die weitergeleitete Anfrage ohne eigene Authentifizierung akzeptiert.

#### Belege

**Vom Betreiber wählbarer Listener** in [src/tools/lmeval_proxy.py](C:\Users\pskra\Python-Projekte\Benchmarks\src\tools\lmeval_proxy.py), Zeilen 185–199:

```python
parser.add_argument("--bind", type=str, default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
args = parser.parse_args()
ProxyHandler.upstream = args.upstream
server = ThreadingHTTPServer((args.bind, args.port), ProxyHandler)
```

Der Standardwert ist Loopback, aber die Anwendung erzwingt keine Loopback-Bindung.

**Nicht authentifizierte Weiterleitung beliebiger POSTs** in `src/tools/lmeval_proxy.py`, Zeilen 88–98:

```python
def do_POST(self) -> None:
    parsed = urlparse(self.path)
    path = parsed.path
    body = self._get_body()
    if path == "/v1/chat/completions":
        self._handle_chat_completion(body)
    else:
        status, resp_headers, resp_body = _proxy_upstream(self.upstream, path, dict(self.headers), body)
        self._send_response(status, resp_headers, resp_body)
```

Jeder andere POST-Pfad wird ohne Autorisierungsprüfung oder Pfad-Allowlist weitergeleitet.

**Sensible Upstream-Operationen** in [src/model_manager.py](C:\Users\pskra\Python-Projekte\Benchmarks\src\model_manager.py), Zeilen 671–693:

```python
result = _rest_request("/api/v1/models/load", method="POST", data=payload,
                      timeout=TIMEOUT_LOAD_MODEL)
```

Der lokale Upstream stellt Modell-Lifecycle-Operationen unter POST-Pfaden bereit, die der Proxy weiterleitet.

**Wildcard-Browserzugriff** in `src/tools/lmeval_proxy.py`, Zeilen 175–180:

```python
self.send_header("Access-Control-Allow-Origin", "*")
```

Der Proxy erlaubt damit ausdrücklich den Zugriff von jeder Browser-Origin auf Antworten.

#### Ursache

Der Proxy behandelt die Wahl der Schnittstelle als Verantwortung des Betreibers, koppelt eine nicht lokale Bindung aber nicht an Authentifizierung, 
eine Pfad-Allowlist oder eine geschützte Upstream-Verbindung.

#### Bewertung und Unsicherheit

Die fehlende Proxy-Kontrolle und die beliebige POST-Weiterleitung sind direkt im Quelltext erkennbar. Die tatsächliche Auswirkung hängt jedoch von der 
Authentifizierung des Upstream-Dienstes und der gewählten Deployment-Bind-Adresse ab.

Der Standardwert ist `127.0.0.1`, und `run_benchmarks.py` startet den Proxy ohne Überschreiben dieses Werts. Ein Upstream, der selbst Authentifizierung verlangt, 
würde die Auswirkung ebenfalls reduzieren.

#### Empfehlung

- Den Listener standardmäßig ausschließlich an Loopback binden.
- Nicht lokale Bind-Adressen ablehnen, sofern nicht ausdrücklich ein Authentifizierungsmodus konfiguriert ist.
- Das Routing auf die zwei benötigten Endpunkte beschränken.
- Wildcard-CORS entfernen oder durch eine Allowlist ersetzen.
- Begrenzte `Content-Length`-Werte und Request-Timeouts erzwingen.
- Für alle modellverwaltungsfähigen Endpunkte authentifizierte Upstream-Aufrufe verlangen.

#### Empfohlene Tests

- `--bind`-Werte außerhalb von Loopback zurückweisen, solange keine Authentifizierung konfiguriert ist.
- Überprüfen, dass unbekannte POST-Pfade mit 404 beantwortet werden und den Upstream nie erreichen.
- Überprüfen, dass Anfragen ohne gültige Zugangsdaten vor der Weiterleitung abgewiesen werden.
- Überprüfen, dass zu große `Content-Length`-Werte vor dem Lesen des Request-Bodys abgewiesen werden.

## Abdeckung und Einschränkungen

### Geprüfte Bereiche

Geprüft wurden unter anderem:

- `src/custom_benchmark.py`
- `src/tools/lmeval_proxy.py`
- `src/model_manager.py`
- `src/run_benchmarks.py`
- `src/registry_tool.py`
- `src/benchmark_config.py`
- `src/assemble_blueprint.py`
- `src/evalplus_subset_eval.py`
- `src/consolidate_results.py`
- `src/csv_writer.py`
- `src/tools/parallel_ab.py`
- `src/tools/correlation_export.py`
- `src/tools/gguf_full_metadata_reader.py`
- `src/tools/tool_eval_bench_runner.py`
- `pyproject.toml`
- `.github/workflows/ci.yml`
- `.github/workflows/review.yml`

### Explizit ausgeschlossene Pfade

- `Archiv/**`: Legacy-Archivcode, nicht Teil der aktiven Laufzeitoberfläche
- `backups/**`: Sicherungskopien, kein aktiver Laufzeitcode
- `Doku-intern/**`: interne Notizen und generiertes Arbeitsmaterial
- `ergebnisse/**`: erzeugte Benchmark-Ausgaben und Datenartefakte
- `logs/**`: Laufzeitprotokolle
- `runs/**`: Lauf-Ausgaben und temporäre Daten

Zusätzlich wurden große Datensatz-, Binär-, Dokument- und Fixture-Bereiche nicht vollständig Zeile für Zeile geprüft, darunter 
`data/`, `ds1000_official/`, `human_eval/`, `human_eval_plus/`, `simple_evals/`, `tests/data/` und `tests/fixtures/`.

### Methodik

- Statische Quelltextprüfung durch den Codex Security Standard Scan
- Parent-geführte Validierung mit lokalem `ripgrep` und Ruff-Sicherheitsmusterprüfung
- Keine verfügbaren Delegations-Worker
- Keine Laufzeit- oder Netzwerkreproduktion

### Offene Fragen

1. Verlangt die eingesetzte LM-Studio- oder TabbyAPI-Instanz am Upstream-Endpunkt Authentifizierung?
2. Wird der optionale Proxy in Produktion oder in einem gemeinsam genutzten Labornetz absichtlich an eine nicht lokale Schnittstelle gebunden?

## Gesamtbewertung

Der wichtigste Befund ist die fehlende echte Prozess- oder Betriebssystemisolation für vom Modell erzeugten Python-Code. 
Dieser Pfad kann bei nicht vertrauenswürdigem Modell-Output zu Codeausführung mit den Berechtigungen des lokalen Benchmark-Benutzers führen und sollte vor einer Nutzung 
mit untrusted oder extern gehosteten Modellen priorisiert behoben werden.

Der Proxy-Befund ist deploymentabhängig. Im Standardbetrieb mit Loopback-Bindung ist die Reichweite begrenzt; bei einer nicht lokalen Bindung muss jedoch 
eine Authentifizierung und eine strikte Pfadkontrolle vorgeschaltet werden.

**Hinweis:** Dieser Bericht ist die deutsche Übersetzung der versiegelten Ergebnisse des Standard Security Scans. 
Die technische Evidenz, Dateipfade, Zeilennummern, Regeln, IDs und CWE-Klassifikationen wurden zur Nachvollziehbarkeit beibehalten.
