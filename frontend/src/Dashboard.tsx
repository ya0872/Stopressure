import React, { useState } from 'react';
import './dashboard.css';
import { WeatherStressWidget } from './components/weather/WeatherStressWidget';
import { EnergySavingTaskWidget } from './components/weather/EnergySavingTaskWidget';

export const Dashboard: React.FC = () => {
  const [activeView, setActiveView] = useState<'home' | 'pressure' | 'reflect' | 'settings'>('home');

  return (
    <>
      <div className="wrap">
        <header>
          <div className="title">低気圧のすゝめ</div>
          <div className="subtitle">ATMOSPHERE STUDIO</div>
        </header>

        <nav className="dashboard-nav">
          <button 
            data-view="home" 
            aria-current={activeView === 'home'} 
            onClick={() => setActiveView('home')}
          >
            今日
          </button>
          <button 
            data-view="pressure" 
            aria-current={activeView === 'pressure'} 
            onClick={() => setActiveView('pressure')}
          >
            気圧
          </button>
          <button 
            data-view="reflect" 
            aria-current={activeView === 'reflect'} 
            onClick={() => setActiveView('reflect')}
          >
            夜の吐き出し
          </button>
          <button 
            data-view="settings" 
            aria-current={activeView === 'settings'} 
            onClick={() => setActiveView('settings')}
          >
            設定
          </button>
        </nav>

        {/* ========== ホーム ========== */}
        <div className={`view ${activeView === 'home' ? 'active' : ''}`} id="view-home">
          <div className="level-block">
            <div className="level-label">本日の省エネ度</div>
            {/* 動的データが入るまでの一時的な表示 */}
            <div className="level-ring" style={{ '--accent': 'hsl(215, 30%, 58%)', '--accent-dim': 'hsl(215, 22%, 32%)' } as any}>
              <div className="level-num">—</div>
              <div className="level-name">算定中</div>
            </div>
            <div className="headline">データを読み込んでいます...</div>
            <div className="budget-note"></div>
          </div>

          <WeatherStressWidget />
          <EnergySavingTaskWidget />
        </div>

        {/* ========== 気圧 ========== */}
        <div className={`view ${activeView === 'pressure' ? 'active' : ''}`} id="view-pressure">
          <section>
            <div className="sec-title">気圧の推移（過去24時間 〜 予報12時間）</div>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.8rem', padding: '1rem', background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: '4px' }}>
              現在、気圧グラフの表示機能は準備中です。
            </div>
          </section>
        </div>

        {/* ========== 夜の吐き出し ========== */}
        <div className={`view ${activeView === 'reflect' ? 'active' : ''}`} id="view-reflect">
          <section>
            <div className="sec-title">今日、うまくいかなかったことを話してください</div>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.8rem', padding: '1rem', background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: '4px' }}>
              夜の吐き出し機能は準備中です。
            </div>
          </section>
        </div>

        {/* ========== 設定 ========== */}
        <div className={`view ${activeView === 'settings' ? 'active' : ''}`} id="view-settings">
          <section>
            <div className="sec-title">設定</div>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.8rem', padding: '1rem', background: 'var(--bg-raised)', border: '1px solid var(--border)', borderRadius: '4px' }}>
              設定画面は準備中です。
            </div>
          </section>
        </div>

      </div>
    </>
  );
};