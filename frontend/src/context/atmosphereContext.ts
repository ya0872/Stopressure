import { createContext, useContext } from 'react';
import type { AtmosphereResponse, DailyPlanResponse } from '../types/weather';

/**
 * 画面全体で共有する取得結果。
 *
 * /atmosphere と /daily-plan は同じ観測値から作られるため、まとめて1回で取り、
 * 「気圧だけ新しくてレベルは古い」という食い違いが起きないようにする。
 * 位置情報の許可ダイアログを複数回出さないためでもある。
 */
export interface AtmosphereState {
  atmosphere: AtmosphereResponse | null;
  plan: DailyPlanResponse | null;
  isLoading: boolean;
  /** 取得に失敗した理由。モックデータで代替はしない（偽の値を本物として見せないため） */
  error: Error | null;
  /** 最後に取得できた時刻 */
  updatedAt: Date | null;
}

export const AtmosphereContext = createContext<AtmosphereState | null>(null);

export function useAtmosphere(): AtmosphereState {
  const state = useContext(AtmosphereContext);
  if (!state) {
    throw new Error('useAtmosphere は AtmosphereProvider の内側でのみ使用できます');
  }
  return state;
}
