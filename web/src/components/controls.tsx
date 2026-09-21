import type { ReactNode } from "react";

export function Row({
  label,
  hint,
  expert,
  children,
}: {
  label: string;
  hint?: string;
  expert?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 py-2">
      <span className="flex items-center gap-2 text-sm text-slate-300">
        {label}
        {expert && (
          <span className="rounded bg-panel-soft px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
            expert
          </span>
        )}
      </span>
      {children}
      {hint && <span className="text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

const inputClass =
  "w-full rounded-md border border-edge bg-panel-soft px-2.5 py-1.5 text-sm text-slate-100 outline-none focus:border-accent";

export function NumberInput({
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled,
}: {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <input
      type="number"
      className={inputClass}
      value={Number.isFinite(value) ? value : 0}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      onChange={(event) => onChange(Number(event.target.value))}
    />
  );
}

export function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      type="text"
      className={inputClass}
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

export function Select({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <select className={inputClass} value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`flex h-6 w-11 items-center rounded-full border border-edge transition ${
        checked ? "bg-accent/80" : "bg-panel-soft"
      }`}
    >
      <span
        className={`mx-0.5 h-4.5 w-4.5 rounded-full bg-slate-100 transition ${
          checked ? "translate-x-5" : ""
        }`}
      />
    </button>
  );
}

export function Slider({
  value,
  min,
  max,
  step,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <input
        type="range"
        className="w-full"
        value={value}
        min={min}
        max={max}
        step={step ?? (max - min) / 200}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <span className="w-20 shrink-0 text-right text-xs tabular-nums text-slate-400">
        {value.toFixed(step && step >= 1 ? 0 : 3)}
      </span>
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "default",
  disabled,
}: {
  children: ReactNode;
  onClick: () => void;
  variant?: "default" | "primary" | "danger" | "ghost";
  disabled?: boolean;
}) {
  const styles = {
    default: "bg-panel-soft hover:bg-edge text-slate-100",
    primary: "bg-accent text-slate-900 hover:brightness-110 font-medium",
    danger: "bg-rose-500/20 text-rose-200 hover:bg-rose-500/30",
    ghost: "text-slate-400 hover:text-slate-100",
  }[variant];
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md border border-edge px-3 py-1.5 text-sm transition disabled:opacity-40 ${styles}`}
    >
      {children}
    </button>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-edge py-3 last:border-b-0">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</h3>
      {children}
    </section>
  );
}
