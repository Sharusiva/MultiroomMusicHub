import { useRef } from "react";
import * as Slider from "@radix-ui/react-slider";

// Volume is stored as a 0-100 fader position. Output gain follows an audio taper
// (gain = position²), so the readout in dB is 20·log10(gain) = 40·log10(position).
export function faderDb(pct) {
  if (pct <= 0) return "−∞ dB";
  const db = 40 * Math.log10(pct / 100);
  if (Math.abs(db) < 0.05) return "0.0 dB";
  return `${db < 0 ? "−" : "+"}${Math.abs(db).toFixed(1)} dB`;
}

const TICKS = Array.from({ length: 21 }, (_, i) => i * 5);

/**
 * A thick tactile fader: slotted track, printed tick scale, a cap you grab,
 * and an exact % / dB readout in tabular numbers. Built on Radix Slider, so it
 * has full keyboard support (arrows, Page Up/Down, Home/End) and ARIA.
 */
export default function Fader({ value, onChange, onCommit, label, size = "md", readout = true, disabled }) {
  const lastTick = useRef(Math.floor(value / 10));

  const change = ([v]) => {
    // a tiny "click" on phones that support vibration, every 10%
    const tick = Math.floor(v / 10);
    if (tick !== lastTick.current) {
      lastTick.current = tick;
      try { navigator.vibrate?.(4); } catch { /* not supported */ }
    }
    onChange?.(v);
  };

  return (
    <div className={`fader ${size}`}>
      <Slider.Root
        className="fader-root"
        value={[value]}
        min={0}
        max={100}
        step={1}
        onValueChange={change}
        onValueCommit={([v]) => onCommit?.(v)}
        disabled={disabled}
        aria-label={label}
      >
        <Slider.Track className="fader-track">
          <Slider.Range className="fader-range" />
          <span className="fader-ticks" aria-hidden="true">
            {TICKS.map((t) => (
              <i key={t} className={t % 25 === 0 ? "major" : ""} style={{ left: `${t}%` }} />
            ))}
          </span>
        </Slider.Track>
        <Slider.Thumb className="fader-cap" aria-label={label} aria-valuetext={`${value}%, ${faderDb(value)}`} />
      </Slider.Root>
      {readout && (
        <output className="fader-readout num" aria-hidden="true">
          <span>{value}%</span>
          <span className="db">{faderDb(value)}</span>
        </output>
      )}
    </div>
  );
}
