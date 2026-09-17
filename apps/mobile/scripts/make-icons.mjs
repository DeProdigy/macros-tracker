/**
 * Draw the app icon, the splash mark, and the favicon.
 *
 * Checked in so the artwork is reproducible. The alternative is three PNGs
 * nobody can regenerate, which is how a project ends up unable to change its
 * own icon. CLAUDE.md forbids hand-editing a generated artifact, and these
 * PNGs are generated artifacts: change this script and rerun it.
 *
 *   node scripts/make-icons.mjs
 *
 * The mark is the calorie ring from the Today screen. Picking the app's own
 * strongest shape beats inventing a logo for a personal build. It is not a
 * brand mark and a later ticket can replace it.
 *
 * No image library. A PNG is a zlib stream of filtered scanlines plus three
 * chunks, and Node ships zlib. Adding sharp or canvas to a React Native app for
 * three static files is a dependency nobody wants to keep patched.
 */

import { deflateSync } from "node:zlib";
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "assets", "images");

// The tokens from lib/theme.ts, as [r, g, b].
const BLACK = [0, 0, 0];
const CYAN = [0x5e, 0xe7, 0xe0];
const TRACK = [0x26, 0x51, 0x51];

/** CRC32, which every PNG chunk carries. */
const CRC_TABLE = Uint32Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

const crc32 = (buf) => {
  let c = 0xffffffff;
  for (const byte of buf) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};

const chunk = (type, data) => {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(data.length, 0);
  head.write(type, 4, "ascii");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])), 0);
  return Buffer.concat([head, data, crc]);
};

/** Encode straight RGBA bytes as an 8-bit colour PNG. */
const encodePng = (width, height, rgba) => {
  const stride = width * 4;
  // Filter byte 0 means "no filter". The images are flat colour, so the
  // smarter filters buy almost nothing and cost a lot of code.
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y += 1) {
    raw[y * (stride + 1)] = 0;
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // colour type: RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
};

/**
 * Paint one ring at `size` pixels square.
 *
 * Supersampled 4x per axis. A ring drawn at one sample per pixel has visibly
 * stepped edges, and 16 samples is enough that no eye finds the seam.
 *
 * `sweep` is how much of the circle the cyan arc covers, clockwise from the
 * top. 0.72 matches the mockup, where the day is part eaten.
 */
const ring = ({ size, opaque, sweep = 0.72, thickness = 0.11, radius = 0.3 }) => {
  const rgba = Buffer.alloc(size * size * 4);
  const ss = 4;
  const centre = size / 2;
  const outer = size * (radius + thickness / 2);
  const inner = size * (radius - thickness / 2);

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let cyan = 0;
      let track = 0;

      for (let sy = 0; sy < ss; sy += 1) {
        for (let sx = 0; sx < ss; sx += 1) {
          const px = x + (sx + 0.5) / ss - centre;
          const py = y + (sy + 0.5) / ss - centre;
          const dist = Math.hypot(px, py);
          if (dist < inner || dist > outer) continue;

          // Angle clockwise from 12 o'clock, in turns.
          const turn = (Math.atan2(px, -py) / (Math.PI * 2) + 1) % 1;
          if (turn <= sweep) cyan += 1;
          else track += 1;
        }
      }

      const samples = ss * ss;
      const i = (y * size + x) * 4;
      const cyanPart = cyan / samples;
      const trackPart = track / samples;
      const inkPart = cyanPart + trackPart;

      for (let c = 0; c < 3; c += 1) {
        const ink = inkPart === 0 ? 0 : (CYAN[c] * cyanPart + TRACK[c] * trackPart) / inkPart;
        rgba[i + c] = Math.round(opaque ? BLACK[c] * (1 - inkPart) + ink * inkPart : ink);
      }
      rgba[i + 3] = opaque ? 255 : Math.round(inkPart * 255);
    }
  }

  return encodePng(size, size, rgba);
};

const files = [
  // The home-screen icon. iOS rounds the corners itself, so the square is flat.
  ["icon.png", ring({ size: 1024, opaque: true })],
  // The splash mark sits on the black splash background, so it is transparent.
  ["splash-icon.png", ring({ size: 512, opaque: false })],
  ["favicon.png", ring({ size: 96, opaque: true })],
  // Android draws the foreground inside a safe zone of about two thirds, so
  // the ring shrinks to survive the mask.
  ["android-icon-foreground.png", ring({ size: 432, opaque: false, radius: 0.26, thickness: 0.09 })],
  ["android-icon-monochrome.png", ring({ size: 432, opaque: false, radius: 0.26, thickness: 0.09 })],
];

for (const [name, buffer] of files) {
  writeFileSync(join(OUT, name), buffer);
  console.log(`wrote ${name} (${buffer.length} bytes)`);
}
