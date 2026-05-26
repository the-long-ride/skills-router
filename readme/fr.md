# Skills Router

[![Version](https://img.shields.io/badge/version-v0.0.2-orange.svg)](../CHANGELOG.md)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](../LICENSE)
[![Author](https://img.shields.io/badge/author-the--long--ride-green.svg)](https://github.com/the-long-ride)
[![Build Status](https://img.shields.io/badge/tests-199%20passed-success.svg)](../tests/)

[English](../README.md) | [Español](es.md) | [简体中文](zh.md) | [日本語](ja.md) | [Deutsch](de.md) | [Français](fr.md)

`skills-router` est la commande CLI et le nom du paquet PyPI. Le paquet wrapper npm
est [`@the-long-ride/skills-router`](https://www.npmjs.com/package/@the-long-ride/skills-router).

**Skills Router est un gestionnaire de compétences pour agents d'IA.** Il examine, enregistre,
découvre, indexe, compare et oriente (route) les compétences/extensions des agents d'IA afin qu'un agent hôte
puisse utiliser la bonne capacité sans s'approprier silencieusement les ressources du paquet.

Skills Router n'est pas un gestionnaire de paquets général. Il détient les métadonnées, les décisions,
les journaux d'audit et l'état du routage. Les fichiers de paquets, les environnements virtuels, les extensions
d'IDE et les répertoires de compétences des agents hôtes restent la propriété de l'outil qui les a installés.

## Pourquoi skills-router ?

Les compétences des agents d'IA sont utiles, mais elles se dispersent dans les CLI, les IDE, les serveurs
MCP, les dossiers globaux, les dossiers de l'espace de travail et les gestionnaires de paquets spécifiques à l'hôte.
Il est donc difficile de répondre à des questions simples : quelle compétence cet agent doit-il utiliser, qui
l'a approuvée, où est-elle active et que se passe-t-il si un autre paquet chevauche celle-ci ?

`skills-router` offre aux agents un plan de contrôle partagé pour résoudre ce problème. Il vous permet
d'installer ou de découvrir des compétences une seule fois, de les examiner via des contrôles de confiance
et de comportement, et d'orienter chaque agent vers la bonne capacité sans copier de fichiers de paquets
ni intégrer de gigantesques tables de routage dans les prompts. Le gestionnaire de paquets reste propriétaire des
ressources du paquet ; Skills Router possède les décisions, les métadonnées, la piste d'audit et la couche de routage.

## Ce qu'il fait

- Examine les manifestes complets de compétences/extensions par le biais de contrôles de confiance, de dépendances, de sémantique, de capacités et de santé.
- Stocke les métadonnées des paquets approuvés dans un Index du Cerveau.
- Écrit des règles `skills-router.json` que les agents hôtes peuvent interroger via MCP ou CLI.
- Installe une compétence une seule fois pour tous les agents hôtes configurés avec `--all-agents` ou `/skills-router install <package> for all agents`.
- Prend en charge des installations limitées pour tous les agents avec des listes de cibles telles que `--agent-target codex,cursor`.
- Impose un routage sensible à la cible lorsque les agents appellent `route_task` ou `skills-router route --target <agent>`.
- Prend en charge le jeu par défaut d'hôtes d'agents : `antigravity`, `antigravity-cli`, `antigravity-ide`, `codex`, `claude`, `hermes-agent`, `opencode`, `cline`, `cursor` et `windsurf`.
- Traite les installations partielles comme une activation sélective des routes, et non comme une extraction partielle de paquets.
- Supprime les métadonnées et le routage appartenant à Skills Router lors de la désinstallation, puis réindexe la surface de routage restante.
- Rapproche les routes avec `/skills-router index`.
- Découvre les compétences externes installées dans l'espace de travail ou au niveau global avec `/skills-router refine`.
- Analyse les répertoires de compétences partagés et spécifiques à l'hôte, tant pour l'espace de travail que globaux, y compris les dossiers de compétences système imbriqués.
- Conserve les nouvelles routes externes découvertes sous l'état `needs_selection` jusqu'à ce que l'humain confirme l'activation.
- Publie les descriptions de version à partir de la section correspondante du fichier `CHANGELOG.md` lors des poussées de tags (tags push), avec des liens de paquets ajoutés par la CI.

## Ce qu'il ne fait pas

- Il ne supprime pas les fichiers appartenant au paquet, les dépôts, les environnements virtuels ou les ressources de plugins/IDE.
- Il ne remplace pas `pip`, `npm`, les gestionnaires d'extensions d'IDE ou les gestionnaires de plugins des agents hôtes.
- Il n'approuve pas automatiquement les avertissements de confiance, les conflits de dépendances, les routes en double ou les comportements inconnus, à moins que l'humain ne donne son accord explicite pour accepter le risque.
- Il n'injecte pas de grandes tables de routage dans les prompts des agents. Les agents doivent interroger Skills Router de manière dynamique.

## Architecture

```mermaid
flowchart LR
    Human[Humain] --> Host[Hôte de l'agent d'IA]
    Host --> Bridge[Pont de l'agent]
    Host --> MCP[Serveur MCP stdio]
    Host --> CLI[CLI]

    Bridge --> Parser[Analyseur de commandes slash]
    Parser --> Executor[Exécuteur de pont]
    MCP --> Executor
    CLI --> Commands[Commandes strictes]

    Commands --> Install[Pipeline d'installation]
    Executor --> Install
    Commands --> Reconcile[Indexation et raffinement]
    Executor --> Reconcile
    Commands --> Lookup[Recherche de routes]
    Executor --> Lookup
    Commands --> Remove[Désinstallation des métadonnées]
    Executor --> Remove

    Install --> Resolver[Résolveur de registre]
    Resolver --> Trust[Porte de confiance]
    Trust --> Deps[Résolveur de dépendances]
    Deps --> Semantic[Évaluateur sémantique]
    Semantic --> Capability[Vérificateur de capacités]
    Capability --> WG[Prompt d'espace de travail/global]
    WG --> Health[Contrôle de santé]

    Reconcile --> Discovery[Découverte de compétences]
    Discovery --> SkillDirs[Dossiers de compétences locaux/globaux]
    Discovery --> GlobalIndex[Index global d'Skills Router]
    Reconcile --> Conflict[Détecteur de conflits]

    Install --> Store[(Index du Cerveau)]
    Reconcile --> Store
    Conflict --> Routes[(skills-router.json)]
    Lookup --> Routes
    Remove --> Store
    Remove --> Routes
    Remove --> Lock
    Remove --> Audit
    Install --> Lock[(Fichier de verrouillage)]
    Install --> Audit[(Journal d'audit)]
```

## Flux de travail principal

```mermaid
flowchart TD
    A[L'humain demande à un agent d'IA] --> B{Forme de la requête}
    B -->|/skills-router install pkg for me| C[Analyser la requête slash]
    B -->|Appel MCP structuré| D[Appeler l'outil MCP]
    B -->|CLI stricte| E[Exécuter la commande]

    C --> F[Résoudre le paquet ou le manifeste]
    D --> F
    E --> F
    F --> G[Contrôles de confiance et de dépendance]
    G -->|Rejet strict| H[Arrêter et résumer]
    G -->|Examen nécessaire| I[Demander à l'humain]
    I -->|Annuler| H
    I -->|Approuver| J[Comparaison sémantique et de capacités]
    G -->|Sécurisé| J
    J -->|Chevauchement| K[Recommander un choix de route]
    K --> L[L'humain sélectionne la route]
    J -->|Pas de conflit| M[Persister les métadonnées]
    L --> M
    M --> N[Écrire la route et le fichier de verrouillage]
    N --> O[Contrôle de santé]
    O -->|Échec| P[Nettoyer l'état d'Skills Router]
    O -->|Succès| Q[Audit et résumé court]

    R[Le gestionnaire de paquets de l'hôte modifie les fichiers] --> S["/skills-router index"]
    T[Une compétence externe apparaît] --> U["/skills-router refine"]
    S --> V[Actualiser les routes et marquer comme obsolète]
    U --> W[Découvrir et importer les métadonnées]
    V --> X[Recommander des décisions de routage]
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

Le stockage back-end par défaut est une mémoire locale basée sur JSON sous
`~/.skills-router`. Un wrapper Node local est disponible dans `skills-router-npx/` pour les
flux de travail `npx` et d'IDE ; voir [GUIDELINE.md](../GUIDELINE.md).

## Démarrage rapide

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

## Liste des commandes

| Commande | Objectif |
| :--- | :--- |
| `install <manifest-or-package>` | Résout, examine, enregistre et achemine un paquet. |
| `index` | Reconstruit les vecteurs/routes indexés et détecte les conflits ou routes obsolètes. |
| `refine [skillset ...]` | Découvre les compétences externes, importe les métadonnées et rapproche les routes. |
| `route <task>` | Interroge les routes actives ou nécessitant un examen pour une tâche. |
| `uninstall <tool_id>` | Supprime uniquement les métadonnées/le routage appartenant à Skills Router. |
| `list` | Répertorie les outils indexés. |
| `inspect <tool_id>` | Affiche une entrée de l'Index du Cerveau. |
| `audit` | Interroge les événements d'audit. |
| `watch` | Exécute Registry Watch une fois ou en mode démon. |
| `prompt` | Génère les instructions de pont spécifiques à l'hôte. |
| `chat` | Analyse et exécute les requêtes `/skills-router` au format chat. |
| `mcp` | Exécute le serveur d'outils JSON-RPC stdio local. |

## Installations uniques pour tous les agents

Les installations pour tous les agents sont le flux de travail phare de la version v0.0.2 :

```bash
skills-router install writer-pack --package-type skillset --all-agents --json
```

Le paquet est toujours enregistré une seule fois dans Skills Router. Les routes générées
sont globales, et chaque hôte configuré y accède par le biais de MCP ou du pont
de la CLI. Skills Router possède uniquement les métadonnées et le routage ; les ressources du
paquet restent la propriété du gestionnaire de paquets de l'hôte ou de l'installateur de compétences.

Cibles par défaut pour tous les agents :

```text
antigravity, antigravity-cli, antigravity-ide, codex, claude,
hermes-agent, opencode, cline, cursor, windsurf
```

Utilisez `--agent-target` lorsqu'une compétence ne doit s'appliquer qu'à une partie de cet ensemble :

```bash
skills-router install writer-pack \
  --package-type skillset \
  --all-agents \
  --agent-target codex,cursor \
  --json
```

Lorsqu'une liste de cibles est stockée, la recherche de routes la respecte uniquement lorsque l'appelant
identifie l'hôte actuel :

```bash
skills-router route "draft release notes" --target codex --json
skills-router route "draft release notes" --target cursor --json
```

Pour les requêtes au format chat, les agents peuvent utiliser :

```text
/skills-router install <package> for all installed agents
```

## Modèle de routage

Skills Router sépare la présence du paquet de l'activation de l'agent :

- **Présence du paquet :** le gestionnaire de paquets de l'hôte installe ou met à jour le paquet complet.
- **Index du Cerveau :** Skills Router stocke les métadonnées de manifeste, de confiance, de dépendance, de vecteur, de comportement et de portée.
- **Routage :** Skills Router écrit les paquets et les règles dans `skills-router.json`.
- **Sélection :** les conflits de routes et les compétences découvertes de l'extérieur utilisent `needs_selection` jusqu'à ce que l'humain confirme l'activation.
- **Recherche :** les agents appellent le MCP `route_task` ou `skills-router route` avec leur cible au lieu de lire directement les fichiers de route.
- **Routes obsolètes :** `index` marque les paquets manquants comme `missing_from_index` ; il ne supprime pas les fichiers de paquets.

## Raffinement et Découverte

`skills-router refine` comble l'écart lorsqu'un humain installe des compétences en dehors de
l'espace de travail, par exemple via `npx`, un installateur de compétences de l'agent hôte, ou un
répertoire global de compétences Codex.

Sources de découverte :

- Dossiers de compétences d'espace de travail : `.agents/skills` plus les dossiers spécifiques à l'hôte comme `.codex/skills`, `.claude/skills`, `.cline/skills`, `.cursor/skills`, `.windsurf/skills`, `.opencode/skills`, `.agent/skills`, `.antigravity/skills`, `.hermes/skills` et `.kiro/skills`
- Dossiers de compétences globaux : `$CODEX_HOME/skills`, `~/.codex/skills` et les dossiers de compétences globaux correspondants spécifiques à l'hôte.
- Dossiers de compétences imbriqués, y compris `.system/.../SKILL.md`
- État global d'Skills Router provenant de `global_data_dir`

Un raffinement vierge découvre toutes les compétences installées visibles. Un raffinement nommé découvre et signale uniquement les ensembles de compétences correspondants tout en les comparant à la surface de routage visible. Le chat `/skills-router refine` attribue les routes découvertes dans l'espace de travail à `workspace:<agent-id>` tout en comparant avec toutes les portées visibles.

## Commandes Slash pour les agents

Le Pont de l'agent accepte les requêtes humaines naturelles et les transforme en opérations strictes :

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

Le pont définit par défaut la portée de l'installation sur `workspace:<agent-id>` à moins que l'humain ne spécifie globale. `for all agents` signifie une installation globale pour l'ensemble cible d'agents par défaut ; les listes personnalisées `--agent-target` sont appliquées par recherche de routes sensible à la cible. L'analyseur supprime les mots de remplissage tels que `for me` et renvoie `human_summary` pour les réponses courtes de l'agent.

## Interface d'outils MCP

`skills-router mcp` expose :

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

Utilisez `run_slash_command` pour le texte du chat humain. Utilisez les outils structurés uniquement lorsque l'hôte dispose déjà d'arguments propres. Le texte du contenu MCP est intentionnellement compact ; les données complètes lisibles par machine restent dans `structuredContent`.

Les appels d'installation MCP structurés peuvent transmettre `all_agents: true` et facultativement `target_agents`. Les appels de routage structurés peuvent transmettre `target` afin que les listes de cibles stockées soient appliquées pour l'hôte appelant.

## Hôtes d'agents pris en charge

| Cible | Emplacements des instructions |
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

Générez le texte du pont spécifique à la cible avec :

```bash
skills-router prompt --target codex
skills-router prompt --target cursor
skills-router prompt --target windsurf
skills-router prompt --target codex --detail full
```

Le prompt par défaut est compact afin que les instructions persistantes de l'agent coûtent moins de tokens. Utilisez `--detail full` uniquement lors de la génération de documents ou du débogage d'une intégration.

## Configuration

`~/.skills-router/config.json` peut remplacer les champs de `SkillsRouterConfig` tels que :

```json
{
  "storage_backend": "memory",
  "workspace_root": "/path/to/workspace",
  "workspace_skill_dirs": [".agents/skills", ".codex/skills", ".cursor/skills"],
  "global_skill_dirs": ["$CODEX_HOME/skills", "~/.codex/skills", "~/.cursor/skills"],
  "pgvector_dsn": "postgresql://user:pass@localhost:5432/skills_router"
}
```

## Automatisation des versions

Le CI du dépôt valide Python, le wrapper Node et les builds de paquets. Lors des poussées de tags, le flux de travail peut publier le wrapper npm, puis créer ou mettre à jour la version GitHub. La description de la version est générée à partir de l'entrée correspondante de `CHANGELOG.md` et ajoute des liens vers :

- le changelog spécifique au tag
- le paquet npm : https://www.npmjs.com/package/@the-long-ride/skills-router

## Feuille de route

- [x] Pipeline d'examen de l'installation principale.
- [x] Pont de l'agent pour les hôtes d'agents d'IA populaires.
- [x] Installation de paquets complets avec plans de routage générés.
- [x] Installations uniques pour tous les agents avec routage sensible à la cible.
- [x] Rapprochement de `/skills-router index` et recommandations de conflits.
- [x] Découverte et raffinement de routes avec `/skills-router refine`.
- [x] Recherche dynamique de routes via MCP et CLI.
- [x] Démon Registry Watch avec alertes de dégradation de la confiance.
- [ ] API de persistance de choix de route pour l'application des sélections humaines.
- [ ] Migration de production native pgvector.
- [ ] Tableau de bord pour l'historique du routage, les journaux d'audit et les décisions de conflits.

## Licence

Ce projet est sous licence **GNU General Public License (GPLv3)**.

Développé par **the-long-ride**.
