/**
 * 設定・接続状態コンソールが扱うバックエンドのレスポンス型。
 *
 * ここはサーバー側 Pydantic モデルの写しであり、派生値を足す場所ではない。
 * 対応関係:
 *   GeminiStatus / GoogleStatus / TestResult <- backend/app/routers/settings.py
 *   ContextResponse                          <- backend/app/routers/context.py
 * フィールド名は snake_case のまま保つ（src/types/weather.ts と同じ方針）。
 *
 * 気象まわりの型（AtmosphereResponse / DailyPlanResponse）は Dashboard と共通なので
 * ../types/weather.ts を再利用する。こちらで定義し直さない。
 */

/** GET /settings/gemini — 平文キーは含まれない。masked_key だけが返る */
export interface GeminiStatus {
  configured: boolean;
  /** 例: AIzaSy…3f9c。平文を返すAPIは存在しない */
  masked_key: string | null;
  /** 'settings'（この画面で保存） | 'env'（環境変数） | null（未登録） */
  source: string | null;
  model: string;
  /** google-genai が import できるか */
  sdk_installed: boolean;
}

/** PUT /settings/gemini のリクエスト。省略した項目は既存値を維持する */
export interface GeminiUpdate {
  api_key?: string;
  model?: string;
}

/** GET /settings/google — client_secret は含まれない */
export interface GoogleStatus {
  configured: boolean;
  linked: boolean;
  /** 認可URLに載る値なので平文で返る */
  client_id: string | null;
  scopes: string[];
  /** ISO8601(UTC)。未連携なら null */
  linked_at: string | null;
  /** 体力予算へ反映するか。連携を保ったまま反映だけ止められる */
  use_context: boolean;
  login_url: string;
}

/** PUT /settings/google のリクエスト。指定した項目だけが更新される */
export interface GoogleUpdate {
  client_id?: string;
  client_secret?: string;
  use_context?: boolean;
}

/** POST /settings/{gemini,google}/test の結果 */
export interface TestResult {
  ok: boolean;
  message: string;
}

/**
 * GET /context — Google連携から得た当日の負荷。
 *
 * null は「未計測」であって 0 ではない。0 は「計測して負荷なし」を意味する。
 * 表示の際にこの2つを混同しないこと（docs/design.md §7.2.1）。
 */
export interface ContextResponse {
  linked: boolean;
  use_context: boolean;
  busy_hours: number | null;
  actionable_mail_count: number | null;
  open_task_count: number | null;
  /** 項目ごとの取得失敗の理由。3つのAPIは独立に失敗しうる */
  warnings: string[];
}

/** client_secret.json（Cloud Console がシークレット作成時に配布するもの）の形 */
export interface ClientSecretJson {
  web?: { client_id?: string; client_secret?: string };
  /** デスクトップ用クライアント。このアプリでは使えない */
  installed?: { client_id?: string; client_secret?: string };
  client_id?: string;
  client_secret?: string;
}
