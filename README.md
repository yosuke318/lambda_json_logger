# lambda_json_logger

AWS Lambda のログを 1 行 1 JSON で出力する小さなロギングライブラリ。

## なぜ作ったか

Lambda のデフォルトのログ出力はテキスト形式で、リクエスト ID が行頭のプレフィックスに
埋め込まれた状態になっている。CloudWatch Logs Insights から見るとこれは単なる文字列の
一部でしかないため、`filter aws_request_id = "..."` のようなフィールド指定でのクエリが
できず、`parse` を書かないと絞り込めない。

同じくリクエストの内容（event）もデフォルトのログには出てこないので、
「このエラーはどんなリクエストで起きたのか」を後から追えない。

このライブラリは `logging` の Formatter を差し替えて、リクエスト ID・環境名・event を
**JSON のトップレベルフィールドとして** 出力する。Logs Insights は JSON ログを自動で
パースするので、そのままフィールドとしてクエリできる。

```
fields @timestamp, message, function_name
| filter aws_request_id = "8f7e6d5c-..."
| filter level = "ERROR"
| sort @timestamp desc
```

event はネストしたキーもドット記法で辿れる。

```
fields @timestamp, message, event.httpMethod, event.path
| filter level = "ERROR" and event.path like /^\/orders/
| sort @timestamp desc
```

## インストール

Lambda Layer として使う場合は後述の「Layer のビルド」を参照。
ローカルやテストから使う場合は pip で直接入れる。

```bash
pip install -e .
# または
pip install -r tests/requirements.txt
```

## 使い方

```python
from lambda_json_logger import getLambdaJsonLoggerInstance


def lambda_handler(event, context):
    logger = getLambdaJsonLoggerInstance(context=context, stage="dev", event=event)
    logger.info("processing started")
    return {"statusCode": 200}
```

出力:

```json
{"time": "2026-08-16 12:34:56,789", "level": "INFO", "message": "processing started", "function_name": "lambda_handler", "module": "app", "aws_request_id": "8f7e6d5c-...", "stage": "dev", "event": {"path": "/health", "httpMethod": "GET"}}
```

`event` を省けば `event` キーは出力されない。ログ量とのトレードオフは
「注意点」を参照。

例外を記録する場合は `logger.exception()`（または `exc_info=True`）を使うと、
トレースバックが `exception` フィールドに入る。

```python
try:
    charge(order)
except PaymentError:
    logger.exception("failed to charge order")
```

```json
{"time": "...", "level": "ERROR", "message": "failed to charge order", "function_name": "lambda_handler", "module": "app", "aws_request_id": "8f7e6d5c-...", "stage": "dev", "exception": "Traceback (most recent call last):\n  File \"app.py\", line 12, in lambda_handler\n    charge(order)\nPaymentError: card declined"}
```

### 引数

| 引数 | デフォルト | 説明 |
| --- | --- | --- |
| `level` | `DEBUG` | ログレベル。`logging` の定数、または `LOG_LEVELS` の値 |
| `context` | `None` | Lambda の context オブジェクト。`aws_request_id` の取得のみに使う |
| `stage` | `None` | 環境名（`dev` / `prd` など）。全ログ行に付与される |
| `event` | `None` | Lambda の event。渡すと全ログ行に `event` フィールドが付く |

`getLambdaJsonLoggerInstance()` はハンドラを 1 つだけ作り、呼び出しのたびに
`context` / `stage` / `event` を差し替える。ウォームスタートで同じコンテナが次の
リクエストを処理する場合も、ハンドラの先頭で呼び直せば正しいリクエスト ID になる。

### 出力フィールド

| フィールド | 由来 |
| --- | --- |
| `time` | `Formatter.formatTime()` |
| `level` | `record.levelname` |
| `message` | `record.getMessage()` |
| `function_name` | `record.funcName`（ログを呼んだ関数名。Lambda の関数名ではない） |
| `module` | `record.module` |
| `aws_request_id` | `context.aws_request_id`（`context` 未指定なら `null`） |
| `stage` | 引数の `stage` をそのまま |
| `event` | 引数の `event` をそのまま。**未指定のときはキー自体が出ない** |
| `exception` | `record.exc_info` のトレースバック。**例外情報がないときはキー自体が出ない** |

JSON 化できない値が `event` に混ざっていても `default=str` で文字列化されるので、
ログ呼び出しが例外で落ちることはない。日本語は `ensure_ascii=False` でエスケープせず
そのまま出力する。

## Layer のビルド

Lambda Layer は `python/lib/python<version>/site-packages/` の階層を要求する。

```bash
pip install . --target python/lib/python3.12/site-packages
zip -r layer.zip python
```

生成された `layer.zip` を Layer としてアップロードし、Lambda 関数にアタッチする。
`python/` と `layer.zip` はビルド成果物なので `.gitignore` 済み。

## テスト

`lambda_json_logger` が import できる状態が前提。

```bash
pytest tests/test.py
# または
PYTHONPATH=. python tests/test.py
```

## 注意点

- **`event` を渡すと全ログ行に載る。** CloudWatch の課金は取り込みバイト数に対して
  かかるので、大きな event を渡したまま 1 リクエストで何十行も出すとログ量が膨らむ。
  量が気になる場合は `event` を渡さず、開始時に 1 行だけ
  `logger.info(json.dumps(event))` で出し、あとは `aws_request_id` で突き合わせる形にする。
- **ロガーはプロセス内で共有される。** 名前が固定（`"lambda_json_logger"`）なので、
  ハンドラの先頭で毎回 `getLambdaJsonLoggerInstance()` を呼んで、そのリクエストの
  `context` に差し替えること。呼ばないと前のリクエストの ID のまま出力される。
- **トレースバックは 1 行に収まる。** `exception` フィールドの中で改行は `\n` として
  エスケープされるため、CloudWatch 上で複数イベントに分割されない。読むときは
  Logs Insights の詳細表示か `fields exception` で展開する。

## 補足

AWS は 2023 年 11 月に Lambda の Advanced Logging Controls を追加しており、関数設定で
ログ形式を JSON にすると `requestId` や `level` を含む構造化ログがランタイム側で出る。
新規に組むならまずそちらで足りるか確認するとよい。このライブラリは任意のフィールド
（`stage` など）を足したい場合や、その機能を使わない構成で有効。
