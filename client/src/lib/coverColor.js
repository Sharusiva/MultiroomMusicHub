// Picks a representative color from an album cover so the Now Playing stage can be
// tinted by the music instead of by the interface. Saturated, mid-brightness pixels
// count most, so a red sleeve with a white disco ball reads as red, not pink-grey.

const cache = new Map();

function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function coverColor(src, fallbackHex) {
  if (!src) return Promise.resolve(hexToRgb(fallbackHex));
  if (cache.has(src)) return cache.get(src);
  const p = new Promise((resolve) => {
    const img = new Image();
    img.decoding = "async";
    img.onload = () => {
      try {
        const size = 40;
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = size;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(img, 0, 0, size, size);
        const { data } = ctx.getImageData(0, 0, size, size);
        let r = 0, g = 0, b = 0, total = 0;
        for (let i = 0; i < data.length; i += 4) {
          const R = data[i], G = data[i + 1], B = data[i + 2];
          const max = Math.max(R, G, B), min = Math.min(R, G, B);
          const sat = max === 0 ? 0 : (max - min) / max;
          const light = (max + min) / 510;
          const w = 0.05 + sat * sat * (1 - Math.abs(light - 0.5) * 1.4);
          r += R * w; g += G * w; b += B * w; total += w;
        }
        resolve(total ? [Math.round(r / total), Math.round(g / total), Math.round(b / total)] : hexToRgb(fallbackHex));
      } catch {
        resolve(hexToRgb(fallbackHex));
      }
    };
    img.onerror = () => resolve(hexToRgb(fallbackHex));
    img.src = src;
  });
  cache.set(src, p);
  return p;
}
