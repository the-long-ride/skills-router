# Skills Router

[![Version](https://img.shields.io/badge/version-v0.0.2-orange.svg)](../CHANGELOG.md)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](../LICENSE)
[![Author](https://img.shields.io/badge/author-the--long--ride-green.svg)](https://github.com/the-long-ride)
[![Build Status](https://img.shields.io/badge/tests-199%20passed-success.svg)](../tests/)

[English](../README.md) | [Español](es.md) | [简体中文](zh.md) | [日本語](ja.md) | [Deutsch](de.md) | [Français](fr.md)

`skills-router` ist der CLI-Befehl und der Name des PyPI-Pakets. Das npm-Wrapper-Paket
ist [`@the-long-ride/skills-router`](https://www.npmjs.com/package/@the-long-ride/skills-router).

**Skills Router ist ein AI-Agent-Skillset-Manager.** Er überprüft, registriert,
entdeckt, indiziert, vergleicht und leitet AI-Agent-Skills/-Plugins weiter, damit ein Host-Agent
die richtige Fähigkeit nutzen kann, ohne stillschweigend Paketressourcen zu übernehmen.

Skills Router ist kein allgemeiner Paketmanager. Er besitzt Metadaten, Entscheidungen, Audit-Protokolle
und den Routing-Status. Paketdateien, virtuelle Umgebungen, IDE-Erweiterungen und Skill-Verzeichnisse des
Host-Agents verbleiben im Besitz des Tools, das sie installiert hat.

## Warum skills-router?

AI-Agent-Skills sind nützlich, aber sie verteilen sich auf CLIs, IDEs, MCP-Server, globale Ordner,
Workspace-Ordner und hostspezifische Paketmanager. Das macht es schwierig, einfache Fragen zu beantworten:
Welchen Skill sollte dieser Agent verwenden, wer hat ihn genehmigt, wo ist er aktiv und was passiert,
wenn sich ein anderes Paket damit überschneidet?

`skills-router` bietet Agenten eine gemeinsame Steuerungsebene für dieses Problem. Es ermöglicht Ihnen,
Skills einmal zu installieren oder zu entdecken, sie durch Vertrauens- und Verhaltensprüfungen zu überprüfen
und jeden Agenten an die richtige Fähigkeit weiterzuleiten, ohne Paketdateien zu kopieren oder riesige
Routingtabellen in Prompts zu packen. Der Paketmanager besitzt weiterhin die Paketressourcen;
Skills Router besitzt die Entscheidungen, Metadaten, das Audit-Protokoll und die Routing-Ebene.

## Was es tut

- Überprüft vollständige Skill-/Plugin-Manifeste durch Vertrauens-, Abhängigkeits-, semantische, Fähigkeits- und Integritätsprüfungen.
- Speichert genehmigte Paket-Metadaten in einem Gehirn-Index.
- Schreibt `skills-router.json`-Regeln, die Host-Agenten über MCP oder CLI abfragen können.
- Installiert einen Skill einmal für alle konfigurierten Host-Agenten mit `--all-agents` oder `/skills-router install <package> for all agents`.
- Unterstützt eingeschränkte All-Agent-Installationen mit Ziellisten wie `--agent-target codex,cursor`.
- Erzwingt zielbewusstes Routing, wenn Agenten `route_task` oder `skills-router route --target <agent>` aufrufen.
- Unterstützt das Standard-Set von Agenten-Hosts: `antigravity`, `antigravity-cli`, `antigravity-ide`, `codex`, `claude`, `hermes-agent`, `opencode`, `cline`, `cursor` und `windsurf`.
- Behandelt Teilinstallationen als selektive Routenaktivierung, nicht als partielle Paketextraktion.
- Entfernt von Skills Router besessene Metadaten/Routing bei der Deinstallation und indiziert die verbleibende Routenoberfläche neu.
- Gleicht Routen mit `/skills-router index` ab.
- Entdeckt extern installierte Workspace- oder globale Skills mit `/skills-router refine`.
- Scannt gemeinsame und hostspezifische Workspace- und globale Skill-Verzeichnisse, einschließlich verschachtelter System-Skill-Ordner.
- Behält neu entdeckte externe Routen auf `needs_selection`, bis der Mensch die Aktivierung bestätigt.
- Veröffentlicht Release-Beschreibungen aus dem entsprechenden Abschnitt der `CHANGELOG.md` bei Tag-Pushes, wobei Paketlinks von der CI angehängt werden.

## Was es nicht tut

- Es löscht keine Dateien im Besitz des Pakets, Repositories, virtuellen Umgebungen oder IDE-/Plugin-Ressourcen.
- Es ersetzt nicht `pip`, `npm`, IDE-Erweiterungsmanager oder die Plugin-Manager von Host-Agenten.
- Es genehmigt Vertrauenswarnungen, Abhängigkeitskonflikte, doppelte Routen oder unbekanntes Verhalten nicht automatisch, es sei denn, der Mensch stimmt dem Risiko explizit zu.
- Es fügt keine großen Routingtabellen in Agenten-Prompts ein. Agenten sollten Skills Router dynamisch abfragen.

## Architektur

```mermaid
flowchart LR
    Human[Mensch] --> Host[AI-Agent-Host]
    Host --> Bridge[Agenten-Brücke]
    Host --> MCP[MCP-stdio-Server]
    Host --> CLI[CLI]

    Bridge --> Parser[Slash-Parser]
    Parser --> Executor[Brücken-Executor]
    MCP --> Executor
    CLI --> Commands[Strikte Befehle]

    Commands --> Install[Installations-Pipeline]
    Executor --> Install
    Commands --> Reconcile[Indizieren und verfeinern]
    Executor --> Reconcile
    Commands --> Lookup[Routensuche]
    Executor --> Lookup
    Commands --> Remove[Metadaten deinstallieren]
    Executor --> Remove

    Install --> Resolver[Registry-Resolver]
    Resolver --> Trust[Vertrauensprüfung]
    Trust --> Deps[Abhängigkeits-Resolver]
    Deps --> Semantic[Semantischer Evaluator]
    Semantic --> Capability[Fähigkeitsprüfung]
    Capability --> WG[Workspace/Globaler Prompt]
    WG --> Health[Integritätsprüfung]

    Reconcile --> Discovery[Skill-Entdeckung]
    Discovery --> SkillDirs[Workspace/Globale Skill-Verzeichnisse]
    Discovery --> GlobalIndex[Globaler Skills Router Index]
    Reconcile --> Conflict[Konfliktdetektor]

    Install --> Store[(Gehirn-Index)]
    Reconcile --> Store
    Conflict --> Routes[(skills-router.json)]
    Lookup --> Routes
    Remove --> Store
    Remove --> Routes
    Remove --> Lock
    Remove --> Audit
    Install --> Lock[(Sperrdatei)]
    Install --> Audit[(Audit-Protokoll)]
```

## Kern-Workflow

```mermaid
flowchart TD
    A[Mensch bittet AI-Agenten] --> B{Form der Anfrage}
    B -->|/skills-router install pkg for me| C[Slash-Anfrage parsen]
    B -->|Strukturierter MCP-Aufruf| D[MCP-Tool aufrufen]
    B -->|Strikte CLI| E[Befehl ausführen]

    C --> F[Paket oder Manifest auflösen]
    D --> F
    E --> F
    F --> G[Vertrauens- und Abhängigkeitsprüfungen]
    G -->|Harte Ablehnung| H[Stoppen und zusammenfassen]
    G -->|Prüfung erforderlich| I[Mensch fragen]
    I -->|Abbrechen| H
    I -->|Genehmigen| J[Semantischer und Fähigkeitsvergleich]
    G -->|Sicher| J
    J -->|Überschneidung| K[Routenwahl empfehlen]
    K --> L[Mensch wählt Routing]
    J -->|Kein Konflikt| M[Metadaten persistieren]
    L --> M
    M --> N[Routing und Sperrdatei schreiben]
    N --> O[Integritätsprüfung]
    O -->|Fehlgeschlagen| P[Skills Router Status bereinigen]
    O -->|Erfolgreich| Q[Audit und kurze Zusammenfassung]

    R[Host-Paketmanager ändert Dateien] --> S["/skills-router index"]
    T[Externer Skill erscheint] --> U["/skills-router refine"]
    S --> V[Routen aktualisieren und als veraltet markieren]
    U --> W[Metadaten entdecken und importieren]
    V --> X[Routenentscheidungen empfehlen]
    W --> X
```

## Installation

```bash
# Core local install
pip install -e .

# Optional real embedding support
pip install -e ".[ml]"

# Optional pgvector backend
pip install -e ".[pgvector]"

# Run through npm/npx
npx @the-long-ride/skills-router --help
```

Das Standard-Speicher-Backend ist ein JSON-basierter lokaler Speicher unter
`~/.skills-router`. Ein lokaler Node-Wrapper ist in `skills-router-npx/` für
`npx`- und IDE-Workflows verfügbar; siehe [GUIDELINE.md](../GUIDELINE.md).

## Schnellstart

```bash
# Review and register a local manifest
skills-router install examples/sample_manifests/weather_tool.json --scope global

# Review and register by registry package name
skills-router install writer-pack --package-type skillset --scope workspace:codex-local

# Install once and make routes visible to all configured AI-agent hosts
skills-router install writer-pack --package-type skillset --all-agents --json

# Install once but expose routes only to selected agent hosts
skills-router install writer-pack --package-type skillset --all-agents --agent-target codex,cursor --json

# Install the full package but leave routes inactive until selection
skills-router install writer-pack --package-type skillset --routing-mode selective_routes --scope workspace:codex-local --json

# Preview review decisions without writing state
skills-router install writer-pack --dry-run --explain --json

# Remove Skills Router metadata/routing only
skills-router uninstall writer-pack --json

# Reconcile already indexed packages and routes
skills-router index --json

# Discover workspace/global host-agent skills and refine routes
skills-router refine --json
skills-router refine writer-pack engram --json
skills-router refine --workspace-scope workspace:codex-local --json

# Ask Skills Router which route matches a task for the current host
skills-router route "draft article about release notes" --scope workspace:codex-local --target codex --json

# Let an AI-agent host execute a human slash request
skills-router chat "/skills-router install writer-pack for me" --target codex --agent-id codex-local --json
skills-router chat "/skills-router install writer-pack for all installed agents" --target codex --agent-id codex-local --json
skills-router chat "/skills-router refine writer-pack engram" --target codex --agent-id codex-local --json

# Expose Skills Router through stdio JSON-RPC
skills-router mcp

# Render bridge instructions for a host
skills-router prompt --target codex
skills-router prompt --list
```

## Befehlsschnittstelle

| Befehl | Zweck |
| :--- | :--- |
| `install <manifest-or-package>` | Ein Paket auflösen, überprüfen, registrieren und routen. |
| `index` | Indizierte Vektoren/Routen neu erstellen und Konflikte oder veraltete Routen erkennen. |
| `refine [skillset ...]` | Externe Skills entdecken, Metadaten importieren und Routen abgleichen. |
| `route <task>` | Aktive oder prüfungsbedürftige Routen für eine Aufgabe abfragen. |
| `uninstall <tool_id>` | Nur von Skills Router besessene Metadaten/Routing entfernen. |
| `list` | Indizierte Tools auflisten. |
| `inspect <tool_id>` | Einen Gehirn-Index-Eintrag ausgeben. |
| `audit` | Audit-Ereignisse abfragen. |
| `watch` | Registry Watch einmal oder als Daemon ausführen. |
| `prompt` | Host-spezifische Brücken-Anweisungen rendern. |
| `chat` | Chat-förmige `/skills-router`-Anfragen parsen und ausführen. |
| `mcp` | Den lokalen stdio JSON-RPC-Tool-Server ausführen. |

## Einmalige Installationen für alle Agenten

All-Agent-Installationen sind der wichtigste v0.0.2-Workflow:

```bash
skills-router install writer-pack --package-type skillset --all-agents --json
```

Das Paket wird weiterhin einmal in Skills Router registriert. Die generierten
Routen sind global, und jeder konfigurierte Host erreicht sie über MCP oder die CLI-Brücke.
Skills Router besitzt nur Metadaten und Routing; Paketressourcen verbleiben im Besitz
des Host-Paketmanagers oder des Skill-Installers.

Standard-All-Agent-Ziele:

```text
antigravity, antigravity-cli, antigravity-ide, codex, claude,
hermes-agent, opencode, cline, cursor, windsurf
```

Verwenden Sie `--agent-target`, wenn ein Skill nur für einen Teil dieses Sets gelten soll:

```bash
skills-router install writer-pack \
  --package-type skillset \
  --all-agents \
  --agent-target codex,cursor \
  --json
```

Wenn eine Zielliste gespeichert ist, respektiert die Routensuche diese nur, wenn der Aufrufer den aktuellen Host identifiziert:

```bash
skills-router route "draft release notes" --target codex --json
skills-router route "draft release notes" --target cursor --json
```

Für Chat-förmige Anfragen können Agenten Folgendes verwenden:

```text
/skills-router install <package> for all installed agents
```

## Routing-Modell

Skills Router trennt die Paketpräsenz von der Agentenaktivierung:

- **Paketpräsenz:** Der Host-Paketmanager installiert oder aktualisiert das vollständige Paket.
- **Gehirn-Index:** Skills Router speichert Manifest-, Vertrauens-, Abhängigkeits-, Vektor-, Verhaltens- und Scope-Metadaten.
- **Routing:** Skills Router schreibt `skills-router.json`-Pakete und -Regeln.
- **Auswahl:** Routenkonflikte und extern entdeckte Skills verwenden `needs_selection`, bis der Mensch die Aktivierung bestätigt.
- **Suche:** Agenten rufen MCP `route_task` oder `skills-router route` mit ihrem Ziel auf, anstatt Routendateien direkt zu lesen.
- **Veraltete Routen:** `index` markiert fehlende Pakete als `missing_from_index`; es löscht keine Paketdateien.

## Verfeinerung und Entdeckung

`skills-router refine` schließt die Lücke, in der ein Mensch Skills außerhalb des Workspaces installiert,
beispielsweise über `npx`, einen Host-Agent-Skill-Installer oder ein globales Codex-Skill-Verzeichnis.

Entdeckungsquellen:

- Workspace-Skill-Verzeichnisse: `.agents/skills` plus hostspezifische Verzeichnisse wie `.codex/skills`, `.claude/skills`, `.cline/skills`, `.cursor/skills`, `.windsurf/skills`, `.opencode/skills`, `.agent/skills`, `.antigravity/skills`, `.hermes/skills` und `.kiro/skills`
- Globale Skill-Verzeichnisse: `$CODEX_HOME/skills`, `~/.codex/skills` und die entsprechenden hostspezifischen globalen Skill-Verzeichnisse
- Verschachtelte Skill-Ordner, einschließlich `.system/.../SKILL.md`
- Globaler Skills Router Status aus `global_data_dir`

Ein leeres Refine entdeckt alle sichtbaren installierten Skills. Ein benanntes Refine entdeckt und meldet nur übereinstimmende Skillsets, während es sie mit der sichtbaren Routenoberfläche vergleicht. Chat-förmiges `/skills-router refine` weist im Workspace entdeckte Routen `workspace:<agent-id>` zu, vergleicht sie aber dennoch mit allen sichtbaren Scopes.

## Slash-Befehle für Agenten

Die Agenten-Brücke akzeptiert natürliche menschliche Anfragen und wandelt sie in strikte Operationen um:

```text
/skills-router install <package> for me
/skills-router install <package> for all agents
/skills-router install <package> globally dry run
/skills-router install <package> skillset only needed skills for me
/skills-router uninstall <tool_id>
/skills-router index
/skills-router refine
/skills-router refine <skillset> <skillset>
/skills-router route <task>
/skills-router list
/skills-router inspect <tool_id>
/skills-router audit --tool <tool_id>
/skills-router watch --once
```

Die Brücke setzt den Installationsbereich standardmäßig auf `workspace:<agent-id>`, es sei denn, der Mensch sagt global. `for all agents` bedeutet eine globale Installation für das Standard-All-Agent-Zielset; benutzerdefinierte `--agent-target`-Listen werden durch zielbewusstes Routing erzwungen. Der Parser entfernt Füllwörter wie `for me` und gibt `human_summary` für kurze Agentenantworten zurück.

## MCP-Tool-Schnittstelle

`skills-router mcp` macht Folgendes verfügbar:

- `get_agent_prompt`
- `parse_slash_command`
- `run_slash_command`
- `install_tool`
- `uninstall_tool`
- `index_routes`
- `refine_routes`
- `route_task`
- `list_tools`
- `inspect_tool`
- `watch_once`

Verwenden Sie `run_slash_command` für menschlichen Chattext. Verwenden Sie die strukturierten Tools nur, wenn der Host bereits über bereinigte Argumente verfügt. Der MCP `content`-Text ist absichtlich kompakt; vollständige maschinenlesbare Daten verbleiben in `structuredContent`.

Strukturierte MCP-Installationsaufrufe können `all_agents: true` und optional `target_agents` übergeben. Strukturierte Routenaufrufe können `target` übergeben, sodass gespeicherte Ziellisten für den aufrufenden Host erzwungen werden.

## Unterstützte Agenten-Hosts

| Ziel | Speicherorte der Anweisungen |
| :--- | :--- |
| `antigravity` | `.agent/rules/skills-router.md`, `AGENTS.md` |
| `antigravity-cli` | `.agent/rules/skills-router.md`, `AGENTS.md` |
| `antigravity-ide` | `.agent/rules/skills-router.md`, `.antigravity/rules/skills-router.md`, `AGENTS.md` |
| `codex` | `AGENTS.md` |
| `cline` | `.clinerules/skills-router.md`, `AGENTS.md` |
| `cursor` | `.cursor/rules/skills-router.md`, `AGENTS.md` |
| `kiro` | `.kiro/steering/skills-router.md`, `AGENTS.md` |
| `claude` | `CLAUDE.md`, `.claude/commands/skills-router.md` |
| `github-copilot` | `.github/copilot-instructions.md`, `AGENTS.md` |
| `opencode` | `AGENTS.md`, `.opencode/agent/skills-router.md` |
| `hermes-agent` | `SOUL.md`, `AGENTS.md` |
| `windsurf` | `.windsurf/rules/skills-router.md`, `AGENTS.md` |

Rendern Sie zielspezifischen Brückentext mit:

```bash
skills-router prompt --target codex
skills-router prompt --target cursor
skills-router prompt --target windsurf
skills-router prompt --target codex --detail full
```

Der Standard-Prompt ist kompakt, damit persistente Agenten-Anweisungen weniger Token kosten. Verwenden Sie `--detail full` nur beim Generieren von Dokumenten oder beim Debuggen einer Integration.

## Konfiguration

`~/.skills-router/config.json` kann `SkillsRouterConfig`-Felder überschreiben, wie zum Beispiel:

```json
{
  "storage_backend": "memory",
  "workspace_root": "/path/to/workspace",
  "workspace_skill_dirs": [".agents/skills", ".codex/skills", ".cursor/skills"],
  "global_skill_dirs": ["$CODEX_HOME/skills", "~/.codex/skills", "~/.cursor/skills"],
  "pgvector_dsn": "postgresql://user:pass@localhost:5432/skills_router"
}
```

## Release-Automatisierung

Die Repository-CI validiert Python, den Node-Wrapper und Paket-Builds. Bei Tag-Pushes kann der Workflow den npm-Wrapper veröffentlichen und anschließend das GitHub-Release erstellen oder aktualisieren. Die Release-Beschreibung wird aus dem passenden `CHANGELOG.md`-Eintrag generiert und fügt Links hinzu zu:

- dem tag-spezifischen Changelog
- dem npm-Paket: https://www.npmjs.com/package/@the-long-ride/skills-router

## Roadmap

- [x] Kern-Installationsprüfpipeline.
- [x] Agenten-Brücke für beliebte AI-Agenten-Hosts.
- [x] Vollpaketinstallation mit generierten Routenplänen.
- [x] Einmalige All-Agent-Installationen mit zielbewusstem Routing.
- [x] `/skills-router index` Abgleich und Konfliktempfehlungen.
- [x] `/skills-router refine` Entdeckung und Routenverfeinerung.
- [x] Dynamische Routensuche über MCP und CLI.
- [x] Registry Watch Daemon mit Vertrauensverlustwarnungen.
- [ ] Routenwahl-Persistenz-API zur Anwendung menschlicher Auswahlen.
- [ ] pgvector-native Produktionsmigration.
- [ ] Dashboard für Routing-Verlauf, Audit-Protokolle und Konfliktentscheidungen.

## Lizenz

Dieses Projekt ist unter der **GNU General Public License (GPLv3)** lizenziert.

Entwickelt von **the-long-ride**.
