import { useEffect, useState } from 'react';
import './dashboard.css';
import { AtmosphereProvider } from './context/AtmosphereProvider';
import { useAtmosphere } from './context/atmosphereContext';
import { WeatherStressWidget } from './components/weather/WeatherStressWidget';
import { EnergySavingTaskWidget } from './components/weather/EnergySavingTaskWidget';
import { PressureChart } from './components/weather/PressureChart';

type ViewName = 'home' | 'enviroment' | 'reflect' | 'settings';

/** 省エネレベルごとの色相。mockup/index.html と同じ値に揃える */
const LEVEL_HUE: Record<number, number> = { 1: 150, 2: 190, 3: 215, 4: 245, 5: 272 };

/**
 * 体力予算と気圧ストレスの区切り。全角空白を挟む。
 * ソースに全角空白を直接書くと ESLint の no-irregular-whitespace に触れるため、
 * エスケープで持つ。
 */
const BUDGET_SEP = '\u3000・\u3000';

/**
 * レベルに応じて差し色を差し替える。
 * ライト環境では暗い差し色がコントラストを強めすぎるため、明度を反転させる。
 */
function useAccent(level: number | undefined) {
  useEffect(() => {
    const hue = LEVEL_HUE[level ?? 3] ?? 215;
    const media = window.matchMedia('(prefers-color-scheme: light)');

    const apply = () => {
      const root = document.documentElement.style;
      const light = media.matches;
      root.setProperty('--accent', light ? `hsl(${hue}, 34%, 42%)` : `hsl(${hue}, 30%, 60%)`);
      root.setProperty('--accent-dim', light ? `hsl(${hue}, 30%, 80%)` : `hsl(${hue}, 22%, 30%)`);
    };

    apply();
    media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [level]);
}

/** バックエンドは改行を含まない平文を返すため、1文ごとに折る */
function headlineLines(text: string): string[] {
  return text.split(/(?<=。)/).filter((s) => s.length > 0);
}

const DashboardView = () => {
  const [activeView, setActiveView] = useState<ViewName>('home');
  const { atmosphere, plan, isLoading, error, updatedAt } = useAtmosphere();

  useAccent(plan?.level);

  const tabs: { key: ViewName; label: string }[] = [
    { key: 'home', label: '今日' },
    { key: 'enviroment', label: '環境' },
    { key: 'reflect', label: '夜の吐き出し' },
    { key: 'settings', label: '設定' },
  ];

  return (
    <div className="wrap">
      <header>
        <div className="title">低気圧のすゝめ</div>
        <div className="subtitle">ATMOSPHERE STUDIO</div>
      </header>

      <nav className="dashboard-nav">
        {tabs.map((t) => (
          <button
            key={t.key}
            data-view={t.key}
            aria-current={activeView === t.key}
            onClick={() => setActiveView(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* 取得に失敗したときは、値を捏造せず理由と復旧手順を出す */}
      {error && !plan && (
        <div className="notice">
          バックエンドからデータを取得できませんでした。（{error.message}）
          <br />
          <code>cd backend; python -m uvicorn app.main:app --reload --port 8000</code>{' '}
          が動作しているか確認してください。
        </div>
      )}
      {error && plan && (
        <div className="notice">
          最新のデータを取得できませんでした。表示中の値は{' '}
          {updatedAt ? updatedAt.toLocaleTimeString('ja-JP') : '前回'} 時点のものです。
        </div>
      )}
      {plan?.stale && (
        <div className="notice">
          気象サービスに接続できなかったため、保存済みの観測値で算定しています。
        </div>
      )}

      {/* ========== ホーム ========== */}
      <div className={`view ${activeView === 'home' ? 'active' : ''}`} id="view-home">
        <div className="level-block">
          <div className="level-label">本日の省エネ度</div>
          <div className="level-ring">
            <div className="level-num">{plan ? plan.level : '—'}</div>
            <div className="level-name">{plan ? plan.level_name : '算定中'}</div>
          </div>
          <div className="headline">
            {plan
              ? headlineLines(plan.headline).map((line, i) => <div key={i}>{line}</div>)
              : isLoading
                ? 'データを読み込んでいます...'
                : '算定できませんでした。'}
          </div>
          <div className="budget-note">
            {plan
              // 区切りは全角空白。エスケープで書くのは no-irregular-whitespace を避けるため
              ? `体力予算 ${plan.energy_budget} / 100${BUDGET_SEP}気圧ストレス ${plan.pressure_stress} / 100`
              : ''}
          </div>
        </div>

        <section>
          <div className="sec-title">体力予算の内訳</div>
          {plan && plan.breakdown.length > 0 ? (
            plan.breakdown.map((f) => (
              <div className="factor" key={f.factor}>
                <div className="factor-head">
                  <span>{f.factor}</span>
                  {/* 数値を必ず併記する。棒の長さだけに情報を持たせない（§8.2） */}
                  <span className="factor-cost">
                    −{f.cost} / 上限 {f.cap}
                  </span>
                </div>
                <div className="factor-bar">
                  <i style={{ width: `${f.cap > 0 ? Math.min(100, (f.cost / f.cap) * 100) : 0}%` }} />
                </div>
                <div className="factor-detail">{f.detail}</div>
              </div>
            ))
          ) : (
            <p className="widget-note">
              {plan ? '差し引かれた要素はありません。' : '内訳を取得できていません。'}
            </p>
          )}
          {plan?.level_driven_by_pressure && (
            <p className="widget-note">
              本日のレベルは体力予算ではなく、気圧ストレスによる下限で決まっています。
            </p>
          )}
        </section>

        <EnergySavingTaskWidget />

        {/* 未連携は正常な状態。連携を促す文言にはしない（§1.2 の督促の禁止） */}
        {plan && !plan.google_context_used && (
          <p className="widget-note">
            Googleと連携していないため、天候の要素のみで算定しています。
          </p>
        )}
      </div>

      {/* ========== 環境 ========== */}
      <div className={`view ${activeView === 'enviroment' ? 'active' : ''}`} id="view-pressure">
        <section>
          <div className="sec-title">気圧の推移（過去24時間 〜 予報12時間）</div>
          {atmosphere ? (
            <PressureChart chart={atmosphere.chart} />
          ) : (
            <p className="widget-note">気象データを取得できていません。</p>
          )}
        </section>
        <WeatherStressWidget />
      </div>

      {/* ========== 夜の吐き出し ========== */}
      <div className={`view ${activeView === 'reflect' ? 'active' : ''}`} id="view-reflect">
        <section>
          <div className="sec-title">今日、うまくいかなかったことを話してください</div>
          <p className="widget-note">
            この画面は未実装です。POST /api/v1/reflection は動作しているため、
            入力欄の実装のみが残っています。
          </p>
        </section>
      </div>

      {/* ========== 設定 ========== */}
      <div className={`view ${activeView === 'settings' ? 'active' : ''}`} id="view-settings">
        <section>
          <div className="sec-title">設定</div>
          <p className="widget-note">
            この画面は未実装です。現時点では mockup/settings.html から
            Gemini APIキーとGoogle連携を登録してください。
          </p>
        </section>
      </div>

      {/* 免責事項。常時表示が実装必須（docs/design.md §1.4） */}
      <div className="disclaimer">
        気象データと体調の関連は、体感を説明するための目安として扱っています。医学的な診断・治療の代替ではありません。
        体調不良が続く場合は医療機関を受診してください。
      </div>
    </div>
  );
};

export const Dashboard = () => (
  <AtmosphereProvider>
    <DashboardView />
  </AtmosphereProvider>
);
