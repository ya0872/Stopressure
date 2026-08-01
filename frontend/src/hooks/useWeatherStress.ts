import { useAtmosphere } from '../context/atmosphereContext';
import type { AtmosphereResponse } from '../types/weather';

/**
 * 気象生データと気圧ストレス指数を取り出す（GET /atmosphere）。
 *
 * 通信自体は AtmosphereProvider が行う。ここは取り出すだけで、閾値判定や段階分けはしない。
 * 気圧ストレスの段階（何点から「警戒」か）は backend/app/config/thresholds.yaml が
 * 唯一の定義であり、画面側に写しを作らないこと（CLAUDE.md）。
 *
 * levelDrivenByPressure は /daily-plan の level_driven_by_pressure。
 * 「今日の省エネレベルは体力予算ではなく気圧で決まった」＝「今日は気圧のせい」と
 * 言い切ってよい日かどうかの判定で、これもサーバー側の計算結果をそのまま使う。
 */
export function useWeatherStress(): {
  data: AtmosphereResponse | null;
  levelDrivenByPressure: boolean;
  isLoading: boolean;
  error: Error | null;
} {
  const { atmosphere, plan, isLoading, error } = useAtmosphere();
  return {
    data: atmosphere,
    levelDrivenByPressure: plan?.level_driven_by_pressure ?? false,
    isLoading,
    error,
  };
}
