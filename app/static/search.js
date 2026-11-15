/**
 * Умный нечеткий поиск договоров с защитой от опечаток и раскладки клавиатуры.
 */

const RU_TO_EN = {
  с: "s", т: "t", н: "n", р: "r", о: "o", е: "e", а: "a", к: "k",
  х: "h", в: "v", м: "m", п: "p", б: "b", д: "d", л: "l", у: "u",
  и: "i", г: "g", з: "z", ф: "f", й: "y", ж: "zh", ч: "ch", ш: "sh", щ: "sch",
};

const EN_TO_RU = {
  s: "с", t: "т", n: "н", c: "с", r: "р", o: "о", e: "е", a: "а",
  k: "к", h: "х", v: "в", b: "б", m: "м", p: "п", d: "д", l: "л",
  u: "у", i: "и", g: "г", z: "з", f: "ф", y: "й", w: "в", x: "х",
};

function translit(str, map) {
  let res = "";
  for (const ch of str) res += map[ch] || ch;
  return res;
}

export function normalize(str) {
  return String(str || "")
    .toLocaleLowerCase("ru-RU")
    .replace(/ё/g, "е")
    .replace(/[«»""''.,\-_/\\()]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function condense(str) {
  return String(str || "")
    .toLocaleLowerCase("ru-RU")
    .replace(/ё/g, "е")
    .replace(/[^a-zа-я0-9]/gi, "");
}

export function levenshtein(a, b) {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = i;
    for (let j = 1; j <= b.length; j++) {
      const val = a[i - 1] === b[j - 1] ? row[j - 1] : Math.min(row[j - 1], prev, row[j]) + 1;
      row[j - 1] = prev;
      prev = val;
    }
    row[b.length] = prev;
  }
  return row[b.length];
}

export function matchContract(contract, rawQuery) {
  const query = normalize(rawQuery);
  if (!query) return true;

  const rawText = `${contract.number} ${contract.supplier || ""}`;
  const text = normalize(rawText);
  const textCondensed = condense(rawText);
  const queryCondensed = condense(rawQuery);

  // 1. Прямое или сжатое вхождение (stn101 -> STN-101, контурэлектро -> Контур Электро)
  if (text.includes(query)) return true;
  if (queryCondensed && textCondensed.includes(queryCondensed)) return true;

  // 2. Раскладка клавиатуры / транслит (стн-101 <-> stn-101)
  const queryRu = translit(query, EN_TO_RU);
  const queryEn = translit(query, RU_TO_EN);
  const textEn = translit(text, RU_TO_EN);
  const queryCondensedEn = condense(queryEn);
  const textCondensedEn = condense(textEn);

  if (text.includes(queryRu)) return true;
  if (textEn.includes(queryEn)) return true;
  if (queryCondensedEn && textCondensedEn.includes(queryCondensedEn)) return true;

  // 3. Токены и опечатки (Levenshtein)
  const queryTokens = query.split(" ").filter(Boolean);
  const textWords = text.split(" ").filter((w) => w.length > 0);

  return queryTokens.every((qToken) => {
    const qTokenEn = translit(qToken, RU_TO_EN);
    if (qToken.length <= 2) {
      return textWords.some((w) => {
        const wEn = translit(w, RU_TO_EN);
        return w.startsWith(qToken) || w.startsWith(queryRu) || wEn.startsWith(qTokenEn);
      });
    }

    return textWords.some((w) => {
      const wEn = translit(w, RU_TO_EN);
      if (w.startsWith(qToken) || w.includes(qToken) || wEn.startsWith(qTokenEn)) return true;

      const maxDistance = qToken.length >= 6 ? 2 : 1;
      const sub = w.slice(0, Math.min(w.length, qToken.length + 1));
      if (levenshtein(qToken, sub) <= maxDistance) return true;
      if (levenshtein(qToken, w) <= maxDistance) return true;
      if (levenshtein(qTokenEn, wEn.slice(0, Math.min(wEn.length, qTokenEn.length + 1))) <= maxDistance) return true;
      return false;
    });
  });
}
