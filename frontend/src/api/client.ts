/**
 * バックエンド（FastAPI）への通信をまとめた層。
 *
 * ここより上ではURLの組み立てや fetch を書かない。エンドポイントが増減したときに
 * 探す場所を1箇所に保つため。
 */
import type { AtmosphereResponse, DailyPlanResponse } from '../types/weather';
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000/api/v1';

/** 位置情報。取得できなければ null を渡し、バックエンドの既定値（野々市）に任せる */
export interface Coords {
  lat: number;
  lon: number;
}

/** HTTPステータスを保持する例外。呼び出し側が 503（気象データ取得不能）を判別するのに使う */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface RequestOptions {
  coords?: Coords | null;
  signal?: AbortSignal;
}

async function getJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { coords, signal } = options;
  // 位置情報が無いときはパラメータ自体を付けない。付けないとバックエンドの既定値が使われる
  const query = coords ? `?lat=${coords.lat}&lon=${coords.lon}` : '';

  const res = await fetch(`${API_BASE}${path}${query}`, { signal });

  if (!res.ok) {
    // FastAPI は失敗時に {"detail": "..."} を返す。原因の切り分けに直結するので本文を読む
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body && body.detail) detail = String(body.detail);
    } catch {
      // 本文がJSONでない場合（プロキシのエラーページなど）はステータスだけで諦める
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}

/** 気象生データと気圧ストレス指数 */
export function fetchAtmosphere(
  coords: Coords | null,
  signal?: AbortSignal,
): Promise<AtmosphereResponse> {
  return getJson<AtmosphereResponse>('/atmosphere', { coords, signal });
}

/** 体力予算・省エネレベル・提案。レベルの算出はすべてサーバー側で行われる */
export function fetchDailyPlan(
  coords: Coords | null,
  signal?: AbortSignal,
): Promise<DailyPlanResponse> {
  return getJson<DailyPlanResponse>('/daily-plan', { coords, signal });
}

/** 疎通確認。バックエンドが落ちているのか、データが無いだけなのかを切り分けるのに使う */
export function fetchHealth(signal?: AbortSignal): Promise<{ status: string }> {
  return getJson<{ status: string }>('/health', { signal });
}

/**
 * POST 用。getJson と同じくエラー時は ApiError を投げる。
 *
 * これが無かったため Healing.tsx が直接 fetch を書いており、独自の API_BASE を
 * 持つことで上の既定値フォールバックが効かない状態になっていた。
 */
async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const b = (await res.json()) as { detail?: unknown };
      if (b && b.detail) detail = String(b.detail);
    } catch {
      // 本文がJSONでない場合はステータスだけで諦める
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}

/**
 * 夜の吐き出しへの応答。
 *
 * fallback=true は「Gemini を通していない」ことを示す。利用回数の上限に達した場合
 * （docs/design.md §4.8）と生成に失敗した場合の両方で true になり、どちらも 200 で返る。
 * 上限到達を 429 で突き返さないのは意図した仕様なので、200 だから生成された、とは限らない。
 *
 * どちらだったかは reason で分かる。**これは開発者向けであって画面に出すものではない。**
 * 「上限」「制限」「あと何回」を利用者に見せることは §1.2 / §4.8 が禁じている。
 */
export interface ReflectionResponse {
  reply: string;
  model: string | null;
  fallback: boolean;
  /** 'limit'（上限到達） | 'error'（生成失敗） | null（生成できた） */
  reason: 'limit' | 'error' | null;
}

/** 吐き出したテキストを送り、全肯定の応答を受け取る */
export function postReflection(
  text: string,
  level?: number,
  signal?: AbortSignal,
): Promise<ReflectionResponse> {
  return postJson<ReflectionResponse>('/reflection', { text, level }, signal);
}

/**
 * 対話機能を今使えるか。
 *
 * 回数は返らない（blocked と resets_at だけ）。これは意図的な仕様で、
 * 「あと何回」を表示させないためのもの（docs/design.md §1.2 / §4.8）。
 *
 * ★ 現在フロントからは呼んでいない。
 *   2026-08-02 に「遮断中は夜の吐き出しの入力欄を disabled にする」用途で足したが、
 *   実際に文字が打てなくなり撤回した。/reflection は上限に達していても 200 で受け取り
 *   内容を保存する設計（§4.7）なので、**この値を使って入力を塞いではいけない**。
 *   使うとすれば「送信後に定型文だったことを開発者向けログへ出す」程度に留めること。
 */
export interface UsageResponse {
  blocked: boolean;
  resets_at: string;
  message: string | null;
  endpoints: Record<string, { blocked: boolean }>;
}

/** 利用状況の取得。カウントは増えない */
export function fetchUsage(signal?: AbortSignal): Promise<UsageResponse> {
  return getJson<UsageResponse>('/usage', { signal });
}
