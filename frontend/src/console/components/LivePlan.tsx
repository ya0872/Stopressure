/**
 * /daily-plan の結果表示。省エネレベル・体力予算の内訳・提案。
 *
 * ここは描画専用で、レベルや点数の計算は一切しない。判定はすべてサーバー側にある
 * （mockup/index.html にあったJS版の複製は 2026-08-01 に削除済み。復活させないこと）。
 */
import type { DailyPlanResponse } from '../../types/weather';
import { Section } from './primitives';

/**
 * 値の区切り。全角スペースを含むため定数に切り出す。
 * JSXテキストに直接書くと改行が空白として畳み込まれて間隔が崩れ、
 * テンプレートリテラルに直接書くと no-irregular-whitespace に引っかかる。
 */
const SEP = '　・　';

export function LivePlan({ plan, error }: { plan: DailyPlanResponse | null; error: string | null }) {
  if (!plan) {
    return (
      <Section title="本日">
        <div className="empty">
          気象データを取得できませんでした。
          <br />
          {error ?? '読み込んでいます…'}
        </div>
      </Section>
    );
  }

  return (
    <Section title="本日">
      <div className="level-row">
        <span className="level-num">{plan.level}</span>
        <span className="level-name">{plan.level_name}</span>
      </div>
      <div className="headline">{plan.headline}</div>
      <div className="budget-note">
        {`体力予算 ${plan.energy_budget} / 100${SEP}気圧ストレス ${plan.pressure_stress} / 100${SEP}${plan.date}`}
        {plan.stale && `${SEP}保存済みの値`}
      </div>
    </Section>
  );
}

/**
 * 予算の内訳。
 * 未計測の因子はサーバー側で除かれてくるため、ここに 0 点の行は出てこない
 * （0＝計測して負荷なし、null＝未計測 の区別: docs/design.md §7.2.1）。
 */
export function LiveBreakdown({ plan }: { plan: DailyPlanResponse | null }) {
  const notes: string[] = [];
  if (plan) {
    notes.push(
      plan.level_driven_by_pressure
        ? 'このレベルは体力予算ではなく気圧ストレスの下限で決まっています（設計書 §4.2.1）。'
        : 'このレベルは体力予算から決まっています。',
    );
    notes.push(
      plan.google_context_used
        ? 'カレンダー・メール・ToDoを予算に反映しています。'
        : 'Google未連携のため、気象の要因のみで算出しています。',
    );
  }

  return (
    <Section title="体力予算の内訳">
      {!plan ? (
        <div className="empty">—</div>
      ) : plan.breakdown.length === 0 ? (
        <div className="empty">差し引く要因がありません。予算は満額です。</div>
      ) : (
        plan.breakdown.map((b) => (
          <div className="factor" key={b.factor}>
            <div className="factor-head">
              <span>{b.factor}</span>
              {/* 色だけでなく数値でも示す（§8.2） */}
              <span className="factor-cost">
                -{b.cost} <span style={{ opacity: 0.5 }}>/ {b.cap}</span>
              </span>
            </div>
            <div className="bar">
              <div style={{ width: `${Math.min((b.cost / b.cap) * 100, 100)}%` }} />
            </div>
            <div className="factor-detail">{b.detail}</div>
          </div>
        ))
      )}
      {notes.length > 0 && <div className="note">{notes.join(' ')}</div>}
    </Section>
  );
}

/**
 * 提案。
 * チェックボックス相当の要素を置かない。完了・未完了の概念を持ち込まないため
 * （docs/design.md §1.2 の禁止事項。型の側でも done を持たせていない）。
 */
export function LiveSuggestions({ plan }: { plan: DailyPlanResponse | null }) {
  return (
    <Section title={plan?.suggest_title ?? '提案'}>
      {!plan ? (
        <div className="empty">—</div>
      ) : (
        plan.suggestions.map((s) => (
          <div className="suggest" key={s.id}>
            <div className="suggest-text">{s.text}</div>
            <div className="suggest-reason">{s.reason}</div>
          </div>
        ))
      )}
      <div className="note">完了・未完了の概念を持ちません。やらなくても何も起きません。</div>
    </Section>
  );
}
