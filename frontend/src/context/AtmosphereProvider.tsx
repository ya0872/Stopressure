import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { fetchAtmosphere, fetchDailyPlan } from '../api/client';
import { useGeolocation } from '../hooks/useGeolocation';
import { AtmosphereContext } from './atmosphereContext';
import type { AtmosphereState } from './atmosphereContext';

/**
 * 自動更新の間隔。気象は1時間粒度、Google連携はバックエンド側で5分キャッシュされるため、
 * これより短くしても返る値は変わらない（mockup/index.html と同じ間隔）。
 */
const REFRESH_MS = 5 * 60 * 1000;

const INITIAL: AtmosphereState = {
  atmosphere: null,
  plan: null,
  isLoading: true,
  error: null,
  updatedAt: null,
};

export function AtmosphereProvider({ children }: { children: ReactNode }) {
  const coords = useGeolocation();
  const [state, setState] = useState<AtmosphereState>(INITIAL);

  // coords は最初 null で、位置情報が取れた時点で入る。
  // 許可ダイアログを待たずにまず既定地点で取得し、座標が確定したら取り直す。
  // 決着を待ってから通信すると、拒否・タイムアウト時に最大10秒間なにも表示されない。
  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      try {
        // 2本を並行で取る。順に待つと表示が2段階で入れ替わり、値の対応が読み取りにくくなる
        const [atmosphere, plan] = await Promise.all([
          fetchAtmosphere(coords, controller.signal),
          fetchDailyPlan(coords, controller.signal),
        ]);
        setState({ atmosphere, plan, isLoading: false, error: null, updatedAt: new Date() });
      } catch (e) {
        // 中断はエラーではないので握りつぶす（座標確定時の取り直しとアンマウントで起きる）
        if (controller.signal.aborted) return;
        console.error('バックエンドからの取得に失敗しました:', e);
        // 前回取得できた値は残したまま error を立てる。値が消えるより古い値のほうがましなため
        setState((prev) => ({ ...prev, isLoading: false, error: e as Error }));
      }
    };

    void load();

    // 非表示のタブでは更新しない。放置されたタブが5分ごとにAPIを叩き続けるのを避ける
    const timer = setInterval(() => {
      if (!document.hidden) void load();
    }, REFRESH_MS);

    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [coords]);

  return <AtmosphereContext.Provider value={state}>{children}</AtmosphereContext.Provider>;
}
