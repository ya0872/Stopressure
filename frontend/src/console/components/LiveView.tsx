/**
 * 接続状態タブ。mockup/live.html の置き換え。
 *
 * どこまで動いているかを1画面で確かめるためのもので、製品画面ではない。
 * バックエンドが落ちている・気象が取れない・Googleが未連携、といった状態を
 * 隠さずそのまま出す。
 */
import { useEffect } from 'react';
import { useLiveData } from '../hooks/useLiveData';
import { LiveAtmosphere, LiveChart } from './LiveAtmosphere';
import { LiveGoogle } from './LiveGoogle';
import { LiveBreakdown, LivePlan, LiveSuggestions } from './LivePlan';
import { Disclaimer, Pill } from './primitives';
import type { Tone } from './primitives';

/**
 * 省エネレベルに応じたアクセントの色相。1（平常運転）から 5（完全休止）へ向かって
 * 緑 → 青 → 紫に寄せる。mockup/index.html の LEVELS と揃えてある。
 */
const LEVEL_HUE: Record<number, number> = { 1: 150, 2: 190, 3: 215, 4: 245, 5: 272 };

export function LiveView({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { data, reload, locate, locateLabel, locating } = useLiveData();
  const level = data.plan?.level;

  // レベルに合わせて CSS 変数を差し替える。色は補助であって、
  // レベルの数値と呼称は常に文字で出しているため色だけに情報は乗らない（§8.2）
  useEffect(() => {
    if (level === undefined) return;
    const hue = LEVEL_HUE[level] ?? 215;
    const light = matchMedia('(prefers-color-scheme: light)').matches;
    const root = document.documentElement.style;
    root.setProperty('--accent', light ? `hsl(${hue}, 34%, 42%)` : `hsl(${hue}, 30%, 60%)`);
    root.setProperty('--accent-dim', light ? `hsl(${hue}, 30%, 70%)` : `hsl(${hue}, 22%, 34%)`);
  }, [level]);

  const backendPill: { text: string; tone: Tone } =
    data.backend === 'checking'
      ? { text: '確認中', tone: 'plain' }
      : data.backend === 'up'
        ? { text: '接続済み', tone: 'ok' }
        : { text: '未起動', tone: 'ng' };

  const weatherPill: { text: string; tone: Tone } =
    data.backend !== 'up'
      ? { text: '—', tone: 'plain' }
      : !data.plan
        ? { text: '取得失敗', tone: 'ng' }
        : data.plan.stale
          ? { text: '保存済みの値', tone: 'warn' }
          : { text: '取得済み', tone: 'ok' };

  const googlePill: { text: string; tone: Tone } = !data.googleStatus
    ? { text: '—', tone: 'plain' }
    : !data.googleStatus.configured
      ? { text: 'クライアント未登録', tone: 'warn' }
      : !data.googleStatus.linked
        ? { text: '未連携', tone: 'warn' }
        : { text: '連携済み', tone: 'ok' };

  return (
    <>
      <div className="statusbar">
        <div className="wrap">
          <span>バックエンド</span>
          <Pill {...backendPill} />
          <span>気象データ</span>
          <Pill {...weatherPill} />
          <span>Google</span>
          <Pill {...googlePill} />
          <span className="spacer" />
          <button type="button" className="slim" onClick={locate} disabled={locating}>
            {locateLabel}
          </button>
          <button type="button" className="slim" onClick={reload}>
            再取得
          </button>
        </div>
      </div>

      <div className="wrap">
        <header>
          <div className="title">停気圧</div>
          <div className="subtitle">STOPRESSURE — バックエンド実データ確認</div>
        </header>

        {data.backend === 'down' ? (
          <section>
            <div className="empty">
              バックエンドに接続できません。
              <br />
              backend で <code className="inline">uvicorn app.main:app --port 8000</code>{' '}
              を起動してください。
            </div>
          </section>
        ) : (
          <>
            <LivePlan plan={data.plan} error={data.planError} />
            <LiveBreakdown plan={data.plan} />
            <LiveSuggestions plan={data.plan} />
            <LiveChart atmosphere={data.atmosphere} />
            <LiveAtmosphere atmosphere={data.atmosphere} />
            <LiveGoogle
              status={data.googleStatus}
              context={data.context}
              onReload={reload}
              onOpenSettings={onOpenSettings}
            />
          </>
        )}

        <Disclaimer />
      </div>
    </>
  );
}
