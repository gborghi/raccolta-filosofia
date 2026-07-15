// Gli emblem escono da Recraft a ~2MB l'uno. Sul sito stanno a ~200px:
// senza ridimensionarli la homepage scaricherebbe 25MB per mostrarne 12.
//
// Scrive IN PLACE. Prima emetteva un <nome>.min.webp affianco e lasciava intatto
// l'originale — ma stampava lo stesso "5.4 MB -> 0.88 MB", cioe' annunciava un
// risparmio che il sito non vedeva: le pagine continuavano a servire i file
// grossi, e il .min andava rinominato a mano. Chi rilanciava lo script si fidava
// del log e spediva 2MB per emblema. Ora il log dice il vero.
//
// Idempotente: `withoutEnlargement` e la soglia sul guadagno fanno si' che un
// secondo giro su file gia' ridotti non li ricomprima (ricomprimere un webp
// degrada, e la perdita non si recupera).
import sharp from "sharp";
import { readdir, stat, readFile, writeFile, unlink } from "node:fs/promises";
import path from "node:path";

const DIR = "quartz/static/emblems";
const SIZE = { desk: 1600, _default: 400 };

const all = await readdir(DIR);

// Ripulisce i .min.webp lasciati dalla vecchia versione a due tempi.
for (const f of all.filter((f) => f.endsWith(".min.webp"))) {
  await unlink(path.join(DIR, f));
  console.log(`  rimosso residuo ${f}`);
}

const files = all.filter((f) => f.endsWith(".webp") && !f.endsWith(".min.webp"));
let before = 0, after = 0;
for (const f of files) {
  const name = path.basename(f, ".webp");
  const src = path.join(DIR, f);
  const size = (await stat(src)).size;
  before += size;
  const w = SIZE[name] ?? SIZE._default;
  // Il sorgente si legge in memoria PRIMA di passarlo a sharp: `sharp(path)`
  // tiene aperto il file, e su Windows non ci si puo' riscrivere sopra
  // (EPERM). Con un Buffer l'handle non esiste proprio.
  const buf = await sharp(await readFile(src))
    .resize({ width: w, withoutEnlargement: true })
    .webp({ quality: 82 })
    .toBuffer();
  // Gia' abbastanza piccolo: lascialo stare invece di ricomprimerlo.
  if (buf.length >= size * 0.95) {
    after += size;
    console.log(`  ${name.padEnd(11)} ${w}px  ${(size / 1024).toFixed(0)} KB  (invariato)`);
    continue;
  }
  await writeFile(src, buf);
  after += buf.length;
  console.log(`  ${name.padEnd(11)} ${w}px  ${(size / 1024).toFixed(0)} -> ${(buf.length / 1024).toFixed(0)} KB`);
}
console.log(`\ntotale ${(before / 1048576).toFixed(1)} MB -> ${(after / 1048576).toFixed(2)} MB (in place)`);
