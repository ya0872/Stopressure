/**
 * /atmosphere の生値表示と気圧グラフ。
 *
 * グラフは Dashboard と同じ src/components/weather/PressureChart.tsx を使う。
 * 同じデータを別の描き方で2つ持つと、片方だけ直して食い違うため複製しない。
 */
import { PressureChart } from '../../components/weather/PressureChart';
import type { AtmosphereResponse } from '../../types/weather';
import { Row, Rows, Section } from './primitives';

/** 増減が読み取れるよう符号を必ず付ける */
const signed = (v: number) => (v > 0 ? '+' : '') + v.toFixed(1);

export function LiveChart({ atmosphere }: { atmosphere: AtmosphereResponse | null }) {
  return (
    <Section title="気圧の推移（過去24時間 〜 予報12時間）">
      {!atmosphere ? (
        <div className="empty">—</div>
      ) : (
        <>
          <PressureChart chart={atmosphere.chart} />
          <div className="chart-legend">
            <span className="lg-fall">下降している区間</span>
            <span className="lg-rise">上昇・横ばいの区間</span>
            <span className="lg-now">現在時刻</span>
          </div>
          <Rows>
            <Row
              label="表示範囲"
              tone="dim"
              value={`${atmosphere.chart.times[0]?.replace('T', ' ')} 〜 ${atmosphere.chart.times.at(-1)?.replace('T', ' ')}`}
            />
            <Row
              label="最高 / 最低"
              value={`${Math.max(...atmosphere.chart.pressure).toFixed(1)} / ${Math.min(...atmosphere.chart.pressure).toFixed(1)} hPa`}
            />
            <Row
              label={`現在（${atmosphere.chart.times[atmosphere.chart.now_index]?.slice(11, 16)}）`}
              value={`${atmosphere.chart.pressure[atmosphere.chart.now_index]?.toFixed(1)} hPa`}
            />
          </Rows>
        </>
      )}
    </Section>
  );
}

export function LiveAtmosphere({ atmosphere }: { atmosphere: AtmosphereResponse | null }) {
  if (!atmosphere) {
    return (
      <Section title="気象データ">
        <div className="empty">—</div>
      </Section>
    );
  }

  const s = atmosphere.stress;
  return (
    <Section title="気象データ">
      <Rows>
        <Row label="観測時刻" value={atmosphere.observed_at} />
        <Row label="地点" tone="dim" value={`${atmosphere.latitude}, ${atmosphere.longitude}`} />
        <Row
          label="取得元"
          tone="dim"
          value={atmosphere.source + (atmosphere.stale ? '（保存済みの値）' : '')}
        />
        <Row label="海面更正気圧" value={`${atmosphere.pressure.toFixed(1)} hPa`} />
        <Row
          label="気温"
          value={`${atmosphere.temperature.toFixed(1)} ℃（前日比 ${signed(atmosphere.temp_delta_vs_yesterday)}）`}
        />
        <Row label="湿度" value={`${atmosphere.humidity.toFixed(0)} %`} />
        <Row label="不快指数" value={atmosphere.discomfort_index.toFixed(1)} />
        <Row label="気圧ストレス" value={`${s.score.toFixed(1)} / 100`} />
        <Row label="　直近6時間" tone="dim" value={`${signed(s.delta_6h)} hPa`} />
        <Row label="　直近24時間" tone="dim" value={`${signed(s.delta_24h)} hPa`} />
        <Row label="　予報6時間" tone="dim" value={`${signed(s.delta_next6h)} hPa`} />
      </Rows>
    </Section>
  );
}
