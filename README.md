# Místník

**Kdo kandiduje. A kdo kandidoval.** Kandidátky komunálních voleb 2026 ve všech 6 393 obcích a městských částech a u každého kandidáta jeho dřívější kandidatury od roku 2002: za koho kandidoval, kdy byl zvolen, kolik dostal hlasů a kam přešel.

Web: https://mistnik.cz · Otevřená data: https://mistnik.cz/data · Metodika: https://mistnik.cz/metodika

## Proč to není triviální

Kandidáti v datech ČSÚ nemají žádný identifikátor napříč volbami. Že „Jan Novák, 45, Hnojice“ z roku 2018 je tentýž člověk jako „Jan Novák, 49, Hnojice“ z roku 2022, je odhad. Místník proto spojuje kandidatury opatrně: falešné spojení by skutečnému člověku přisoudilo cizí politickou minulost, chybějící spojení jen zkrátí historii.

Jak se rozhoduje:

1. **Tvrdé podmínky.** Stejné jméno a příjmení, věk v obou volbách odpovídá jednomu datu narození, jeden člověk má v jedněch volbách nejvýš jednu kandidaturu (kromě souběhu město + městská část).
2. **Skóre shody** (Fellegi-Sunter). Jak vzácné je jméno (kolik lidí stejného jména a ročníku v Česku žije, z četností MV ČR), kde kandidovali, společní spolukandidáti, strana, kandidátka, povolání (i přechody typu student → obor, obor → důchodce), tituly.
3. **Druhý signál.** Ve velkých městech a tam, kde v obci kandiduje jmenovec, nestačí samotné skóre; musí sedět ještě něco dalšího.
4. **Jazykový model jako rozhodčí.** Sporné páry posuzuje model [Jev](https://openrouter.ai/typesafe/jev-1.13); sám o spojení nerozhoduje, jen potvrzuje případy s vysokým skóre a druhou shodou.
5. **Skládání osob** s hlídáním tranzitivity: nové spojení musí sedět se všemi dosavadními kandidaturami téhož člověka.

Výsledek: zhruba 749 tisíc osob z 1,45 milionu kandidatur. Nejistá spojení (uvnitř obce se týkají asi 2 % letošních kandidátů) se na webu nezobrazují, ale jsou v otevřených datech, aby si je mohl kdokoli zkontrolovat.

Podrobný návrh a jeho kritika: [`docs/parovani-kandidatu-v2.md`](docs/parovani-kandidatu-v2.md).

## Co je kde

| soubor | co dělá |
|---|---|
| `src/linkage.py` | načtení dat ČSÚ, skóre všech párů kandidatur |
| `src/cluster.py` | rozhodnutí o spojení, druhý signál, Jev, skládání osob |
| `src/gender.py` | odhad pohlaví ze jména (jen pro tvary slov a souhrnné počty) |
| `src/occupations.py`, `src/occ_cards.py` | třídění volných zápisů povolání do oborů (CZ-ISCO) |
| `src/build_site.py` | statický web do `site/`: stránky obcí, hledání, hlavní stránka |
| `src/export_open_data.py` | otevřená data bez jmen |
| `src/obec_template.html`, `src/home_template.html` | šablony stránek |
| `src/label_*.py`, `src/pdv_*.py` | ruční kontrola vzorku a srovnání s programydovoleb.cz |
| `src/kv2026_live.py` | archiv průběžných výsledků 2026 (živá data se po volbách mažou) |
| `tests/test_match.py` | testy tvrdých podmínek |

## Jak to spustit

Python 3.9+, pandas, numpy. Vstupní data se do repozitáře nedávají, odkud je stáhnout, popisuje [`data/README.md`](data/README.md).

```sh
python3 src/linkage.py        # -> data/derived/linkage_edges.csv.gz
python3 src/cluster.py        # -> cluster_edges.csv.gz, cluster_persons.csv.gz
python3 src/occ_cards.py      # -> povolání
python3 src/build_site.py     # -> site/ včetně otevřených dat
python3 tests/test_match.py
```

Dotazy na jazykové modely (Jev, Gemini) jdou přes OpenRouter a potřebují `OPENROUTER_API_KEY`; odpovědi se ukládají do lokální cache.

## Data a osobní údaje

Podkladem jsou otevřená data Českého statistického úřadu (kandidátní listiny 2002–2026), licencovaná [CC BY 4.0](https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu). Vše, co Místník ukazuje nad rámec kandidátních listin (spojení osob, přesuny, statistiky), jsou **odvozené údaje**, ne oficiální statistika ČSÚ. Četnosti jmen MV ČR se používají jen uvnitř výpočtu a nezveřejňují se.

Na webu jsou osobní údaje kandidátů ze zveřejněných kandidátních listin. Chyba ve spojení nebo námitka: **jan@klr.cz**.

## Licence

Kód a dokumentace v tomto repozitáři jsou volné dílo ([Unlicense](LICENSE)): kopírujte, upravujte a používejte k čemukoli, bez uvádění autora.

Pro data platí podmínky ČSÚ: kdo šíří data ČSÚ nebo z nich odvozená, uvede ČSÚ jako zdroj, odkaz na [podmínky licence](https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu) a označí odvozené údaje jako odvozené. Místník sám uvádět nemusíte.
