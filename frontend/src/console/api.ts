/**
 * コンソール専用のバックエンド通信層。
 *
 * src/api/client.ts と分けてある理由:
 *   あちらは「失敗＝例外」で、画面は値が取れた前提で描く。こちらは逆に、
 *   「バックエンドが落ちている」「保存に失敗した」こと自体が表示対象である。
 *   例外にすると try/catch が全コンポーネントに散るため、結果を判別可能な union で返す。
 *   気象・プラン取得もここに置くのは、同じ扱い（エラーも状態として描く）にするため。
 */
import type { AtmosphereResponse, DailyPlanResponse } from '../types/weather';
import type {
  ContextResponse,
  GeminiStatus,
  GeminiUpdate,
  GoogleStatus,
  GoogleUpdate,
  TestResult,
} from './types';

/**
 * ベースURL。frontend/.env の VITE_API_BASE で差し替えられる。
 *
 * 既定を固定IPではなく location.hostname にしているのは、localhost と 127.0.0.1 が
 * 別オリジンとして扱われるため。開いたホストに合わせないと CORS で弾かれる
 * （backend/app/main.py の CORS_ORIGINS は両方を許可しているので、揃えれば通る）。
 */
const API_BASE =
  import.meta.env.VITE_API_BASE ?? `http://${location.hostname || '127.0.0.1'}:8000/api/v1`;

/**
 * 認可のリダイレクト先は Cloud Console に localhost で登録する前提のため、
 * ここだけは location.hostname に追随させず固定する。127.0.0.1 で開いていても
 * 認可は localhost へ飛ばさないと redirect_uri_mismatch になる。
 */
export const LOGIN_URL = 'http://localhost:8000/api/v1/auth/google/login';
export const REDIRECT_URI = 'http://localhost:8000/api/v1/auth/google/callback';

/** 取得結果。3つの状態を型で区別し、呼び出し側に分岐を強制する */
export type ApiResult<T> =
  | { kind: 'ok'; data: T }
  | { kind: 'error'; status: number; detail: string }
  /** バックエンドに到達できない（uvicorn 未起動・ポート違い） */
  | { kind: 'unreachable' };

/** FastAPI のエラー本文。detail は文字列のことも、バリデーション配列のこともある */
interface ErrorBody {
  detail?: string | { msg?: string }[];
}

function detailOf(status: number, body: unknown): string {
  const d = (body as ErrorBody | null)?.detail;
  if (!d) return `エラー（HTTP ${status}）`;
  if (typeof d === 'string') return d;
  return d.map((e) => e.msg ?? JSON.stringify(e)).join(' / ');
}

async function request<T>(
  path: string,
  method: 'GET' | 'PUT' | 'POST' | 'DELETE' = 'GET',
  body?: unknown,
): Promise<ApiResult<T>> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    // fetch 自体が失敗するのは接続不能のとき。HTTPエラーとは区別する
    return { kind: 'unreachable' };
  }

  // 204 や空ボディがありうるので、JSON パースは中身がある場合だけ
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      // プロキシのHTMLエラーページなど。ステータスだけで判断する
      parsed = null;
    }
  }

  if (!res.ok) return { kind: 'error', status: res.status, detail: detailOf(res.status, parsed) };
  return { kind: 'ok', data: parsed as T };
}

/** 位置情報。取得できなければ null を渡し、バックエンドの既定値（野々市）に任せる */
export interface Coords {
  lat: string;
  lon: string;
}

function locParams(coords: Coords | null): string {
  return coords ? `?lat=${coords.lat}&lon=${coords.lon}` : '';
}

// --- 疎通 --------------------------------------------------------------------

export const getHealth = () => request<{ status: string }>('/health');

// --- Gemini ------------------------------------------------------------------

export const getGemini = () => request<GeminiStatus>('/settings/gemini');
export const putGemini = (body: GeminiUpdate) => request<GeminiStatus>('/settings/gemini', 'PUT', body);
export const deleteGemini = () => request<GeminiStatus>('/settings/gemini', 'DELETE');
export const getGeminiModels = () => request<string[]>('/settings/gemini/models');
export const testGemini = () => request<TestResult>('/settings/gemini/test', 'POST');

// --- Google ------------------------------------------------------------------

export const getGoogle = () => request<GoogleStatus>('/settings/google');
export const putGoogle = (body: GoogleUpdate) => request<GoogleStatus>('/settings/google', 'PUT', body);
export const unlinkGoogle = () => request<GoogleStatus>('/settings/google', 'DELETE');
export const testGoogle = () => request<TestResult>('/settings/google/test', 'POST');

// --- 実データ ----------------------------------------------------------------

export const getContext = () => request<ContextResponse>('/context');
export const getAtmosphere = (coords: Coords | null) =>
  request<AtmosphereResponse>('/atmosphere' + locParams(coords));
export const getDailyPlan = (coords: Coords | null) =>
  request<DailyPlanResponse>('/daily-plan' + locParams(coords));
