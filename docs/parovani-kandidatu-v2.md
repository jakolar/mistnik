# Párování kandidátů napříč komunálními volbami, v2

Revize zadání v1. Cíl se nemění: **precision automatických spojení**, auditovatelnost,
ruční kontrola nejistých případů. Mění se, jak k tomu dojít.

## 0. Co říkají data (KV 2018 → 2022, ověřeno 2026-10-08)

| Měření | Hodnota |
|---|---|
| Kandidatur 2018 / 2022 | 218 622 / 195 474 |
| Stejné jméno + stejné zastupitelstvo, jednoznačně (1:1) | 106 223 |
| … z toho věkový posun 4 / 3 / 5 let | 101 237 / 3 595 / 218 |
| … posun −18 až −26 let (otec a syn, stejné jméno, stejná obec) | stovky |
| Stejné jméno + stejné zastupitelstvo, víceznačné | 2 499 |
| Kandidát 2018 s věkově konzistentním jmenovcem kdekoli v ČR 2022 | 117 555 (z toho 13 872 má jmenovců víc) |
| Dvojice stejné jméno + stejný věk v jedné volbě 2022 | 5 621 |
| Bezpartijní (`PSTRANA=99`) | 86 % |

Datum řádných voleb: 2002-11-01, 2006-10-20, 2010-10-15, 2014-10-10, 2018-10-05, 2022-09-23, 2026-10-09.

Posun 3 roky má 3,4 % dvojic, a to přesně odpovídá podílu lidí s narozeninami mezi
23. 9. a 5. 10. (12 dní / 365 = 3,3 %). Věk je tedy věk ke dni voleb a dá se z něj
spočítat **interval data narození**. Posun 5 let je pro dvojici 2018 → 2022 nemožný,
takže 218 případů jsou chyby v datech nebo jiné osoby.

## 1. Hlavní výhrady k v1

1. **Věk je pojatý jako tolerance, přitom jde o tvrdou podmínku.** `±1 rok` je moc volné
   (2018 → 2022 je platný jen posun 4, nebo 3 pro 12denní okno narozenin; posun 5 je nemožný)
   i moc přísné (u voleb s posunutým datem může být platná jiná dvojice). Penalizační schody
   „2 roky −10, 3–4 roky −30" jsou v rozporu s tím, že každý nesoulad mimo okno je
   buď chyba dat, nebo jiný člověk. Řešení v 3.1.
2. **Body jsou ručně odhadnuté a nekalibrované.** „95" neznamená 95 % jistotu a nikdo neví, kolik
   falešných spojení při něm vznikne. Stejný formát (součet vah) dává Fellegi-Sunter model,
   kde váhy jsou `log2(m/u)` a dají se z dat odhadnout. Výstup je pravděpodobnost, práh pak
   znamená něco měřitelného.
3. **Signály, které v datech nejsou.** „Veřejná funkce" v registru kandidátů neexistuje.
   Je tam jen `MANDAT` (byl zvolen) a volný text `POVOLANI` (občas „starosta").
4. **Signály, které nic nerozlišují.** Shoda „BEZPP = BEZPP" platí pro 86 % kandidátů, nese
   skoro nulovou informaci, ale v1 za ni dává +10. Stejně tak „stejná obec": kandidát musí mít
   v obci trvalý pobyt, takže „bydliště" je prakticky název obce. Geografie je ve skutečnosti
   jen otázka, jestli jde o stejné zastupitelstvo, nebo se člověk přestěhoval.
5. **Četnost jména se počítá na špatné úrovni.** Jan Novák je celostátně častý, ale ve vesnici
   s 200 obyvateli je jediný. Naopak vzácné jméno v obci, kde kandiduje otec i syn, je past
   (viz posun −18 až −26 let). Rozhoduje, kolik věkově slučitelných jmenovců je v okruhu.
6. **Párové skóre bez tranzitivity.** A~B a B~C, ale A≁C (otec/syn, chyba věku). V1 ukládá
   `candidacy → person`, ale skóruje dvojice; není řečeno, jak se z dvojic stane osoba.
   Navíc platí strukturální omezení: **v jedné volbě má člověk nejvýš jednu kandidaturu**
   (výjimka: obec + městská část téhož města). To je cannot-link zadarmo.
7. **Příklady odporují pravidlům.** Příklad 14 (Jan Novák, velmi časté jméno) nedostal −10 a
   prošel jako AUTO_MATCH; podle §13 by potřeboval ≥ 98. Příklad 15 nemá −5 za jinou příslušnost.
   Kladné body dávají maximum 117, škála 0–100 není ohraničená.
8. **Chybí:** změna příjmení po sňatku (ženy, `-ová`), vývoj titulů (Bc. → Ing. je slučitelné,
   Ing. → nic je podezřelé), mezery mezi volbami (2010 → 2022 bez 2014/2018), doplňkové
   a opakované volby, verze algoritmu, velikost fronty na ruční kontrolu.
9. **GDPR.** Většina kandidátů jsou soukromé osoby z malých obcí. Sestavování politické historie
   je profilování; čl. 5 (přesnost) je přesně důvod, proč je precision priorita. Potřeba
   posouzení oprávněného zájmu (DPIA) a postup pro námitku a opravu.

## 2. Datový model kandidatury

Zdroj `kvrk` + `kvros` + `kvrzcoco`, klíč kandidatury
`(DATUMVOLEB, KODZASTUP, COBVODU, POR_STR_HL, PORCISLO)`.

Odvozená pole:

- `name_display`, `first_names[]`, `surname`, `surname_base` (bez `-ová`, pro budoucí rozšíření),
  `name_key` = lowercase, bez diakritiky, bez titulů, sjednocené mezery.
- `titles_pre[]`, `titles_post[]` (normalizované: `ing`, `mgr`, `bc`, `mudr`, `phd` …).
- `birth_from`, `birth_to`: interval data narození z `VEK` a data voleb
  (`[datum − (VEK+1) let + 1 den, datum − VEK let]`).
- `obec_kod` (z `KODZASTUP`/`kvrzcoco`, nikdy z textu `BYDLISTEN`), `orp`, `okres`, `kraj`,
  souřadnice obce z RÚIAN pro vzdálenost.
- `pstrana`, `nstrana`, `vstrana` (volební strana), `list_name`, `elected`, `votes`, `pref_rank`.
- `occupation_norm` (lowercase, sjednocený rod: `advokátka` → `advokát`).

## 3. Rozhodování

### 3.1 Tvrdá omezení (před skórováním)

| Omezení | Důsledek |
|---|---|
| Průnik intervalů narození všech kandidatur v clusteru je prázdný | cannot-link |
| Dvě kandidatury ve stejný den voleb (mimo dvojici obec + MČ téhož města) | cannot-link |
| Ruční rozhodnutí „různé osoby" | cannot-link, má přednost |
| Ruční rozhodnutí „stejná osoba" | must-link, má přednost |

Případy těsně mimo okno (o 1 den až 1 rok, např. 218 posunů o 5 let) nejsou automatický
reject, ale **jdou do ruční kontroly s příznakem `age_data_error?`**, nikdy do AUTO_MATCH.

### 3.2 Blocking

Kandidátní dvojice jen se shodou `name_key` (příjmení + aspoň jedno křestní jméno).
Fuzzy jméno (překlep, chybějící druhé jméno) jen jako druhý průchod a nikdy do AUTO_MATCH.

### 3.3 Skóre: Fellegi-Sunter

Každé pole má úrovně shody; váha úrovně = `log2(m/u)`, kde
`m = P(shoda | stejná osoba)`, `u = P(shoda | různé osoby)`.

| Pole | Úrovně | Odkud u |
|---|---|---|
| Jméno | přesné / normalizované / jedno z více křestních | četnost jména **v okruhu** (obec, ORP, kraj, ČR); doplnit četnostmi MV ČR |
| Narození | průnik intervalů (šířka v dnech) | šířka průniku / rozpětí věků |
| Geografie | stejné zastupitelstvo / stejné město jiná MČ / stejné ORP / okres / kraj / jinde | podíl kandidátů v daném okruhu |
| Kandidátka | stejná volební strana ve stejné obci / stejný název listiny / jiná | z dat |
| Příslušnost | shoda konkrétní strany / shoda „BEZPP" / různé | z dat (BEZPP vyjde ≈ 0) |
| Povolání | podobnost normalizovaného textu, vážená vzácností slova | z dat |
| Tituly | shoda / slučitelný vývoj / regrese | z dat |
| Kontinuita | v předchozí volbě zvolen a kandiduje znovu | z dat |

`m` a `u` odhadnout EM nad dvojicemi z blockingu (hotová implementace:
[Splink](https://github.com/moj-analytical-services/splink), DuckDB backend).
Seed pro sanity check: vzácné jméno + stejné zastupitelstvo + slučitelné narození (~100 tis. dvojic).

Výstup: `match_probability` + per-field příspěvky v bitech (= auditovatelná evidence,
stejná role jako body ve v1, ale s významem).

### 3.4 Z dvojic osoby

1. Seřadit dvojice podle pravděpodobnosti sestupně.
2. Postupně slučovat clustery (union-find), **sloučení povolit jen když celý výsledný cluster
   splní 3.1** (průnik narození, nejvýš jedna kandidatura na volbu, žádný cannot-link).
3. Cluster dostane `person_id`. Při přepočtu zachovat ID podle největšího překryvu s minulým během.

Mezery mezi volbami řeší přirozeně: 2010 → 2022 se spojí přímo, i když 2014/2018 chybí.

### 3.5 Prahy

Nastavit **až z validační sady**, ne předem. Pracovní výchozí hodnoty:

| Rozhodnutí | Podmínka |
|---|---|
| AUTO_MATCH | `p ≥ 0.999` a zároveň stejné zastupitelstvo **nebo** dva nezávislé silné signály (narození + kandidátka, narození + vzácné povolání) |
| MANUAL_REVIEW | `0.9 ≤ p < 0.999`, nebo podezření na chybu věku |
| POSSIBLE_MATCH | `0.5 ≤ p < 0.9` |
| NO_MATCH | `p < 0.5` |

Před schválením prahů spočítat **velikost fronty MANUAL_REVIEW**. Při ~200 tis.
kandidaturách na volbu je fronta snadno desetitisíce a pak je práh fikce.

## 4. Validace

Ručně označená sada, **stratifikovaná**, ne náhodná (náhodný vzorek je z 90 % triviální):

- vzácné jméno, stejná obec (kontrolní, má vyjít ~100 %),
- časté jméno, stejná obec,
- otec/syn (stejné jméno, posun věku 15–40 let),
- přestěhovaní (jiné zastupitelstvo),
- posun věku mimo okno (chyby dat),
- mezery mezi volbami (8+ let),
- Praha a statutární města (obec + MČ).

Hlásit precision s intervalem spolehlivosti pro každou vrstvu zvlášť, ne jedno číslo.

## 5. Uložení

```sql
candidacy_pair (
  candidacy_a, candidacy_b,
  match_probability  NUMERIC(6,5),
  match_weight       NUMERIC(7,3),         -- součet bitů
  evidence           JSONB,                -- per pole: úroveň, m, u, bity
  hard_violation     TEXT NULL,            -- 'birth_window' | 'same_election' | 'cannot_link'
  model_version      TEXT,
  PRIMARY KEY (candidacy_a, candidacy_b, model_version)
)

person_candidacy (
  person_id, candidacy_id,
  decision      ENUM('auto','manual','singleton'),
  model_version TEXT,
  run_id        UUID
)

link_constraint (                           -- ruční rozhodnutí, přežijí přepočet
  candidacy_a, candidacy_b,
  kind        ENUM('must_link','cannot_link'),
  reason      TEXT,
  source      TEXT,                          -- reviewer / externí zdroj
  decided_by, decided_at
)
```

Evidence ukládat i pro zamítnuté dvojice, jinak nejde vysvětlit, proč něco **nebylo** spojeno.

## 6. Mimo MVP (vědomě)

- Změna příjmení po sňatku: velká ztráta recall u žen, ale řešit až s externím zdrojem.
- Krajské a parlamentní volby: stejný model, jiný `u` pro geografii.
- Fuzzy jména do AUTO_MATCH: nikdy.

## 7. Prototyp 2018 → 2022 (2026-10-08)

`src/match_v2.py` (pandas, ~40 s), test `tests/test_match.py`. Bayesovský model místo EM:
`odds = r·Π m / (E_eff·c·Π u)`, kde `E` = očekávaní jmenovci stejného ročníku v ČR
z četností MV 2017 (`src/mv_names.py`, zdroj jmenovac), `E_eff` = `E` × místní
koncentrace příjmení mezi kandidáty. `u` pro stranu/povolání/tituly/spolukandidáty
uvnitř obce se měří na náhodných dvojicích ze stejného zastupitelstva.
Osoba-událost = jméno + město + věk (sloučí kandidaturu za město i MČ).
Výsledné `p` je normalizované proti všem konkurenčním jmenovcům na obou stranách.

| | |
|---|---|
| 2018 / 2022 kandidatur | 216 161 / 195 223 |
| r (kandiduje znovu) | 0,476 |
| auto_match | 105 956 osob-událostí, model čeká ~1 chybné |
| manual_review | 1 050 |
| possible_match | 177 |
| konflikt věku na kontrolu | 220 |
| spolukandidáti 2+ společní | m = 0,86, u v téže obci = 0,26 |

Neověřeno: přesnost je odhad modelu, ne měření. Další krok je ruční označení
`data/derived/labeling_sample_2018_2022.csv` (8 vrstev po 40).

Známé slabiny: podmíněná nezávislost polí neplatí (stejná listina ⇒ stejní spolukandidáti
i strana), `r` a `c` nezávisí na věku, `E` předpokládá nezávislost jména a příjmení
(podceňuje komunity s korelovanými jmény), seed ze vzácných jmen může mít jiné `m`.
