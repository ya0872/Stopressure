import { useWeatherStress } from '../../hooks/useWeatherStress';

/** 変化量は符号を明示する。「-3」と「3」の取り違えが体感の説明を逆にしてしまうため */
function signed(v: number): string {
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}`;
}

export const WeatherStressWidget = () => {
  const { data, levelDrivenByPressure, isLoading, error } = useWeatherStress();

  // 取得できていない間も、値を捏造して埋めることはしない
  if (isLoading && !data) {
    return <div className="widget-box" style={{ opacity: 0.7 }}>気象データを取得しています...</div>;
  }
  if (!data) {
    return (
      <div className="widget-box">
        <div className="widget-header">
          <h3 className="widget-title">現在の環境ストレス</h3>
        </div>
        <p className="widget-note">
          気象データを取得できませんでした。{error ? `（${error.message}）` : ''}
        </p>
      </div>
    );
  }

  const s = data.stress;

  return (
    <div className="widget-box">
      <div className="widget-header">
        <h3 className="widget-title">現在の環境ストレス</h3>
        {/* 段階に丸めず指数をそのまま出す。丸め方の定義はサーバー側にしか無い */}
        <span className="pill">気圧ストレス {s.score.toFixed(0)} / 100</span>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <p className="metric-label">気圧</p>
          <p className="metric-value">
            {data.pressure.toFixed(1)}<span className="metric-unit">hPa</span>
          </p>
        </div>
        <div className="metric-card">
          <p className="metric-label">気温</p>
          <p className="metric-value">
            {data.temperature.toFixed(1)}<span className="metric-unit">℃</span>
          </p>
        </div>
        <div className="metric-card">
          <p className="metric-label">湿度</p>
          <p className="metric-value">
            {data.humidity.toFixed(0)}<span className="metric-unit">%</span>
          </p>
        </div>
      </div>

      <p className="widget-note">
        6時間 {signed(s.delta_6h)} hPa ／ 24時間 {signed(s.delta_24h)} hPa ／
        今後6時間 {signed(s.delta_next6h)} hPa
        <br />
        気温は前日同時刻比 {signed(data.temp_delta_vs_yesterday)} ℃、不快指数{' '}
        {data.discomfort_index.toFixed(0)}
      </p>

      {/* 「気圧のせい」と言い切れるかはサーバーが判定済み。ここで閾値を持たない */}
      {levelDrivenByPressure && (
        <p className="widget-note warn">
          ※本日の省エネレベルは気圧の変化によって決まっています。頭痛や倦怠感が出やすい状態です。
        </p>
      )}

      <p className="widget-note">
        観測 {data.observed_at}（{data.stale ? '保存済みの値' : data.source}）
      </p>
    </div>
  );
};
