/** Horizontal bars, one series: value labeled at the tip, bars grow from a shared baseline. */
export default function BarList({ items, emptyText = "Sin datos todavía." }) {
  if (!items.length) return <p className="muted">{emptyText}</p>;
  const max = Math.max(...items.map((item) => item.value));
  return (
    <div className="barlist">
      {items.map((item) => (
        <div className="barlist-row" key={item.label} title={`${item.label}: ${item.value}`}>
          <span className="label">{item.label}</span>
          <div className="barlist-track">
            <div className="barlist-bar" style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
          <span className="value">{item.value}</span>
        </div>
      ))}
    </div>
  );
}
