/**
 * 接続状態タブが使う実データの取得。
 *
 * まず /health で疎通を確かめ、通ってから4つのエンドポイントを並行で取る。
 * 順に待つと表示が段階的に入れ替わり、値の対応が読み取りにくくなるため。
 *
 * 個々の取得失敗はエラーとして投げず状態として保持する。ここは「どこまで動いているか」を
 * 確認するための画面なので、落ちていること自体が表示すべき情報である。
 */
import { useCallback, useEffect, useState } from 'react';
import * as api from '../api';
import type { Coords } from '../api';
import type { ContextResponse, GoogleStatus } from '../types';
import type { AtmosphereResponse, DailyPlanResponse } from '../../types/weather';

export type BackendState = 'checking' | 'up' | 'down';

export interface LiveData {
  backend: BackendState;
  plan: DailyPlanResponse | null;
  /** プランを取得できなかった理由。取得できていれば null */
  planError: string | null;
  atmosphere: AtmosphereResponse | null;
  googleStatus: GoogleStatus | null;
  context: ContextResponse | null;
}

const EMPTY: LiveData = {
  backend: 'checking',
  plan: null,
  planError: null,
  atmosphere: null,
  googleStatus: null,
  context: null,
};

/**
 * 4つのエンドポイントを取得して画面用の形にまとめる。
 *
 * ここに状態更新を混ぜないのは、effect の本体で setState を同期的に呼ばないため
 * （react-hooks/set-state-in-effect）。取得と反映を分けておくと、応答が返る前に
 * アンマウントされた場合に結果を捨てるのも簡単になる。
 */
async function fetchAll(at: Coords | null): Promise<LiveData> {
  const health = await api.getHealth();
  if (health.kind !== 'ok') {
    // バックエンドが落ちているときは、他を叩いても同じ失敗が並ぶだけなので打ち切る
    return { ...EMPTY, backend: 'down' };
  }

  const [plan, atmosphere, googleStatus, context] = await Promise.all([
    api.getDailyPlan(at),
    api.getAtmosphere(at),
    api.getGoogle(),
    api.getContext(),
  ]);

  return {
    backend: 'up',
    plan: plan.kind === 'ok' ? plan.data : null,
    planError:
      plan.kind === 'ok' ? null : plan.kind === 'error' ? plan.detail : '接続できませんでした',
    atmosphere: atmosphere.kind === 'ok' ? atmosphere.data : null,
    googleStatus: googleStatus.kind === 'ok' ? googleStatus.data : null,
    context: context.kind === 'ok' ? context.data : null,
  };
}

export function useLiveData() {
  const [data, setData] = useState<LiveData>(EMPTY);
  const [coords, setCoords] = useState<Coords | null>(null);
  /** 位置情報ボタンの表示。取得中・取得済み・拒否で文言が変わる */
  const [locateLabel, setLocateLabel] = useState('現在地を使う');
  const [locating, setLocating] = useState(false);

  // 初回と、位置情報が確定したときに取り直す
  useEffect(() => {
    let cancelled = false;
    void fetchAll(coords).then((next) => {
      if (!cancelled) setData(next);
    });
    return () => {
      cancelled = true;
    };
  }, [coords]);

  /** 手動の再取得。押した直後に反応が見えるよう、いったん確認中へ戻す */
  const reload = useCallback(() => {
    setData((prev) => ({ ...prev, backend: 'checking' }));
    void fetchAll(coords).then(setData);
  }, [coords]);

  /**
   * 現在地を取得して取り直す。
   * 拒否・失敗時はバックエンドの既定値（野々市市）のまま使う（docs/design.md §11 #7）。
   */
  const locate = useCallback(() => {
    if (!navigator.geolocation) {
      setLocateLabel('この環境では取得できません');
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const next = {
          lat: pos.coords.latitude.toFixed(4),
          lon: pos.coords.longitude.toFixed(4),
        };
        setCoords(next);          // coords が変わると useEffect が取り直す
        setLocateLabel(`現在地 ${next.lat}, ${next.lon}`);
        setLocating(false);
      },
      () => {
        setLocateLabel('現在地を使えません');
        setLocating(false);
      },
    );
  }, []);

  return { data, coords, reload, locate, locateLabel, locating };
}
