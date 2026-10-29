import { SENSITIVITY, percent } from "../../utils/format";

/** Part-to-whole bar for the four sensitivity levels; status colors always paired with a text label. */
export default function SegmentBar({ items }) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  return (
    <div>
      <div className="segbar" role="img" aria-label={items.map((i) => `${SENSITIVITY[i.label]?.label}: ${i.value}`).join(", ")}>
        {total === 0 ? (
          <div style={{ flex: 1, background: "var(--surface-2)" }} />
        ) : (
          items
            .filter((item) => item.value > 0)
            .map((item) => (
              <div
                key={item.label}
                style={{ flex: item.value, background: SENSITIVITY[item.label]?.color }}
                title={`${SENSITIVITY[item.label]?.label}: ${item.value}`}
              />
            ))
        )}
      </div>
      <div className="seg-legend">
        {items.map((item) => (
          <div key={item.label}>
            <i style={{ background: SENSITIVITY[item.label]?.color }} />
            <span>{SENSITIVITY[item.label]?.label}</span>
            <b>{item.value}</b>
            <small>{percent(item.value, total)}%</small>
          </div>
        ))}
      </div>
    </div>
  );
}
