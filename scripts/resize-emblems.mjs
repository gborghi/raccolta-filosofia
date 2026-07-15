// Gli emblem escono da Recraft a ~2MB l'uno. Sul sito stanno a ~200px:
// senza ridimensionarli la homepage scaricherebbe 25MB per mostrarne 12.
import sharp from "sharp";
import { readdir, stat } from "node:fs/promises";
import path from "node:path";

const DIR = "quartz/static/emblems";
const SIZE = { desk: 1600, _default: 400 };

const files = (await readdir(DIR)).filter((f) => f.endsWith(".webp") && !f.endsWith(".min.webp"));
let before = 0, after = 0;
for (const f of files) {
  const name = path.basename(f, ".webp");
  const src = path.join(DIR, f);
  before += (await stat(src)).size;
  const w = SIZE[name] ?? SIZE._default;
  const buf = await sharp(src).resize({ width: w, withoutEnlargement: true })
    .webp({ quality: 82 }).toBuffer();
  await sharp(buf).toFile(path.join(DIR, `${name}.min.webp`));
  after += buf.length;
  console.log(`  ${name.padEnd(11)} ${w}px  ${(buf.length / 1024).toFixed(0)} KB`);
}
console.log(`\ntotale ${(before / 1048576).toFixed(1)} MB -> ${(after / 1048576).toFixed(2)} MB`);
