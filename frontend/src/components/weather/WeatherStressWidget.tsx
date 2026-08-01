import React from 'react';
import { useWeatherStress } from '../../hooks/useWeatherStress';
import type { StressLevel } from '../../types/weather';

export const WeatherStressWidget: React.FC = () => {
  const { data, isLoading, error } = useWeatherStress();

  if (isLoading) return <div className="widget-box" style={{ opacity: 0.7 }}>データを読み込み中...</div>;
  if (error) return <div className="widget-box" style={{ color: 'hsl(350, 60%, 60%)' }}>データの取得に失敗しました</div>;
  if (!data) return null;

  const getStressClass = (level: StressLevel) => {
    switch (level) {
      case 'CRITICAL': return 'critical';
      case 'HIGH': return 'high';
      case 'MEDIUM': return 'medium';
      case 'LOW': return 'low';
      default: return '';
    }
  };

  const stressLabels: Record<StressLevel, string> = {
    LOW: '安定',
    MEDIUM: 'やや注意',
    HIGH: '警戒',
    CRITICAL: '限界'
  };

  return (
    <div className="widget-box">
      <div className="widget-header">
        <h3 className="widget-title">現在の環境ストレス</h3>
        <span className={`pill ${getStressClass(data.stressLevel)}`}>
          {stressLabels[data.stressLevel]}
        </span>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <p className="metric-label">天気</p>
          <p className="metric-value">{data.condition}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">気圧</p>
          <p className="metric-value">{data.pressure}<span className="metric-unit">hPa</span></p>
        </div>
        <div className="metric-card">
          <p className="metric-label">気温</p>
          <p className="metric-value">{data.temperature}<span className="metric-unit">℃</span></p>
        </div>
      </div>
      
      {data.stressLevel === 'HIGH' && (
        <p className="widget-note warn">
          ※前日からの気圧降下が激しいです。頭痛や倦怠感が出やすい状態です。
        </p>
      )}
    </div>
  );
};