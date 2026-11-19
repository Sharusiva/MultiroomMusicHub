import * as Popover from "@radix-ui/react-popover";

const kbps = (b) => (b ? `${Math.round(b / 1000)} kbps` : "– kbps");
const khz = (hz) => (hz ? `${(hz / 1000).toFixed(hz % 1000 ? 1 : 0)} kHz` : "– kHz");
const ms = (v, signed) => {
  if (v == null || !isFinite(v)) return "–";
  const s = Math.abs(v).toFixed(1);
  return signed ? `${v < 0 ? "−" : "+"}${s} ms` : `${s} ms`;
};

export function syncHealth({ playing, waiting, blocked, driftMs }) {
  if (!playing) return { led: "", text: "paused" };
  if (blocked) return { led: "warn", text: "tap anywhere for sound" };
  if (waiting) return { led: "", text: "starting" };
  return { led: Math.abs(driftMs) <= 25 ? "ok" : "warn", text: `${ms(driftMs)} drift` };
}

/**
 * The unobtrusive status pill (format • sample rate • drift) that opens into the
 * full audio chain: file → NGINX → control node → clock sync → scheduler → output → zone.
 */
export default function SignalPath({ track, state, core, server, zoneLabel, zoneRooms, deviceCount, leadMs, health }) {
  const driftMs = core.player.drift * 1000;
  const rate = core.player.audio.playbackRate || 1;
  const fmtLabel = track ? `${track.codec || "Audio"} ${kbps(track.bitrate)} • ${khz(track.sample_rate)} • ${health.text}` : "No song loaded";

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button className="signal-pill num" aria-label={`Signal path: ${fmtLabel}`}>
          <i className={`led ${health.led}`} aria-hidden="true" />
          <span>{fmtLabel}</span>
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="popover" side="bottom" align="start" sideOffset={8} collisionPadding={16}>
          <h3>Signal path</h3>
          <p>How this song gets from the server to this device, in time with every other speaker.</p>
          <ol className="chain">
            <li>
              <i className="node" />
              <span className="stage-name">Source</span>
              <span className="stage-val num">{track?.file || "–"}
                <small>{track ? `${track.codec}, ${kbps(track.bitrate)}, ${khz(track.sample_rate)}, ${track.channels === 1 ? "mono" : "stereo"}` : "Nothing queued"}</small>
              </span>
            </li>
            <li>
              <i className="node" />
              <span className="stage-name">Delivery</span>
              <span className="stage-val">NGINX file server<small>Streamed in ranges, never through the app servers</small></span>
            </li>
            <li>
              <i className="node" />
              <span className="stage-name">Control</span>
              <span className="stage-val num">{server || "–"}<small>Picked by NGINX: the server with the fewest connections</small></span>
            </li>
            <li>
              <i className={`node ${core.clock.synced ? "ok" : ""}`} />
              <span className="stage-name">Clock</span>
              <span className="stage-val num">offset {ms(core.clock.offset, true)}, round trip {ms(core.clock.rtt)}
                <small>Matched to server time from the fastest of 16 pings</small></span>
            </li>
            <li>
              <i className="node" />
              <span className="stage-name">Scheduler</span>
              <span className="stage-val num">start lead {leadMs ?? 600} ms, change #{state?.version ?? 0}
                <small>Every play, skip and seek starts at the same future moment everywhere</small></span>
            </li>
            <li>
              <i className={`node ${health.led === "ok" ? "ok" : ""}`} />
              <span className="stage-name">Output</span>
              <span className="stage-val num">drift {state?.is_playing ? ms(driftMs, true) : "–"}, speed {rate.toFixed(3)}×
                <small>Checked 4 times a second; small drift is nudged out by speed, big drift by a jump</small></span>
            </li>
            <li>
              <i className={`node ${zoneRooms > 1 ? "ok" : ""}`} />
              <span className="stage-name">Zone</span>
              <span className="stage-val">{zoneLabel}
                <small className="num">{deviceCount} {deviceCount === 1 ? "device" : "devices"} in {zoneRooms} {zoneRooms === 1 ? "room" : "rooms"}</small></span>
            </li>
          </ol>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
