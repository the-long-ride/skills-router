# Skills Router

[![Version](https://img.shields.io/badge/version-v0.0.2-orange.svg)](../CHANGELOG.md)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](../LICENSE)
[![Author](https://img.shields.io/badge/author-the--long--ride-green.svg)](https://github.com/the-long-ride)
[![Build Status](https://img.shields.io/badge/tests-199%20passed-success.svg)](../tests/)

[English](../README.md) | [Español](es.md) | [简体中文](zh.md) | [日本語](ja.md) | [Deutsch](de.md) | [Français](fr.md)

`skills-router` es el comando CLI y el nombre del paquete PyPI. El paquete de envoltura npm
es [`@the-long-ride/skills-router`](https://www.npmjs.com/package/@the-long-ride/skills-router).

**Skills Router es un gestor de conjunto de habilidades para agentes de IA.** Revisa, registra,
descubre, indexa, compara y enruta habilidades/complementos de agentes de IA para que un agente host
pueda usar la capacidad correcta sin apoderarse silenciosamente de los recursos del paquete.

Skills Router no es un gestor de paquetes general. Posee metadatos, decisiones, registros
de auditoría y estado de enrutamiento. Los archivos de paquetes, entornos virtuales, extensiones de IDE
y directorios de habilidades de agentes host siguen siendo propiedad de la herramienta que los instaló.

## ¿Por qué skills-router?

Las habilidades de los agentes de IA son útiles, pero se dispersan en CLIs, IDEs, servidores
MCP, carpetas globales, carpetas de espacio de trabajo y gestores de paquetes específicos del host.
Eso hace que sea difícil responder preguntas simples: ¿qué habilidad debería usar este agente,
quién la aprobó, dónde está activa y qué sucede si otro paquete se superpone con ella?

`skills-router` ofrece a los agentes un plano de control compartido para ese problema. Le permite
instalar o descubrir habilidades una vez, revisarlas mediante comprobaciones de confianza y comportamiento,
y enrutar a cada agente a la capacidad correcta sin copiar archivos de paquetes ni meter enormes
tablas de rutas en los prompts. El gestor de paquetes sigue siendo el propietario de los recursos del paquete;
Skills Router posee las decisiones, los metadatos, el registro de auditoría y la capa de enrutamiento.

## Qué hace

- Revisa manifiestos completos de habilidades/complementos a través de comprobaciones de confianza, dependencias, semántica, capacidad y salud.
- Almacena metadatos de paquetes aprobados en un Índice del Cerebro.
- Escribe reglas `skills-router.json` que los agentes host pueden consultar a través de MCP o CLI.
- Instala una habilidad una vez para todos los agentes host configurados con `--all-agents` o `/skills-router install <package> for all agents`.
- Soporta instalaciones limitadas para todos los agentes con listas de objetivos como `--agent-target codex,cursor`.
- Enfuerza el enrutamiento consciente del objetivo cuando los agentes llaman a `route_task` o `skills-router route --target <agent>`.
- Soporta el conjunto predeterminado de hosts de agentes: `antigravity`, `antigravity-cli`, `antigravity-ide`, `codex`, `claude`, `hermes-agent`, `opencode`, `cline`, `cursor` y `windsurf`.
- Trata las instalaciones parciales como activación selectiva de rutas, no como extracción parcial de paquetes.
- Elimina los metadatos y el enrutamiento propiedad de Skills Router al desinstalar, luego vuelve a indexar la superficie de rutas restante.
- Reconcilia las rutas con `/skills-router index`.
- Descubre habilidades externas instaladas en el espacio de trabajo o globales con `/skills-router refine`.
- Escanea directorios de habilidades compartidos y específicos del host tanto en el espacio de trabajo como globales, incluyendo carpetas de habilidades del sistema anidadas.
- Mantiene las rutas externas recién descubiertas en `needs_selection` hasta que el humano confirme la activación.
- Publica descripciones de lanzamiento desde la sección correspondiente de `CHANGELOG.md` al enviar etiquetas, con enlaces de paquetes añadidos por la CI.

## Qué no hace

- No elimina archivos propiedad del paquete, repositorios, entornos virtuales o recursos de plugins/IDEs.
- No reemplaza a `pip`, `npm`, gestores de extensiones de IDE o gestores de plugins de agentes host.
- No auto-aprueba advertencias de confianza, conflictos de dependencias, rutas duplicadas o comportamientos desconocidos a menos que el humano apruebe explícitamente el riesgo.
- No inyecta grandes tablas de rutas en los prompts de los agentes. Los agentes deben consultar Skills Router dinámicamente.

## Arquitectura

```mermaid
flowchart LR
    Human[Humano] --> Host[Host del agente de IA]
    Host --> Bridge[Puente del agente]
    Host --> MCP[Servidor MCP stdio]
    Host --> CLI[CLI]

    Bridge --> Parser[Analizador de barra inclinada]
    Parser --> Executor[Ejecutor del puente]
    MCP --> Executor
    CLI --> Commands[Comandos estrictos]

    Commands --> Install[Flujo de instalación]
    Executor --> Install
    Commands --> Reconcile[Indexar y refinar]
    Executor --> Reconcile
    Commands --> Lookup[Búsqueda de rutas]
    Executor --> Lookup
    Commands --> Remove[Desinstalar metadatos]
    Executor --> Remove

    Install --> Resolver[Resolutor de registros]
    Resolver --> Trust[Filtro de confianza]
    Trust --> Deps[Resolutor de dependencias]
    Deps --> Semantic[Evaluador semántico]
    Semantic --> Capability[Comprobador de capacidad]
    Capability --> WG[Prompt de espacio de trabajo/global]
    WG --> Health[Comprobación de salud]

    Reconcile --> Discovery[Descubrimiento de habilidades]
    Discovery --> SkillDirs[Dirs de habilidades locales/globales]
    Discovery --> GlobalIndex[Índice global de Skills Router]
    Reconcile --> Conflict[Detector de conflictos]

    Install --> Store[(Índice del Cerebro)]
    Reconcile --> Store
    Conflict --> Routes[(skills-router.json)]
    Lookup --> Routes
    Remove --> Store
    Remove --> Routes
    Remove --> Lock
    Remove --> Audit
    Install --> Lock[(Archivo de bloqueo)]
    Install --> Audit[(Registro de auditoría)]
```

## Flujo de trabajo principal

```mermaid
flowchart TD
    A[El humano le pide a un agente de IA] --> B{Forma de la solicitud}
    B -->|/skills-router install pkg for me| C[Analizar solicitud de barra inclinada]
    B -->|Llamada estructurada de MCP| D[Llamar herramienta MCP]
    B -->|CLI estricta| E[Run command]

    C --> F[Resolver paquete o manifiesto]
    D --> F
    E --> F
    F --> G[Comprobaciones de confianza y dependencias]
    G -->|Rechazo duro| H[Detener y resumir]
    G -->|Revisión necesaria| I[Preguntar al humano]
    I -->|Cancelar| H
    I -->|Aprobar| J[Comparación semántica y de capacidad]
    G -->|Seguro| J
    J -->|Superposición| K[Recomendar elección de ruta]
    K --> L[El humano selecciona enrutamiento]
    J -->|Sin conflicto| M[Persistir metadatos]
    L --> M
    M --> N[Escribir enrutamiento y archivo de bloqueo]
    N --> O[Comprobación de salud]
    O -->|Fallo| P[Limpiar estado de Skills Router]
    O -->|Paso| Q[Auditoría y resumen corto]

    R[El gestor de paquetes del host cambia archivos] --> S["/skills-router index"]
    T[Aparece habilidad externa] --> U["/skills-router refine"]
    S --> V[Actualizar rutas y marcar obsoletas]
    U --> W[Descubrir e importar metadatos]
    V --> X[Recomendar decisiones de ruta]
    W --> X
```

## Instalación

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

El backend de almacenamiento predeterminado es la memoria local respaldada por JSON en
`~/.skills-router`. Hay un contenedor local de Node disponible en `skills-router-npx/` para
flujos de trabajo de `npx` e IDE; ver [GUIDELINE.md](../GUIDELINE.md).

## Inicio rápido

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

## Superficie de comandos

| Comando | Propósito |
| :--- | :--- |
| `install <manifest-or-package>` | Resuelve, revisa, registra y enruta un paquete. |
| `index` | Reconstruye vectores/rutas indexadas y detecta conflictos o rutas obsoletas. |
| `refine [skillset ...]` | Descubre habilidades externas, importa metadatos y reconcilia rutas. |
| `route <task>` | Consulta rutas activas o que requieren revisión para una tarea. |
| `uninstall <tool_id>` | Elimina únicamente el enrutamiento/metadatos propiedad de Skills Router. |
| `list` | Lista las herramientas indexadas. |
| `inspect <tool_id>` | Imprime una entrada del Índice del Cerebro. |
| `audit` | Consulta eventos de auditoría. |
| `watch` | Ejecuta Registry Watch una vez o como demonio. |
| `prompt` | Renderiza instrucciones de puente específicas del host. |
| `chat` | Analiza y ejecuta solicitudes de `/skills-router` en formato de chat. |
| `mcp` | Ejecuta el servidor de herramientas JSON-RPC de stdio local. |

## Instalaciones únicas para todos los agentes

Las instalaciones para todos los agentes son el flujo de trabajo principal de v0.0.2:

```bash
skills-router install writer-pack --package-type skillset --all-agents --json
```

El paquete todavía se registra una vez en Skills Router. Las rutas generadas
son globales, y cada host configurado llega a ellas a través de MCP o el puente
de la CLI. Skills Router posee únicamente metadatos y enrutamiento; los recursos
del paquete siguen siendo propiedad del gestor de paquetes del host o del instalador de habilidades.

Objetivos predeterminados de todos los agentes:

```text
antigravity, antigravity-cli, antigravity-ide, codex, claude,
hermes-agent, opencode, cline, cursor, windsurf
```

Use `--agent-target` cuando una habilidad deba aplicarse solo a una parte de ese conjunto:

```bash
skills-router install writer-pack \
  --package-type skillset \
  --all-agents \
  --agent-target codex,cursor \
  --json
```

Cuando se almacena una lista de objetivos, la búsqueda de rutas la respeta solo cuando el llamador
identifica el host actual:

```bash
skills-router route "draft release notes" --target codex --json
skills-router route "draft release notes" --target cursor --json
```

Para solicitudes en formato de chat, los agentes pueden usar:

```text
/skills-router install <package> for all installed agents
```

## Modelo de enrutamiento

Skills Router separa la presencia del paquete de la activación del agente:

- **Presencia del paquete:** el gestor de paquetes del host instala o actualiza el paquete completo.
- **Índice del Cerebro:** Skills Router almacena metadatos del manifiesto, confianza, dependencias, vectores, comportamiento y alcance.
- **Enrutamiento:** Skills Router escribe paquetes y reglas en `skills-router.json`.
- **Selección:** los conflictos de rutas y las habilidades descubiertas externamente utilizan `needs_selection` hasta que el humano confirme la activación.
- **Búsqueda:** los agentes llaman a MCP `route_task` o `skills-router route` con su objetivo en lugar de leer archivos de ruta directamente.
- **Rutas obsoletas:** `index` marca los paquetes faltantes como `missing_from_index`; no elimina archivos de paquetes.

## Refinamiento y Descubrimiento

`skills-router refine` cierra la brecha cuando un humano instala habilidades fuera del
espacio de trabajo, por ejemplo a través de `npx`, un instalador de habilidades de agente host,
o un directorio global de habilidades de Codex.

Fuentes de descubrimiento:

- Directorios de habilidades del espacio de trabajo: `.agents/skills` más directorios específicos del host como `.codex/skills`, `.claude/skills`, `.cline/skills`, `.cursor/skills`, `.windsurf/skills`, `.opencode/skills`, `.agent/skills`, `.antigravity/skills`, `.hermes/skills` y `.kiro/skills`
- Directorios globales de habilidades: `$CODEX_HOME/skills`, `~/.codex/skills` y los directorios de habilidades globales específicos del host correspondientes.
- Carpetas de habilidades anidadas, incluyendo `.system/.../SKILL.md`
- Estado global de Skills Router desde `global_data_dir`

Un refinamiento en blanco descubre todas las habilidades instaladas visibles. El refinamiento con nombre descubre y reporta solo los conjuntos de habilidades coincidentes mientras los compara con la superficie de rutas visible. El chat `/skills-router refine` asigna rutas descubiertas en el espacio de trabajo a `workspace:<agent-id>` mientras las compara con todos los alcances visibles.

## Comandos de barra inclinada para agentes

El Puente del Agente acepta solicitudes naturales humanas y las convierte en operaciones estrictas:

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

El puente establece por defecto el alcance de instalación en `workspace:<agent-id>` a menos que el humano especifique global. `for all agents` significa una instalación global para el conjunto de objetivos de todos los agentes predeterminado; las listas personalizadas `--agent-target` se aplican mediante la búsqueda de rutas consciente del objetivo. El analizador elimina palabras de relleno como `for me` y devuelve `human_summary` para respuestas cortas de los agentes.

## Superficie de herramientas MCP

`skills-router mcp` expone:

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

Use `run_slash_command` para el texto de chat humano. Use las herramientas estructuradas solo cuando el host ya tenga argumentos limpios. El texto del contenido de MCP es intencionadamente compacto; los datos completos legibles por máquina permanecen en `structuredContent`.

Las llamadas MCP de instalación estructuradas pueden pasar `all_agents: true` y opcionalmente `target_agents`. Las llamadas de enrutamiento estructuradas pueden pasar `target` para que las listas de objetivos almacenadas se apliquen al host que realiza la llamada.

## Hosts de agentes compatibles

| Objetivo | Ubicaciones de instrucciones |
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

Renderice el texto del puente específico del objetivo con:

```bash
skills-router prompt --target codex
skills-router prompt --target cursor
skills-router prompt --target windsurf
skills-router prompt --target codex --detail full
```

El prompt predeterminado es compacto para que las instrucciones persistentes del agente cuesten menos tokens. Use `--detail full` solo al generar documentos o depurar una integración.

## Configuración

`~/.skills-router/config.json` puede anular campos de `SkillsRouterConfig` como:

```json
{
  "storage_backend": "memory",
  "workspace_root": "/path/to/workspace",
  "workspace_skill_dirs": [".agents/skills", ".codex/skills", ".cursor/skills"],
  "global_skill_dirs": ["$CODEX_HOME/skills", "~/.codex/skills", "~/.cursor/skills"],
  "pgvector_dsn": "postgresql://user:pass@localhost:5432/skills_router"
}
```

## Automatización de lanzamientos

La CI del repositorio valida Python, el contenedor de Node y las compilaciones de paquetes. Al enviar etiquetas, el flujo de trabajo puede publicar el contenedor npm y luego crear o actualizar el lanzamiento en GitHub. La descripción del lanzamiento se genera a partir de la entrada correspondiente de `CHANGELOG.md` y añade enlaces a:

- el registro de cambios específico de la etiqueta
- el paquete npm: https://www.npmjs.com/package/@the-long-ride/skills-router

## Hoja de ruta

- [x] Flujo de revisión de instalación principal.
- [x] Puente del Agente para hosts de agentes de IA populares.
- [x] Instalación de paquete completo con planes de ruta generados.
- [x] Instalaciones únicas para todos los agentes con enrutamiento consciente del objetivo.
- [x] Reconciliación de `/skills-router index` y recomendaciones de conflicto.
- [x] Descubrimiento y refinamiento de rutas con `/skills-router refine`.
- [x] Búsqueda dinámica de rutas a través de MCP y CLI.
- [x] Demonio Registry Watch con alertas de degradación de confianza.
- [ ] API de persistencia de elección de ruta para aplicar selecciones humanas.
- [ ] Migración de producción pgvector nativa.
- [ ] Panel de control para el historial de enrutamiento, registros de auditoría y decisiones de conflictos.

## Licencia

Este proyecto está bajo la licencia **Licencia Pública General de GNU (GPLv3)**.

Desarrollado por **the-long-ride**.
