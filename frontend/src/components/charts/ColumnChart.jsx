import { useState } from "react";

function niceMax(value) {
  if (value <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * magnitude * 2 >= value) * magnitude;
  return step * 2;
}

/**
 * Stacked column chart (HTML/CSS). series: [{ key, label, color }]; data: [{ label, tooltipLabel, ...values }].
 * Bars <= 22px, 4px rounded top, 2px surface gap between segments, hover/focus tooltip per column.
 */
export default function ColumnChart({ data, series, ariaLabel }) {
  const [active, setActive] = useState(null);
  const totals = data.map((row) => series.reduce((sum, s) => sum + (row[s.key] || 0), 0));
  const max = niceMax(Math.max(1, ...totals));
  const ticks = [max, max / 2, 0];
  const labelEvery = Math.ceil(data.length / 7);

  return (
    <div role="group" aria-label={ariaLabel}>
      <div className="chart-columns">
        {ticks.map((tick) => {
          const top = `${(1 - tick / max) * 100}%`;
          return (
            <div key={tick}>
              <div className={`chart-gridline ${tick === 0 ? "base" : ""}`} style={{ top }} />
              <span className="chart-tick" style={{ top }}>{tick}</span>
            </div>
          );
        })}
        {data.map((row, index) => (
          <button
            key={row.label}
            type="button"
            className="chart-col"
            aria-label={`${row.tooltipLabel}: ${series.map((s) => `${s.label} ${row[s.key] || 0}`).join(", ")}`}
            onMouseEnter={() => setActive(index)}
            onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(index)}
            onBlur={() => setActive(null)}
          >
            <div className="chart-stack" style={{ height: `${(totals[index] / max) * 100}%` }}>
              {series.map((s) =>
                row[s.key] ? (
                  <div
                    key={s.key}
                    className="chart-seg"
                    style={{ flex: row[s.key], background: s.color, minHeight: 3 }}
                  />
                ) : null,
              )}
            </div>
            {active === index && (
              <div className="chart-tooltip" role="tooltip">
                <div className="t-date">{row.tooltipLabel}</div>
                {series.map((s) => (
                  <div className="t-row" key={s.key}>
                    <span className="line-key" style={{ background: s.color }} />
                    <b className="num">{row[s.key] || 0}</b>
                    <span className="muted">{s.label}</span>
                  </div>
                ))}
              </div>
            )}
          </button>
        ))}
      </div>
      <div className="chart-xlabels" aria-hidden="true">
        {data.map((row, index) => (
          <span key={row.label}>{index % labelEvery === 0 || index === data.length - 1 ? row.label : ""}</span>
        ))}
      </div>
    </div>
  );
}
