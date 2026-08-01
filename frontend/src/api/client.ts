/**
 * バックエンド（FastAPI）への通信をまとめた層。
 *
 * ここより上ではURLの組み立てや fetch を書かない。エンドポイントが増減したときに
 * 探す場所を1箇所に保つため。
 */
import type { AtmosphereResponse, DailyPlanResponse } from '../types/weather';

/**
 * ベースURL。frontend/.env の VITE_API_BASE で差し替える。
 *
 * 既定を localhost ではなく 127.0.0.1 にしているのは、Windows のブラウザが localhost を
 * 先に ::1（IPv6）へ解決するのに対し、uvicorn は --host 127.0.0.1 で待ち受けているため。
 * fetch は IPv4 へフォールバックするが、無駄な接続失敗を挟まないよう明示しておく。
 */
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
