# Skills Router

[![Version](https://img.shields.io/badge/version-v0.0.2-orange.svg)](../CHANGELOG.md)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](../LICENSE)
[![Author](https://img.shields.io/badge/author-the--long--ride-green.svg)](https://github.com/the-long-ride)
[![Build Status](https://img.shields.io/badge/tests-199%20passed-success.svg)](../tests/)

[English](../README.md) | [Español](es.md) | [简体中文](zh.md) | [日本語](ja.md) | [Deutsch](de.md) | [Français](fr.md)

`skills-router` は CLI コマンドおよび PyPI パッケージ名です。npm ラッパーパッケージは
[`@the-long-ride/skills-router`](https://www.npmjs.com/package/@the-long-ride/skills-router) です。

**Skills Router は、AI エージェントのスキルセットマネージャーです。** ホストエージェントがパッケージの
リソースを暗黙的に占有することなく、適切な機能を使用できるように、AI エージェントのスキル/プラグインの
レビュー、登録、検出、インデックス作成、比較、およびルーティングを行います。

Skills Router は一般的なパッケージマネージャーではありません。メタデータ、意思決定、監査ログ、
およびルーティング状態を管理します。パッケージファイル、仮想環境、IDE 拡張機能、およびホストエージェントの
スキルディレクトリは、それらをインストールしたツールによって引き続き所有されます。

## なぜ skills-router なのか？

AI エージェントのスキルは有用ですが、CLI、IDE、MCP サーバー、グローバルフォルダ、ワークスペースフォルダ、
およびホスト固有のパッケージマネージャーに分散してしまいます。そのため、「このエージェントはどのスキルを使用すべきか」、
「誰が承認したのか」、「どこでアクティブになっているのか」、「別のパッケージと重複した場合はどうなるのか」といった
簡単な疑問に答えるのが難しくなります。

`skills-router` は、この問題に対してエージェントに1つの共有コントロールプレーンを提供します。パッケージファイルを
コピーしたり、プロンプトに膨大なルートテーブルを詰め込んだりすることなく、スキルを一度インストールまたは検出して、
信頼性と動作チェックを通じてレビューし、各エージェントを適切な機能にルーティングできます。パッケージマネージャーは
引き続きパッケージリソースを所有し、Skills Router は意思決定、メタデータ、監査証跡、およびルーティング層を管理します。

## 主な機能

- 信頼性、依存関係、意味、機能、およびヘルスチェックを通じて、完全なスキル/プラグインマニフェストをレビューします。
- 承認されたパッケージのメタデータを Brain インデックスに保存します。
- ホストエージェントが MCP または CLI を通じてクエリできる `skills-router.json` ルールを書き込みます。
- `--all-agents` または `/skills-router install <package> for all agents` を使用して、設定されたすべてのホストエージェントに対してスキルを一度にインストールします。
- `--agent-target codex,cursor` などのターゲットリストを使用して、絞り込まれた全エージェントインストールをサポートします。
- エージェントが `route_task` または `skills-router route --target <agent>` を呼び出す際、ターゲットを意識したルーティングを強制します。
- デフォルトの全エージェントホストセット（`antigravity`、`antigravity-cli`、`antigravity-ide`、`codex`、`claude`、`hermes-agent`、`opencode`、`cline`、`cursor`、`windsurf`）をサポートします。
- 部分的なインストールを、部分的なパッケージ抽出ではなく、選択的なルートのアクティブ化として処理します。
- アンインストール時に Skills Router 所有のメタデータ/ルーティングを削除し、残りのルートサーフェスを再インデックスします。
- `/skills-router index` でルートを調整します。
- `/skills-router refine` を使用して、ワークスペースやグローバルにインストールされた外部スキルを検出します。
- ネストされたシステムスキルフォルダを含む、共有およびホスト固有のワークスペース/グローバルスキルディレクトリをスキャンします。
- 人間がアクティブ化を確認するまで、新しく検出された外部ルートを `needs_selection` のままにします。
- タグプッシュ時に対応する `CHANGELOG.md` セクションからリリース説明を公開し、CI によってパッケージリンクを追加します。

## 対象外のこと

- パッケージ所有のファイル、リポジトリ、仮想環境、または IDE/プラグインリソースを削除することはありません。
- `pip`、`npm`、IDE 拡張機能マネージャー、またはホストエージェントのプラグインマネージャーを置き換えることはありません。
- 人間が明示的にリスクを承認しない限り、信頼性の警告、依存関係の競合、重複したルート、または不明な動作を自動承認することはありません。
- エージェントのプロンプトに巨大なルートテーブルを注入することはありません。エージェントは Skills Router に動的にクエリする必要があります。

## アーキテクチャ

```mermaid
flowchart LR
    Human[人間] --> Host[AI エージェントホスト]
    Host --> Bridge[エージェントブリッジ]
    Host --> MCP[MCP stdio サーバー]
    Host --> CLI[CLI]

    Bridge --> Parser[スラッシュパーサー]
    Parser --> Executor[ブリッジ実行エンジン]
    MCP --> Executor
    CLI --> Commands[厳密なコマンド]

    Commands --> Install[インストールパイプライン]
    Executor --> Install
    Commands --> Reconcile[インデックスとリファイン]
    Executor --> Reconcile
    Commands --> Lookup[ルート検索]
    Executor --> Lookup
    Commands --> Remove[メタデータアンインストール]
    Executor --> Remove

    Install --> Resolver[レジストリリゾルバー]
    Resolver --> Trust[信頼ゲート]
    Trust --> Deps[依存関係リゾルバー]
    Deps --> Semantic[意味エバリュエーター]
    Semantic --> Capability[機能チェッカー]
    Capability --> WG[ワークスペース/グローバルプロンプト]
    WG --> Health[ヘルスチェック]

    Reconcile --> Discovery[スキル検出]
    Discovery --> SkillDirs[ワークスペース/グローバルスキルディレクトリ]
    Discovery --> GlobalIndex[グローバル Skills Router インデックス]
    Reconcile --> Conflict[競合検出器]

    Install --> Store[(Brain インデックス)]
    Reconcile --> Store
    Conflict --> Routes[(skills-router.json)]
    Lookup --> Routes
    Remove --> Store
    Remove --> Routes
    Remove --> Lock
    Remove --> Audit
    Install --> Lock[(ロックファイル)]
    Install --> Audit[(監査ログ)]
```

## コアワークフロー

```mermaid
flowchart TD
    A[人間が AI エージェントに依頼する] --> B{リクエスト形式}
    B -->|/skills-router install pkg for me| C[スラッシュリクエストの解析]
    B -->|MCP 構造化呼び出し| D[MCP ツールの呼び出し]
    B -->|厳密な CLI| E[コマンドの実行]

    C --> F[パッケージまたはマニフェストの解決]
    D --> F
    E --> F
    F --> G[信頼性と依存関係のチェック]
    G -->|強制拒否| H[停止して要約]
    G -->|レビューが必要| I[人間に確認]
    I -->|キャンセル| H
    I -->|承認| J[意味と機能の比較]
    G -->|安全| J
    J -->|重複| K[ルート選択の推奨]
    K --> L[人間がルーティングを選択]
    J -->|競合なし| M[メタデータの永続化]
    L --> M
    M --> N[ルーティングとロックファイルの書き込み]
    N --> O[ヘルスチェック]
    O -->|失敗| P[Skills Router 状態のクリーンアップ]
    O -->|合格| Q[監査と短い要約]

    R[ホストパッケージマネージャーがファイルを変更] --> S["/skills-router index"]
    T[外部スキルが出現] --> U["/skills-router refine"]
    S --> V[ルートの更新と期限切れマーク]
    U --> W[メタデータの検出とインポート]
    V --> X[ルート決定の推奨]
    W --> X
```

## インストール

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

デフォルトのストレージバックエンドは、`~/.skills-router` 配下の JSON ベースのローカルメモリです。
`npx` および IDE ワークフロー用に `skills-router-npx/` でローカルの Node ラッパーを使用できます。[GUIDELINE.md](../GUIDELINE.md) を参照してください。

## クイックスタート

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

## コマンド一覧

| コマンド | 用途 |
| :--- | :--- |
| `install <manifest-or-package>` | パッケージを解決、レビュー、登録、およびルーティングします。 |
| `index` | インデックス付きのベクトル/ルートを再構築し、競合または古いルートを検出します。 |
| `refine [skillset ...]` | 外部スキルを検出し、メタデータをインポートして、ルートを調整します。 |
| `route <task>` | タスクのアクティブなルートまたはレビューが必要なルートを照会します。 |
| `uninstall <tool_id>` | Skills Router 所有のメタデータ/ルーティングのみを削除します。 |
| `list` | インデックス登録されたツールを一覧表示します。 |
| `inspect <tool_id>` | Brain インデックスのエントリを1つ出力します。 |
| `audit` | 監査イベントを照会します。 |
| `watch` | Registry Watch を一度またはデーモンとして実行します。 |
| `prompt` | ホスト固有のブリッジ手順をレンダリングします。 |
| `chat` | チャット形式の `/skills-router` リクエストを解析して実行します。 |
| `mcp` | ローカルの stdio JSON-RPC ツールサーバーを実行します。 |

## 一括全エージェントインストール

全エージェントインストールは、v0.0.2 の主要なワークフローです：

```bash
skills-router install writer-pack --package-type skillset --all-agents --json
```

パッケージは引き続き Skills Router に1度だけ登録されます。生成されるルートはグローバルであり、設定された各ホストは MCP または CLI ブリッジを介してそれらにアクセスします。Skills Router はメタデータとルーティングのみを所有し、パッケージリソースはホストパッケージマネージャーまたはスキルインストーラーによって引き続き所有されます。

デフォルトの全エージェントターゲット：

```text
antigravity, antigravity-cli, antigravity-ide, codex, claude,
hermes-agent, opencode, cline, cursor, windsurf
```

スキルをそのセットの一部にのみ適用する必要がある場合は、`--agent-target` を使用します：

```bash
skills-router install writer-pack \
  --package-type skillset \
  --all-agents \
  --agent-target codex,cursor \
  --json
```

ターゲットリストが保存されている場合、ルート検索は呼び出し元が現在のホストを識別している場合にのみターゲットリストを尊重します：

```bash
skills-router route "draft release notes" --target codex --json
skills-router route "draft release notes" --target cursor --json
```

チャット形式のリクエストの場合、エージェントは以下を使用できます：

```text
/skills-router install <package> for all installed agents
```

## ルーティングモデル

Skills Router は、パッケージの存在とエージェントのアクティブ化を分離します。

- **パッケージの存在:** ホストパッケージマネージャーが完全なパッケージをインストールまたは更新します。
- **Brain インデックス:** Skills Router は、マニフェスト、信頼性、依存関係、ベクトル、動作、およびスコープのメタデータを保存します。
- **ルーティング:** Skills Router は `skills-router.json` のパッケージとルールを書き込みます。
- **選択:** ルートの競合および外部で検出されたスキルは、人間がアクティブ化を確認するまで `needs_selection` を使用します。
- **検索:** エージェントはルートファイルを直接読み取るのではなく、ターゲットを指定して MCP `route_task` または `skills-router route` を呼び出します。
- **古いルート:** `index` は不足しているパッケージに `missing_from_index` マークを付けます。パッケージファイル自体は削除しません。

## リファインと検出

`skills-router refine` は、人間がワークスペースの外（`npx`、ホストエージェントのスキルインストーラー、グローバルな Codex スキルディレクトリなど）でスキルをインストールした場合のギャップを埋めます。

検出ソース：

- ワークスペースのスキルディレクトリ: `.agents/skills` およびホスト固有のディレクトリ（`.codex/skills`、`.claude/skills`、`.cline/skills`、`.cursor/skills`、`.windsurf/skills`、`.opencode/skills`、`.agent/skills`、`.antigravity/skills`、`.hermes/skills`、`.kiro/skills`）
- グローバルなスキルディレクトリ: `$CODEX_HOME/skills`、`~/.codex/skills`、および対応するホスト固有のグローバルスキルディレクトリ
- ネストされたスキルフォルダ（`.system/.../SKILL.md` を含む）
- `global_data_dir` からのグローバルな Skills Router 状態

引数なしの refine は、表示可能なすべてのインストール済みスキルを検出します。名前指定の refine は、表示可能なルートサーフェスと比較しながら、一致するスキルセットのみを検出して報告します。チャット形式の `/skills-router refine` は、表示可能なすべてのスコープと比較しながら、ワークスペースで検出されたルートを `workspace:<agent-id>` に割り当てます。

## エージェント向けスラッシュコマンド

エージェントブリッジは、自然な人間のリクエストを受け入れ、それを厳密な操作に変換します：

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

ブリッジは、人間がグローバルと言わない限り、インストールのスコープをデフォルトで `workspace:<agent-id>` に設定します。`for all agents` は、デフォルトの全エージェントターゲットセットに対する1つのグローバルインストールを意味します。カスタムの `--agent-target` リストは、ターゲットを意識したルート検索によって強制されます。パーサーは `for me` などの不要な言葉を取り除き、短いエージェントの返信のために `human_summary` を返します。

## MCP ツール一覧

`skills-router mcp` は以下を公開します：

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

人間のチャットテキストには `run_slash_command` を使用します。ホストがすでにクリーンな引数を持っている場合にのみ、構造化ツールを使用します。MCP の `content` テキストは意図的にコンパクトになっています。完全なマシン読み取り可能データは `structuredContent` に残ります。

構造化された MCP インストール呼び出しは、`all_agents: true` およびオプションの `target_agents` を渡すことができます。構造化されたルート呼び出しは `target` を渡すことができるため、保存されたターゲットリストが呼び出し元のホストに対して適用されます。

## サポートされているエージェントホスト

| ターゲット | 指示の場所 |
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

ターゲット固有のブリッジテキストを以下でレンダリングします：

```bash
skills-router prompt --target codex
skills-router prompt --target cursor
skills-router prompt --target windsurf
skills-router prompt --target codex --detail full
```

デフォルトのプロンプトはコンパクトであるため、永続的なエージェントの指示にかかるトークンが少なくなります。ドキュメントを生成する場合、または統合をデバッグする場合にのみ `--detail full` を使用してください。

## 設定

`~/.skills-router/config.json` は、以下のような `SkillsRouterConfig` フィールドを上書きできます：

```json
{
  "storage_backend": "memory",
  "workspace_root": "/path/to/workspace",
  "workspace_skill_dirs": [".agents/skills", ".codex/skills", ".cursor/skills"],
  "global_skill_dirs": ["$CODEX_HOME/skills", "~/.codex/skills", "~/.cursor/skills"],
  "pgvector_dsn": "postgresql://user:pass@localhost:5432/skills_router"
}
```

## リリース自動化

リポジトリの CI は、Python、Node ラッパー、およびパッケージビルドを検証します。タグがプッシュされると、ワークフローは npm ラッパーを公開し、GitHub リリースを作成または更新します。リリース説明は対応する `CHANGELOG.md` エントリから生成され、以下へのリンクが追加されます：

- タグ固有の変更履歴
- npm パッケージ：https://www.npmjs.com/package/@the-long-ride/skills-router

## ロードマップ

- [x] コアインストールレビューパイプライン。
- [x] 主要な AI エージェントホスト用のエージェントブリッジ。
- [x] 生成されたルートプランによるフルパッケージインストール。
- [x] ターゲットを意識したルーティングによる一括全エージェントインストール。
- [x] `/skills-router index` の調整と競合に関する推奨。
- [x] `/skills-router refine` による検出とルートのリファイン。
- [x] MCP および CLI を介した動的ルート検索。
- [x] 信頼性低下アラート付きの Registry Watch デーモン。
- [ ] 人間の選択を適用するためのルート選択永続化 API。
- [ ] pgvector ネイティブのプロダクション移行。
- [ ] ルーティング履歴、監査ログ、および競合の決定用ダッシュボード。

## ライセンス

このプロジェクトは、**GNU General Public License (GPLv3)** に基づいてライセンスされています。

**the-long-ride** によって開発されました。
