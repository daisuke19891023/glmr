# GLMR ユーザーマニュアル（日本語）

## 概要

GLMR（GitLab Merge Request Metrics Toolkit）は、GitLab のマージリクエストデータを収集し、オフライン分析用に生データを保存、さらに集計レポートを生成してダッシュボードへ出力できるツールキットです。本マニュアルでは、日常的な運用に必要なインストール、設定、操作、保守方法を説明します。

## システム要件

- Python 3.13 以上
- `api` スコープを含む GitLab の個人アクセストークン
- 実行ホストから GitLab API へアクセスできるネットワーク
- 依存関係管理に使用する [uv](https://github.com/astral-sh/uv)
- 任意: 自動収集を行う cron などのスケジューラ

## インストール手順

1. リポジトリをクローンし、プロジェクトディレクトリに移動します。
2. 依存関係を同期します。
   ```bash
   uv sync --extra dev
   ```
3. `uv run` を付けずにコマンドを実行したい場合は、uv が作成した仮想環境を有効化します（任意）。

## 設定

1. サンプル環境変数ファイルをコピーします。
   ```bash
   cp .env.example .env
   ```
2. `.env` を編集し、GitLab 環境に合わせて値を更新します。

| 変数名 | 説明 |
| --- | --- |
| `GLMR_GITLAB_API_BASE` | GitLab REST API のベース URL（既定値: `https://gitlab.com/api/v4`）。 |
| `GLMR_GITLAB_TOKEN` | 認証に使用する `api` スコープ付き個人アクセストークン。 |
| `GLMR_GROUP_ID_OR_PATH` | 収集対象となる GitLab グループまたはプロジェクトの ID もしくはフルパス。 |
| `GLMR_REPORT_SINCE` | 対象に含める最古のマージリクエストを示す ISO 8601 タイムスタンプ。 |
| `GLMR_MAX_CONCURRENCY` | コレクタが同時に発行する API リクエスト数の上限（レート制限に合わせて調整）。 |
| `GLMR_PER_PAGE` | API ページネーションのページサイズ（既定値は 100）。 |
| `GLMR_COMMENT_DEDUP_MODE` | コメントの重複統合方法（`author`、`thread`、`none` など）。 |
| `GLMR_LANG_PATTERNS_FILE` | 言語別レビューパターンの上書き設定ファイルへのパス（任意）。 |
| `GLMR_CACHE_DIR` | 取得した JSONL ペイロードを保存するディレクトリ（既定値: `data/raw/mr`）。 |

> **ヒント:** 新しい設定キーを追加した場合は `.env.example` も更新し、オンボーディングを容易に保ちましょう。

## データディレクトリ

- `data/raw/mr/`: 取得したマージリクエストの JSONL キャッシュ。
- `data/agg/report.json`: 集計済みのメトリクス出力。`render` コマンドが利用します。
- `public/`: `render` コマンドが生成する HTML/JS/アセット群。

これらのディレクトリが存在し、CLI を実行するユーザーが書き込み権限を持つことを確認してください。必要に応じて `.env` で出力先を変更できます。

## CLI の実行

再現性のある環境で Typer CLI を実行するには `uv run` を利用します。

```bash
uv run glmr --help
```

代表的なワークフロー:

1. **データ収集**
   ```bash
   uv run glmr collect
   ```
   マージリクエスト、ディスカッション、ノート、レビュアー情報を取得して JSONL キャッシュに保存します。

2. **メトリクス集計**
   ```bash
   uv run glmr aggregate
   ```
   プロジェクトおよび個人単位の指標を算出し、`data/agg/report.json` に保存します。

3. **レポートのレンダリング**
   ```bash
   uv run glmr render
   ```
   `public/` 配下に共有用の静的アセットを生成します。

4. **設定の検証**
   ```bash
   uv run glmr doctor
   ```
   環境変数と GitLab API への接続を確認します。

## スケジューリングと自動化

メトリクスを最新に保つために、`collect` と `aggregate` を定期的に実行する cron ジョブなどを設定してください。

```cron
0 * * * * cd /path/to/glmr && uv run glmr collect && uv run glmr aggregate
```

自動ジョブが失敗した場合に備え、終了コードや出力ファイルの状態を監視することを推奨します。

## 保守とトラブルシューティング

- **トークンの更新:** `GLMR_GITLAB_TOKEN` の有効期限前に更新して認証エラーを防ぎます。
- **レート制限:** GitLab API から 429 が返る場合は `GLMR_MAX_CONCURRENCY` を下げるか、実行間隔を広げます。
- **データのリセット:** 新規に収集し直したい場合は `data/raw/mr/` や `data/agg/` を削除または退避した後に `collect` を再実行します。
- **設定確認:** 設定変更後は `uv run glmr doctor` を実行して接続状況を検証します。
- **ログ確認:** CLI は標準出力・標準エラーにログを出力します。自動実行時はログを保存し、監査や問題解析に備えてください。

## ヘルプとフィードバック

- 最新の設計情報やタスクの詳細はリポジトリ内の `docs/` を参照してください。
- 不具合や不足しているメトリクスを見つけた場合は、内部の課題管理ツールに報告してください。
- 新しいコマンドや設定を追加した際は、利用者の理解を保つためにマニュアルを更新しましょう。
