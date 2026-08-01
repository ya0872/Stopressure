/**
 * バックエンドのレスポンス型。
 *
 * ここはサーバー側の Pydantic モデルの写しであり、独自の派生値を足す場所ではない。
 * 対応関係:
 *   AtmosphereResponse <- backend/app/routers/atmosphere.py
 *   DailyPlanResponse  <- backend/app/routers/plan.py
 * フィールド名は snake_case のまま保つ（変換を挟むと、どちらの名前で書かれているのか
 * 追えなくなり、サーバー側の変更に追随できなくなるため）。
 */

/** 気圧ストレス指数の内訳（0〜100、大きいほど身体負荷が高い） */
export interface StressDetail {
  score: number;
  /** 直近6時間の気圧変化(hPa)。負が低下 */
  delta_6h: number;
  /** 直近24時間の気圧変化(hPa) */
  delta_24h: number;
  /** これから6時間の予報変化(hPa) */
  delta_next6h: number;
}

/** 気圧グラフ用の系列。過去24h〜予報12h */
export interface ChartSeries {
  /** JSTのローカル時刻 */
  times: string[];
  pressure: number[];
  /** times のうち現在時刻に対応する位置 */
  now_index: number;
}

/** GET /atmosphere */
export interface AtmosphereResponse {
  latitude: number;
  longitude: number;
  observed_at: string;
  /** open-meteo | jma */
  source: string;
  /** 通信に失敗し、保存済みの値で代替したか */
  stale: boolean;
  /** 海面更正気圧(hPa) */
  pressure: number;
  temperature: number;
  humidity: number;
  /** 前日同時刻比(℃) */
  temp_delta_vs_yesterday: number;
  discomfort_index: number;
  stress: StressDetail;
  chart: ChartSeries;
}

/** 体力予算の内訳1行 */
export interface BreakdownItem {
  factor: string;
  cost: number;
  cap: number;
  detail: string;
}

/**
 * 提案1件。
 * 完了状態を表すフィールドは持たない。チェックボックスの禁止（docs/design.md §1.2）は
 * 型の段階で守る。UI側で done フラグを足さないこと。
 */
export interface SuggestionItem {
  id: string;
  text: string;
  reason: string;
}

/** GET /daily-plan */
export interface DailyPlanResponse {
  date: string;
  /** 0〜100。小さいほど余裕がない */
  energy_budget: number;
  /** 省エネレベル 1〜5 */
  level: number;
  level_name: string;
  headline: string;
  suggest_title: string;
  /** レベルが体力予算ではなく気圧ストレスの下限で決まったか（§4.2.1） */
  level_driven_by_pressure: boolean;
  pressure_stress: number;
  stale: boolean;
  /** カレンダー・メール・ToDoを予算に反映したか。未連携なら false */
  google_context_used: boolean;
  breakdown: BreakdownItem[];
  suggestions: SuggestionItem[];
}

/** 提案の表示用。SuggestionItem を画面の語彙へ置き換えただけのもの */
export interface EnergyTask {
  id: string;
  title: string;
  description?: string;
}
