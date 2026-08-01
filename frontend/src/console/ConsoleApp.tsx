/**
 * 設定・接続状態コンソールのルート。
 *
 * mockup/settings.html と mockup/live.html を1つのアプリにまとめ、タブで切り替える。
 * 元はページ遷移だったが、両者は同じAPI（/settings/google）を見ており、
 * 「設定を変えて、反映を確かめる」を往復するのが実際の使い方だったため。
 *
 * 製品画面（Dashboard）とは別のエントリ（console.html）に分けてある。
 * こちらは開発・運用のための道具であって、利用者に見せる画面ではない。
 */
import { useEffect, useState } from 'react';
import { LiveView } from './components/LiveView';
import { SettingsView } from './components/SettingsView';
import './console.css';

type Tab = 'settings' | 'live';

/** リロードしても同じタブに戻れるよう、URLのハッシュと同期する */
function initialTab(): Tab {
  return location.hash === '#live' ? 'live' : 'settings';
}

export function ConsoleApp() {
  const [tab, setTab] = useState<Tab>(initialTab);

  useEffect(() => {
    // pushState にすると戻るボタンがタブ切替の履歴で埋まるため replace にする
    history.replaceState(null, '', `#${tab}`);
  }, [tab]);

  return (
    <>
      <div className="topbar">
        <div className="wrap">
          <button
            type="button"
            className={'tab' + (tab === 'settings' ? ' here' : '')}
            onClick={() => setTab('settings')}
          >
            設定
          </button>
          <button
            type="button"
            className={'tab' + (tab === 'live' ? ' here' : '')}
            onClick={() => setTab('live')}
          >
            接続状態・実データ
          </button>
          <span className="spacer" />
          {/* 製品画面へ戻る導線。別エントリなので通常のリンクで移動する */}
          <a href="/">ダッシュボード</a>
        </div>
      </div>

      {tab === 'settings' ? <SettingsView /> : <LiveView onOpenSettings={() => setTab('settings')} />}
    </>
  );
}
