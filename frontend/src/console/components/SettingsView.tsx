/**
 * 設定タブ。mockup/settings.html の置き換え。
 *
 * 秘密情報の扱いは1つの原則で貫く: 入力欄に残さない、画面に平文を返さない。
 * 保存に成功した時点で入力値を捨て、表示はマスク済みの文字列だけにする。
 */
import { GeminiSection } from './GeminiSection';
import { GoogleSection } from './GoogleSection';
import { Disclaimer } from './primitives';

export function SettingsView() {
  return (
    <div className="wrap">
      <header>
        <div className="title">設定</div>
        <div className="subtitle">STOPRESSURE — API キーと Google 連携</div>
      </header>

      <GeminiSection />
      <GoogleSection />

      <Disclaimer />
    </div>
  );
}
