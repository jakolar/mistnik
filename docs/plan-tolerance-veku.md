# Plán: tolerance chybného věku ±1 rok (po volbách 2026)

Stav: naplánováno, neimplementováno. Začít po zveřejnění výsledků KV2026 (nejdřív 12. 10. 2026).

## Problém

ČSÚ má u části kandidátů v jednom ročníku `VEK` o rok jinak (např. 41, 46, 49 let v letech 2018, 2022, 2026:
mezi 2018 a 2022 nelze zestárnout o 5 let). Měřeno na jednoznačných jménech v obci: ~0,2 % dvojic voleb,
zhruba 200 lidí na dvojici. Tvrdý filtr intervalu narození (`linkage.birth_window`) takovou kandidaturu
ze spojení vyřadí; člověku pak chybí rok v historii a vzniká falešný „samostatný“ kandidát
(může se objevit v „už nekandiduje“ nebo jako přesun).

## Návrh

1. V `linkage.py` povolit páry, kde se intervaly narození minou o ≤ 1 rok, jako zvláštní úroveň `age_off1`.
2. Takový pár může být spojen jen při silné shodě, všechno najednou:
   - stejná obec (`geo` zast/city),
   - v obci žádný jiný kandidát toho jména v žádném ročníku (ne `family`, ne `namesake_pe`),
   - stejná kandidátka (název nebo `list_party`) **a** stejné nebo podobné povolání,
   - jinak zůstává nespojeno (otec a syn se o 1 rok neliší, ale dvojčata ano: proto podmínka jediného jména).
3. `SafeClusters`: interval narození osoby počítat s tolerancí jen přes tyto hrany; transitivní kontrola beze změny.
4. Na webu v důvodech spojení uvést „věk v datech ČSÚ se liší o rok“.

## Ověření před nasazením

- Počet nových spojení po dvojicích voleb (očekávání stovky na dvojici).
- Ruční kontrola 50 náhodných nových spojení.
- Srovnání s iROZHLAS na 330 stažených obcích (`scratchpad/irozhlas/obce`, bez nových požadavků):
  počet `both_differ` a `theirs_more` má klesnout, `published agrees` nesmí klesnout.
- `node movecheck.js` (žádné falešné „zůstal“), `tests/test_match.py`.

## Odhad

Kód ~1 h, přepočet `linkage.py` + `cluster.py` + `build_site.py` ~1 h, kontrola ~30 min.
