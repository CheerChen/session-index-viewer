import type { SessionUsage } from "../types";
import { usageChipModel } from "../utils/usage";

interface UsageChipProps {
  usage: SessionUsage;
  source: string;
  onOpen: () => void;
}

// Compact usage chip: bold primary ctx, muted secondary meta.
// Full breakdown opens in UsageModal on click.
export function UsageChip({ usage, source, onOpen }: UsageChipProps) {
  const chip = usageChipModel(usage, source);
  return (
    <button
      type="button"
      className="usage-chip"
      onClick={onOpen}
      title="View usage details (u)"
      aria-label={`Usage: ${chip.line}. Open details.`}
    >
      <span className="usage-chip-primary">{chip.primary}</span>
      {chip.sizeOnly && <span className="usage-chip-tag">size only</span>}
      {chip.secondary && (
        <span className="usage-chip-secondary">{chip.secondary}</span>
      )}
      <span className="usage-chip-affordance" aria-hidden="true">
        ›
      </span>
    </button>
  );
}
