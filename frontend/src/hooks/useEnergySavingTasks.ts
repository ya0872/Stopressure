import { useAtmosphere } from '../context/atmosphereContext';
import type { EnergyTask } from '../types/weather';

/**
 * 本日の提案を取り出す（GET /daily-plan の suggestions）。
 *
 * 何をどれだけ出すかはサーバー側の planner.pick_suggestions が決めている
 * （レベル以下の負荷のものだけ・最大3件・レベル5では1件）。ここで絞り込みや
 * 並べ替えを足すと、その規則が2箇所に分かれるので足さないこと。
 *
 * title は見出し文言。レベルによって変わるためサーバーから受け取る。
 */
export function useEnergySavingTasks(): {
  tasks: EnergyTask[];
  title: string;
  isLoading: boolean;
} {
  const { plan, isLoading } = useAtmosphere();

  // SuggestionItem を画面の語彙へ置き換えるだけ。完了フラグは足さない（§1.2）
  const tasks: EnergyTask[] = (plan?.suggestions ?? []).map((s) => ({
    id: s.id,
    title: s.text,
    description: s.reason,
  }));

  return { tasks, title: plan?.suggest_title ?? '本日の目標', isLoading };
}
