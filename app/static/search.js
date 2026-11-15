/**
 * Умный поиск договоров:
 * 1. Числа: номер договора (101, 102, 103, 01, 1), суммы (840000, 840 000, 840, 1380, 1.38),
 *    даты (30.04, 20.03, 30.04.2026, 2026) и ставки неустойки (0.1, 0,1, 0.05).
 * 2. Текст: название поставщика, реквизиты, защита от опечаток (Levenshtein)
 *    и случайной раскладки клавиатуры (RU <-> EN).
 * 3. Стоп-слова: «договор», «контракт», «поставщик», «№» не ломают поиск.
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

const STOP_WORDS = new Set([
  "договор", "договора", "договору", "договором", "договоре",
  "контракт", "контракта", "поставщик", "поставщика",
  "ооо", "зао", "пао", "ао", "ип", "№", "#", "n",
]);

function translit(str, map) {
  let res = "";
  for (const ch of str) res += map[ch] || ch;
  return res;
}

export function normalize(str) {
  return String(str || "")
    .toLocaleLowerCase("ru-RU")
    .replace(/ё/g, "е")
    .replace(/[«»""''.,\-_/\\()№#]/g, " ")
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

/** Собирает все поисковые термины и числа договора */
export function getContractSearchStrings(contract) {
  const terms = [];

  // Номер договора
  if (contract.number) {
    terms.push(contract.number);
    const digits = contract.number.replace(/\D/g, "");
    if (digits) terms.push(digits);
  }

  // Поставщик
  if (contract.supplier) {
    terms.push(contract.supplier);
  }

  // Сумма
  if (contract.amount?.value !== null && contract.amount?.value !== undefined) {
    const rawVal = String(contract.amount.value);
    terms.push(rawVal);
    // С пробелами: 1 380 000
    terms.push(rawVal.replace(/\B(?=(\d{3})+(?!\d))/g, " "));
    const num = Number(contract.amount.value);
    if (!isNaN(num) && num > 0) {
      if (num >= 1000) {
        terms.push(String(Math.round(num / 1000))); // 840, 1380
      }
      if (num >= 1000000) {
        terms.push((num / 1000000).toFixed(2)); // 1.38
        terms.push((num / 1000000).toFixed(2).replace(".", ",")); // 1,38
      }
    }
  }

  // Срок поставки
  if (contract.delivery_date?.value) {
    const dateStr = String(contract.delivery_date.value);
    terms.push(dateStr);
    const parts = dateStr.split("-");
    if (parts.length === 3) {
      const [y, m, d] = parts;
      terms.push(`${d}.${m}.${y}`); // 30.04.2026
      terms.push(`${d}.${m}`); // 30.04
      terms.push(`${d} ${m}`); // 30 04
      terms.push(d); // 30
      terms.push(m); // 04
      terms.push(y); // 2026
    }
  }

  // Неустойка
  if (contract.penalty?.value) {
    const pStr = String(contract.penalty.value);
    terms.push(pStr);
    terms.push(pStr.replace(",", "."));
    terms.push(pStr.replace("%", "").trim());
  }

  // Связанные документы и предложения
  if (Array.isArray(contract.related_documents)) {
    for (const doc of contract.related_documents) {
      if (doc.explanation) terms.push(doc.explanation);
    }
  }

  if (Array.isArray(contract.proposals)) {
    for (const prop of contract.proposals) {
      if (prop.amount?.value) {
        const pVal = String(prop.amount.value);
        terms.push(pVal);
        terms.push(pVal.replace(/\B(?=(\d{3})+(?!\d))/g, " "));
      }
      if (prop.delivery_date?.value) {
        terms.push(String(prop.delivery_date.value));
      }
    }
  }

  return terms;
}

export function matchContract(contract, rawQuery) {
  const normQuery = normalize(rawQuery);
  if (!normQuery) return true;

  const searchStrings = getContractSearchStrings(contract);
  const fullText = searchStrings.join(" ");
  const textNorm = normalize(fullText);
  const textCondensed = condense(fullText);
  const queryCondensed = condense(rawQuery);

  // 1. Быстрое полное вхождение (прямое или без знаков препинания)
  if (textNorm.includes(normQuery)) return true;
  if (queryCondensed && textCondensed.includes(queryCondensed)) return true;

  // 2. Раскладка клавиатуры / транслитерация
  const queryRu = translit(normQuery, EN_TO_RU);
  const queryEn = translit(normQuery, RU_TO_EN);
  const textEn = translit(textNorm, RU_TO_EN);

  if (textNorm.includes(queryRu)) return true;
  if (textEn.includes(queryEn)) return true;

  const queryCondensedEn = condense(queryEn);
  const textCondensedEn = condense(textEn);
  if (queryCondensedEn && textCondensedEn.includes(queryCondensedEn)) return true;

  // 3. Токенизация с фильтрацией стоп-слов
  let tokens = normQuery.split(" ").filter((t) => t.length > 0);
  if (tokens.length > 1) {
    const nonStop = tokens.filter((t) => !STOP_WORDS.has(t));
    if (nonStop.length > 0) tokens = nonStop;
  }

  // 4. Проверка всех токенов
  const textWords = textNorm.split(" ").filter((w) => w.length > 0);

  return tokens.every((qToken) => {
    // Числовой токен (например, "101", "840000", "840", "30", "2026")
    const isNumeric = /^\d+$/.test(qToken);
    if (isNumeric) {
      // Ищем точное вхождение подстроки чисел
      // Например: "101" в "stn101", "840" в "840000", "01" в "101" или "01_contract"
      if (textCondensed.includes(qToken)) return true;
      return textWords.some((w) => w.includes(qToken));
    }

    // Десятичная дробь или дата (например: "0.1", "0,1", "30.04", "20.03")
    if (/^\d+[.,]\d+$/.test(qToken)) {
      const qDot = qToken.replace(",", ".");
      const qComma = qToken.replace(".", ",");
      return fullText.includes(qDot) || fullText.includes(qComma);
    }

    // Короткий текстовый токен (1-2 символа)
    if (qToken.length <= 2) {
      const qTokenEn = translit(qToken, RU_TO_EN);
      return textWords.some((w) => {
        const wEn = translit(w, RU_TO_EN);
        return w.startsWith(qToken) || w.startsWith(queryRu) || wEn.startsWith(qTokenEn);
      });
    }

    // Текстовый токен >= 3 символов с нечетким поиском
    const qTokenEn = translit(qToken, RU_TO_EN);
    return textWords.some((w) => {
      const wEn = translit(w, RU_TO_EN);
      if (w.includes(qToken) || wEn.includes(qTokenEn)) return true;

      const maxDistance = qToken.length >= 6 ? 2 : 1;
      const sub = w.slice(0, Math.min(w.length, qToken.length + 1));
      if (levenshtein(qToken, sub) <= maxDistance) return true;
      if (levenshtein(qToken, w) <= maxDistance) return true;
      if (levenshtein(qTokenEn, wEn.slice(0, Math.min(wEn.length, qTokenEn.length + 1))) <= maxDistance) return true;

      return false;
    });
  });
}
