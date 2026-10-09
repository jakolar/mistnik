# Povolání kandidátů: revize stránky skupin povolání (2026-10-09)

Předmět: `data/mockup/povolani.html`, generuje `src/occ_cards.py` (šablona `src/occ_template.html`), export `data/derived/occ_groups.json` pro profily kandidátů.
Všechna čísla jsou kandidatury 2002 až 2026 (1 454 482 řádků, 159 302 různých zápisů povolání), pokud není řečeno jinak.
Bez síťových volání; Gemini se jen čte z existujícího `data/derived/occ_gemini.csv`.

## (a) Nálezy podle dopadu

### 1. Polovina kandidatur „Nezařazeno“ ležela mimo top 5 000 (dopad: 13,6 % všech kandidatur)

Skupina „Nezařazeno (vzácné zápisy)“ byla největší na stránce: 198 490 kandidatur, 139 833 různých zápisů. Jev klasifikoval jen 5 000 nejčastějších textů; vše ostatní (každý zápis nejvýš 10krát) končilo nezařazené, i když šlo o zjevné varianty známých zápisů: „osvč - kovář“, „ředitelka zvš“, „mechanik zemědělských strojů“, „zemědělská podnikatelka“, „učitelka zš“ a podobně.

### 2. Řádky „Z čeho se skupina skládá“ ukazovaly kód Jevu, ne konečné zařazení (52 řádků se surovým nebo prázdným popiskem, desítky nesmyslných)

Příčina byla jedna: `D["sub"]` se počítal **před** opravami Gemini a `GROUP_OVERRIDES`. Text přesunutý do jiné skupiny si nesl původní kód Jevu, takže se ve skupině objevil cizí popisek. Statusové kódy (`nejasne`, `podnikatel`, `domacnost`, `duchodce`, `funkce`, `student`, `nezamestnany`) a prázdný kód se propsaly jako surové klíče. Před opravou 52 takových řádků.

Texty za podezřelými řádky (konečná skupina byla většinou správně, špatně byl jen popisek):

| Skupina / řádek (před) | Kandidatur | Hlavní texty | Verdikt |
|---|---:|---|---|
| Lékaři a zdravotníci / Tradiční řemesla a tisk | 535 | zubní technik 322, zubní laborantka 175, zubní laborant 49 | skupina správně (Gemini), popisek špatně |
| Lékaři a zdravotníci / Uklízeči | 467 | sanitářka 474 | skupina správně (pravidlo), popisek špatně |
| Lékaři a zdravotníci / Policisté | 233 | hasič - záchranář 69, hasič-záchranář 57, hasič záchranář 33, hasič, záchranář 20 | **skupina špatně**: pravidlo „záchranář“ přebilo hasiče |
| IT / Ekonomové a odborníci ve veřejné správě | 2 885 | it specialista 2 204, it konzultant 425, it analytik 246 | skupina správně (Gemini), popisek špatně |
| Technici / nejasne | 7 623 | technolog 3 348, mistr 2 679, mistrová 433, thp pracovník 199 | skupina správně, popisek surový klíč |
| Vedoucí a ředitelé / nejasne | 18 040 | manažer 7 155, projektový manažer 3 460, manažerka 1 563 | skupina správně, popisek surový klíč |
| Obchod a služby / Vojáci | 279 | ostraha 140, ostraha objektu 77, ostraha objektů 44 | **sporné**: Gemini dal ostrahu do služeb, CZ-ISCO 5414 patří do 54 |
| Obchod a služby / Policisté | 1 059 | bezpečnostní pracovník 443, strážná 116, pracovník bezpečnostní služby 95, plavčík 79 | **sporné**, totéž |
| Úklid / Policisté | 419 | vrátný 239, vrátná 138, správce budovy 49 | skupina přijatelná, popisek špatně |
| Úklid / Pečovatelé | 756 | školnice 674, školnice mš 76 | skupina správně, popisek špatně |
| Řidiči / Technici | 2 003 | strojvedoucí 1 809, strojvedoucí čd 208 | skupina správně, popisek špatně |
| Vědci a inženýři / Technici | 5 309 | stavební inženýr 2 234, strojní inženýr 524 | skupina správně, popisek špatně |
| Učitelé / prázdný řádek | 7 872 | tail texty chycené pravidlem „učitel“ (učitelka zš, učitel soš) | skupina správně, chyběl popisek |

### 3. Poznámka „U 91,7 % kandidatur bylo zařazení nejisté“ byla nepravdivá

Příznak `lowconf` bral `major_conf < 0.5` z Jevu bez ohledu na to, co se s textem stalo potom. Příklad Řidiči: „řidič“ 29 406 kandidatur má `major_conf` 0,46, ale Jev odpověděl správně (83) a Gemini to potvrdil; „strojvedoucí“ 1 809 (0,47) opravilo Gemini. Po poctivé definici (konečná skupina stojí jen na nejisté odpovědi Jevu, bez pravidla a bez souhlasu Gemini) jde o 0,003 % kandidatur, protože Gemini prošlo všech 5 000 textů. Poznámka proto zmizela a nahradila ji jiná, která něco říká: kolik kandidatur ve skupině je zařazeno automaticky podle klíčových slov.

### 4. Hasiči-záchranáři u lékařů (dopad: asi 180 kandidatur)

`GROUP_OVERRIDES` posílal každý „záchranář“ k lékařům, takže „hasič - záchranář“ a varianty skončily ve zdravotnictví a „báňský záchranář“ taky.

### 5. Pořadí pravidel: Gemini přebíjel ručně kontrolované `OVERRIDES`

Kód tvrdil „our hand-checked overrides still have the last word“, ale oprava Gemini se aplikovala po `OVERRIDES` a přepsala je. Nyní ruční pravidlo vyhrává; liší se to u 38 textů (1 708 kandidatur), hlavně ostraha (viz bod 7).

### 6. Překrývající se a zavádějící názvy skupin

- „Péče a sociální služby“ vedle „Právo, kultura, média a **sociální práce**“: sociální pracovnice (2 693) a pracovníci (1 131) byli v právu a kultuře, pečovatelky vedle. Čtenář hledající sociální práci musel hledat ve dvou skupinách.
- „Armáda, policie a hasiči“ neobsahovala ostrahu, přestože CZ-ISCO 54 ji obsahuje; ostraha se přes Gemini rozlila do „Obchod a služby“.
- „Obchod a služby“ zahrnuje kuchaře, číšníky a kadeřnice; název to neříká.
- „Řidiči“ obsahuje strojvedoucí.
- „Politici a veřejné funkce“: všichni kandidáti jsou politici; jde o lidi, kteří místo povolání napsali svou funkci.

### 7. Veřejné funkce: 89,2 % zvolených

Skupina má úspěšnost 89 % (průměr kolem 30 %), protože jde z velké části o úřadující starosty a místostarosty („starosta“ 7 581, „starosta obce“ 4 785, „starostka“ 2 839). Prezentovat se dá, ale jen s vysvětlením; jinak to vypadá jako zjištění o „politicích“. Pravidlo `^starost…` navíc chytalo „starosta TJ Sokol“ (spolková funkce).

### 8. Statusy proti povoláním

Data (Jev + Gemini) jsou konzistentní a revize je ponechala: „aktivní důchodce“ 63, „invalidní důchodce“ 7 083, „učitelka v důchodu“ 120, „technik, důchodce“ 62 jsou Důchodci; „osvč - truhlář“ 129, „osvč - zedník“ 65 jsou v řemesle; „podnikatel ve stavebnictví“ 490 v řemesle. Tail tuto logiku dřív neměl. „učitelka v.v“, „policista v.v“ (ve výslužbě) skončily u učitelů a policistů, protože zkratku „v.v“ nic nechytalo.

### 9. Drobnosti na stránce

- Popisky major-only kódů Jevu („Specialisté“, „Řemeslníci“, „Služby a prodej“) se objevovaly jako řádky uvnitř skupin; „Specialisté“ dokonce ve skupině Technici.
- Pořadí karet míchalo obory a statusy (Podnikatelé a Důchodci nahoře); index nerozlišoval, co je obor.
- `title="CZ-ISCO: "` s prázdným názvem u řádků bez kódu.
- Patička tvrdila, že vše zařadil Jev.

## (b) Co se změnilo a proč

Vše v `src/occ_cards.py` a `src/occ_template.html`.

1. **Klasifikace přepsaná na úroveň různých textů** (`classify()`): jeden řádek na zápis, s provenancí `src` (`jev`, `rule`, `gemini`, `tail-*`). Je rychlejší (regexy nad 159 tisíci texty místo 1,45 milionu řádků) a dovoluje auditovat, odkud zařazení pochází.
2. *(Později zrušeno rozhodnutím vlastníka, viz (f).)* **Řádek „Z čeho se skupina skládá“ se počítá z konečné skupiny**: kód Jevu, pokud patří do konečné skupiny; jinak kód z ručního pravidla (`RULE_SUB`, např. sanitářka → 32, sociální pracovnice → 2635 „Sociální pracovníci“); jinak kód nejdelšího známého prefixu nebo slova se spolehlivým kódem ve stejné skupině; jinak řádek „Jiné nebo neurčené (např. manažer, jednatel společnosti)“ s dvěma nejčastějšími příklady. Statusy a prázdné kódy už jako řádek vzniknout nemohou; kontrola to hlídá.
3. **Klasifikátor řídkých zápisů** (`tail_group()`), deterministický, bez sítě, učený jen na 5 000 zařazených textech (po opravách Gemini a pravidel). Pořadí kroků:
   1. statusová slova (`STATUS_WORDS`: důchod, invalidní, výslužba, „v.v“, emeritní, student, mateřská/rodičovská dovolená, „na MD“, nezaměstnaný) mají přednost, stejně jako u top textů („elektrikář v důchodu“ je důchodce);
   2. text se rozdělí na části (čárka, středník, lomítko, závorka, pomlčka s mezerou); části s předsedou klubu, spolku, TJ, SDH se přeskočí (`HOBBY`);
   3. v každé části zleva: přesná shoda se známým textem, nejdelší známý prefix po slovech („mechanik zemědělských strojů“ → „mechanik“), známý text za neinformativními přídavnými jmény („revizní elektrotechnik“), a nakonec hlasování slov: slovo hlasuje, jen pokud ho používají aspoň 3 známé texty (6 pro pětipísmenný kmen) a aspoň 85 % z nich má stejnou skupinu; podstatná jména mají přednost před přídavnými („skladová účetní“ je účetní);
   4. slabé statusy (podnikatel, veřejná funkce, nejasné) platí, jen když se nenajde obor („osvč - kovář“ je kovář, „osvč“ samotné zůstává podnikatel).
   Co nesplní žádný krok, zůstává nezařazené.
4. **Pravidla**: hasiči a báňští/horští záchranáři zůstávají u hasičů; ostraha, ochranka, bezpečnostní služby, hlídači do „Armáda, policie, hasiči a ostraha“ (CZ-ISCO 54); sociální pracovníci do „Sociální práce a péče“; ošetřovatelé zvířat do zemědělství; „osvč/podnikatel ve stavebnictví/elektro/…“ do řemesel; „školník zš“ k úklidu stejně jako „školník“; „předseda finančního/kontrolního výboru, komise“ jako veřejná funkce; „starosta TJ/SDH/Sokola“ už není veřejná funkce; „v.v“ jako výslužba. Ruční pravidla mají přednost před Gemini.
5. **Názvy skupin**: „Armáda, policie, hasiči a ostraha“, „Obchod, gastronomie a služby“, „Právo, kultura a média“, „Sociální práce a péče“, „Řidiči a strojvedoucí“, „Veřejné funkce (starosta, radní, poslanec)“. `OLD_NAMES` mapuje staré názvy, takže `occ_gemini.csv` se načítá dál beze změny. Popisky CZ-ISCO 26 a 53 upraveny podle toho, co v nich po přesunech zůstalo.
6. **Poznámky na kartách**: zrušena nepravdivá „nejistá“ poznámka; nová poznámka u skupin, kde je víc než 10 % kandidatur zařazeno podle klíčových slov; vysvětlující poznámky u Veřejných funkcí (proč 89 %), Podnikatelů, Důchodců, Nejasných a Nezařazených.
7. **Stránka**: index rozdělen na „Obory“, „Postavení a funkce místo oboru“, „Bez určitelného oboru“; karty ve stejném pořadí; lede a patička popisují skutečný postup (Jev, kontrola Gemini, ruční pravidla, klíčová slova).
8. `python3 src/occ_cards.py --check`: rychlý test pravidel na příkladech z této revize (bez načítání surových dat).

## (c) Před a po

| Ukazatel | Před | Po |
|---|---:|---|
| Zařazeno (cokoli kromě „Nezařazeno“) | 86,4 % | **97,0 %** |
| Zařazeno do oboru (16 skupin povolání) | 56,7 % | **66,1 %** |
| Nezařazeno, kandidatur | 198 490 | **43 616** |
| Nezařazeno, různých zápisů | 139 833 | 29 126 |
| Kandidatur zařazených klíčovými slovy | 0 | 152 869 (10,5 %) |
| Řádků „Z čeho se skupina skládá“ se surovým nebo prázdným popiskem | 52 | **0** |
| Kandidatur s poctivě „nejistým“ zařazením | (tvrzeno až 91,7 % ve skupině) | 0,003 % |

Odkud zařazení pochází (kandidatury): Jev 1 081 016, Gemini 100 342, ruční pravidla 76 639, klíčová slova 152 869 (prefix 76 206, část textu 33 783, slovo 14 561, status 12 685, přídavné jméno + známý text 9 991, slabý status 5 643), nezařazeno 43 616.

Velikost skupin:

| Skupina | Před | Po | Změna | Zápisů po | Z toho podle klíč. slov | Zvoleno 2002 až 2022 |
|---|---:|---:|---:|---:|---:|---:|
| Vedoucí a ředitelé | 85 592 | 126 196 | +40 604 | 30 459 | 32,2 % | 36,2 % |
| Ekonomika, účetnictví a úřady | 102 777 | 123 397 | +20 620 | 15 527 | 16,7 % | 30,1 % |
| Technici | 104 167 | 118 177 | +14 010 | 9 719 | 11,9 % | 33,7 % |
| Řemesla a stavebnictví | 94 204 | 102 148 | +7 944 | 5 564 | 7,0 % | 30,0 % |
| Dělníci a obsluha strojů | 79 430 | 85 901 | +6 471 | 4 495 | 7,5 % | 23,1 % |
| Učitelé a vychovatelé | 79 469 | 85 592 | +6 123 | 10 877 | 7,3 % | 32,1 % |
| Obchod, gastronomie a služby | 71 516 | 79 598 | +8 082 | 7 225 | 11,8 % | 20,1 % |
| Lékaři a zdravotníci | 48 107 | 53 254 | +5 147 | 4 962 | 10,2 % | 31,4 % |
| Řidiči a strojvedoucí | 38 249 | 40 932 | +2 683 | 1 811 | 6,6 % | 28,1 % |
| Zemědělství a lesnictví | 30 775 | 33 295 | +2 520 | 2 294 | 7,2 % | 46,5 % |
| Právo, kultura a média | 28 105 | 32 926 | +4 821 | 6 841 | 26,6 % | 27,0 % |
| Armáda, policie, hasiči a ostraha | 20 801 | 24 141 | +3 340 | 3 625 | 5,3 % | 37,2 % |
| Vědci a inženýři | 16 258 | 20 686 | +4 428 | 3 431 | 21,4 % | 31,6 % |
| IT | 15 730 | 19 738 | +4 008 | 3 082 | 20,3 % | 26,7 % |
| Sociální práce a péče | 4 626 | 9 826 | +5 200 | 1 029 | 6,5 % | 18,4 % |
| Úklid a pomocné práce | 4 554 | 5 092 | +538 | 414 | 6,8 % | 19,6 % |
| Podnikatelé bez uvedeného oboru | 186 102 | 190 027 | +3 925 | 3 100 | 2,1 % | 29,8 % |
| Důchodci | 142 433 | 149 588 | +7 155 | 5 241 | 4,7 % | 18,7 % |
| Veřejné funkce (starosta, radní, poslanec) | 30 185 | 31 319 | +1 134 | 5 328 | 3,7 % | 89,2 % |
| Studenti | 26 873 | 30 922 | +4 049 | 3 297 | 13,1 % | 7,0 % |
| Rodičovská dovolená a domácnost | 16 114 | 17 713 | +1 599 | 1 307 | 9,0 % | 20,0 % |
| Nezaměstnaní | 4 564 | 4 677 | +113 | 91 | 2,4 % | 19,0 % |
| Nejasně uvedené povolání | 25 361 | 25 721 | +360 | 457 | 1,6 % | 33,2 % |
| Nezařazeno (vzácné zápisy) | 198 490 | 43 616 | −154 874 | 29 126 | 0 % | 24,2 % |

(Názvy „před“ jsou staré názvy stejných skupin; Sociální práce a péče = dřívější „Péče a sociální služby“.)

Ověření výstupu (čteno z vygenerovaného JSON, bez prohlížeče): 24 karet, 0 surových/prázdných popisků řádků, `occ_groups.json` má 159 302 textů a 24 názvů skupin totožných s kartami, `n2026` dává 189 908 kandidatur. JavaScript stránky projde `node --check` a vykreslení se zástupným DOM (24 článků, 3 sekce indexu, žádné `undefined`/`NaN`).

**Přesnost klíčových slov, měřená předem** (leave-one-out na 5 000 známých textech: každý text se zařadí, jako by ho klasifikátor neznal): pokryje 68,5 % textů, z nich 82,5 % do stejné skupiny jako Jev/Gemini/pravidla, váženo kandidaturami 94,1 %. Podle kroku: status 96 %, slovo 88 %, část textu 85 %, přídavné jméno + známý text 81 %, prefix 80 %, slabý status 74 %. Většina „chyb“ prefixu jsou hraniční případy, kde i referenční zařazení je volba („vedoucí prodejny“: Gemini → obchod, prefix → vedoucí). Na těchto textech je úloha těžší než na tailu, protože top texty jsou právě ty nejobecnější.

## (d) Ruční kontrola 60 náhodných nově zařazených zápisů

Náhodný výběr 60 různých textů ze 109 380 zařazených klíčovými slovy (`random_state=20261009`), po finální verzi pravidel. Verdikt: ✓ správně, ~ obhajitelné, ✗ špatně.

| # | Text | Skupina | Krok | Verdikt |
|---:|---|---|---|---|
| 1 | finanční poradce, hudebník | Ekonomika, účetnictví a úřady | část | ✓ |
| 2 | vedoucí prod | Vedoucí a ředitelé | prefix | ✓ |
| 3 | logistik pre, hudební recesista | Ekonomika, účetnictví a úřady | prefix | ✓ |
| 4 | technik-invalid.důch | Důchodci | status | ✓ |
| 5 | předák kolejové dopravy | Dělníci a obsluha strojů | prefix | ✓ |
| 6 | poradce v oboru marketingu a reklamy | Ekonomika, účetnictví a úřady | prefix | ✓ |
| 7 | ředitelka odboru vzp čr | Vedoucí a ředitelé | prefix | ✓ |
| 8 | projektant, předseda fest 2004 | Technici | část | ✓ |
| 9 | zástupce ředitele vzdělávání | Vedoucí a ředitelé | prefix | ✓ |
| 10 | vedoucí truhlářské výroby | Vedoucí a ředitelé | prefix | ✓ |
| 11 | politoložka, referentka na mšmt | Právo, kultura a média | část | ✓ |
| 12 | manager ck | Vedoucí a ředitelé | prefix | ✓ |
| 13 | dramaturg divadla | Právo, kultura a média | prefix | ✓ |
| 14 | jednatel, obchodní zástupce | Obchod, gastronomie a služby | část | ✓ |
| 15 | pomocná kuchařka a kartářka | Úklid a pomocné práce | prefix | ✓ (jako „pomocná kuchařka“) |
| 16 | pedagog a kulturní geograf, projektový manažer | Učitelé a vychovatelé | prefix | ✓ |
| 17 | šéfredaktor, zastupitel | Právo, kultura a média | část | ✓ |
| 18 | sq-c (manažer dodavatelské kvality) | Vedoucí a ředitelé | prefix | ✓ |
| 19 | fin. a bank.pracovník v.v | Důchodci | status | ✓ |
| 20 | zkušební elektrotechnik | Technici | přídavné jméno | ✓ |
| 21 | 1. náměstek sdh, elektrotechnik | Technici | část | ✓ |
| 22 | ved.odb.st.soc.p.úp | Učitelé a vychovatelé | slovo | ✗ (vedoucí odboru na úřadu práce) |
| 23 | specialista tel. sítě | IT | slovo | ✓ |
| 24 | vedoucí progr.odd.domu kultury | Vedoucí a ředitelé | prefix | ✓ |
| 25 | ředitel výroby a kvality | Vedoucí a ředitelé | prefix | ✓ |
| 26 | referentka kontrolingu | Ekonomika, účetnictví a úřady | prefix | ✓ |
| 27 | věd.pracov. a středošk.pedagog | Učitelé a vychovatelé | slovo | ✓ |
| 28 | student uk-pedagogická fakulta | Studenti | status | ✓ |
| 29 | materiální účetní | Ekonomika, účetnictví a úřady | přídavné jméno | ✓ |
| 30 | prodavačka zlata | Obchod, gastronomie a služby | prefix | ✓ |
| 31 | důchodce, rybář, zastupitel pacova | Důchodci | status | ✓ |
| 32 | výkonná manažerka | Vedoucí a ředitelé | přídavné jméno | ✓ |
| 33 | skladnice, prodavačka | Dělníci a obsluha strojů | část | ✓ |
| 34 | jednatel malířské firmy | Řemesla a stavebnictví | slovo | ✓ |
| 35 | projektový manažer, vedoucí odboru | Vedoucí a ředitelé | část | ✓ |
| 36 | podnikatel - reklamní zařízení | Podnikatelé bez uvedeného oboru | slabý status | ✓ (konzervativně) |
| 37 | počítačový analytik, vedoucí pěveckého sboru …, zastupitel města, člen kontrolního výboru | IT | část | ✓ |
| 38 | it specialista, člen rady města chomutova | IT | část | ✓ |
| 39 | technický pracovník výroby | Technici | prefix | ✓ |
| 40 | ved. skladu potravin | Vedoucí a ředitelé | prefix | ✓ |
| 41 | vedoucí úseku skladu | Vedoucí a ředitelé | prefix | ✓ |
| 42 | mechanik-traktorista | Zemědělství a lesnictví | slovo | ✓ |
| 43 | technolog lakování | Technici | prefix | ✓ |
| 44 | vedoucí staveb a investic | Vedoucí a ředitelé | prefix | ✓ |
| 45 | řidič - instruktor | Řidiči a strojvedoucí | část | ✓ |
| 46 | část.důchodce | Důchodci | status | ✓ |
| 47 | živnostnice na md | Rodičovská dovolená a domácnost | status | ✓ |
| 48 | vedoucí katedry sociální práce, zastupitelka | Vedoucí a ředitelé | prefix | ~ (vysokoškolský učitel?) |
| 49 | technický dozor fn olomouc | Technici | prefix | ✓ |
| 50 | strojník - údržbář | Dělníci a obsluha strojů | část | ✓ |
| 51 | právník, diplomat | Právo, kultura a média | část | ✓ |
| 52 | it specialistka, lektorka francouzštiny | IT | část | ✓ |
| 53 | specialista informační bezpečnosti | IT | slovo | ✓ |
| 54 | analytička, poradkyně v soc. oblastech | Nejasně uvedené povolání | slabý status | ✓ (poctivě nejasné) |
| 55 | vedoucí reprezentant společnosti | Vedoucí a ředitelé | prefix | ✓ |
| 56 | profesor gymnázia, předseda kulturní komise rady města | Učitelé a vychovatelé | část | ✓ |
| 57 | trat'ový dělník čd | Dělníci a obsluha strojů | přídavné jméno | ✓ |
| 58 | administrátor personálního oddělení | Ekonomika, účetnictví a úřady | prefix | ✓ |
| 59 | odborný referent, odbor kancelář hejtmana | Ekonomika, účetnictví a úřady | část | ✓ |
| 60 | softwarový vývojář, člen puls evropy | IT | část | ✓ |

Výsledek: 58 ✓, 1 ~, 1 ✗. Pozor na výklad: pravidla jsem během revize ladil na dvou dřívějších náhodných vzorcích (60 textů každý), kde vyšlo 53/60 a 55/60; opravené typy chyb (předseda výboru/klubu jako vedoucí, „na MD“, „v.v“, adjektivum před podstatným jménem, „pracující v neziskovém sektoru“ zařazený podle kmene) jsou v pravidlech. Realistický odhad přesnosti na tailu je proto kolem 90 až 95 %, ne 97 %.

## (e) Otevřené otázky pro vlastníka

1. **Ostraha**: dal jsem ji k armádě, policii a hasičům (CZ-ISCO 54, skupina přejmenována). Gemini ji dával do služeb. Volební úspěšnost ostrahy je spíš podprůměrná, takže to mírně stahuje číslo skupiny. Ponechat, nebo vlastní skupina?
2. **Sociální pracovníci** přesunuti z práva a kultury do „Sociální práce a péče“ (skupina tím vzrostla z 4,6 na 9,8 tisíce). Souhlas?
3. **„Vedoucí X“**: Gemini dával „vedoucí prodejny“ do obchodu, „vedoucí výroby“ do vedoucích. Klasifikátor dědí tuto nekonzistenci (rozhoduje nejdelší známý prefix). Chceme pravidlo „vedoucí a ředitelé vždy do Vedoucích“, nebo „vedoucí podle oboru“?
4. **Vedoucí a ředitelé** mají 44 819 kandidatur v řádku „Jiné nebo neurčené (např. manažer, jednatel společnosti)“ a 32 % skupiny je z tailu. „Manažer“ bez oboru je spíš status než obor; nepřesunout „manažer/jednatel“ bez upřesnění do „Nejasně uvedené povolání“?
5. **Veřejné funkce, 89 % zvolených**: ponechal jsem kartu s vysvětlující poznámkou. Alternativa: na kartě nezobrazovat srovnání úspěšnosti s průměrem, protože jde o úřadující, ne o obor.
6. **„X v důchodu“** je Důchodce (dřívější povolání se ztrácí, 120+ variant typu „učitelka v důchodu“). To odpovídá datům Jevu i Gemini; chceme to tak i na profilech kandidátů?
7. **Kombinace funkce + podnikatel** („podnikatel, místostarosta“) jdou do Podnikatelů, kdežto top text „osvč, místostarosta“ je ve Veřejných funkcích. Drobnost, ale nekonzistentní.
8. **Zbylé nezařazené** (43 616 kandidatur, 29 126 zápisů) jsou hlavně překlepy („záměčník“, „státní zeměstnanec“, „sokromý podnikatel“), obecná slova („pracovník v obchodu“, „správce obce“, „zástupce společnosti“) a zkratky. Fuzzy shoda s překlepy by přidala další procenta; nechal jsem ji stranou kvůli riziku chyb. Chceme ji?
9. **Gemini má poslední slovo u 1 107 textů** (100 342 kandidatur) a tyto texty nikdo ručně nekontroloval; jen 38 z nich teď přebíjí ruční pravidlo. Stálo by za to projít top 100 sporů ručně.
10. `src/occ_gemini_check.py` při případném novém běhu pošle Gemini **nové** názvy skupin (bere je z `occ_cards.GROUPS`); jeho výstup se načte, staré CSV také (`OLD_NAMES`). V promptu je ale napevno „Politici a veřejné funkce“; při dalším běhu by se měl prompt upravit (soubor jsem podle zadání neměnil).

## (f) Doplněk: rozhodnutí vlastníka (2026-10-09, po první verzi revize)

1. **Sekce „Z čeho se skupina skládá“ odstraněna.** Karty ukazují jen „Jak to kandidáti píšou“ (8 nejčastějších zápisů). Data rozpadu do stránky ani do JSON karet nejdou; výpočet podskupin (`HUMAN`, `RULE_SUB`, odhad kódu podle prefixu a slov) byl z `src/occ_cards.py` smazán, nic jiného ho nepoužívalo. Body (a) 2 a (b) 2 výše tím přestávají být relevantní pro stránku; zjištění o nekonzistentních kódech Jevu zůstává platné pro případné budoucí použití CZ-ISCO.
2. **„Záchranář“ zúžen.** K lékařům jde jen zdravotnický záchranář („zdravotnický záchranář“, „zdravotník-záchranář“, „záchranář ZZS/RZP“). „hasič - záchranář“, „hasič, záchranář“, „záchranář - hasič“, „profesionální hasič, záchranář“, „důlní/báňský záchranář“ zůstávají u Armády, policie, hasičů a ostrahy; „vodní záchranář“ a „plavčík“ tamtéž (pravidlo pro plavčíky přidal souběžně koordinátor). Samotné „záchranář“ nechává rozhodnutí Jevu (zdravotnictví). Dopad: asi 120 kandidatur přešlo ze zdravotnictví k hasičům a ostraze.
3. **Status vyhrává obecně.** Statusová slova (`STATUS_WORDS`: důchod, invalidní, výslužba, „v.v“, emeritní, student/studentka/studující, mateřská/rodičovská dovolená, „na MD“, nezaměstnaný) teď přebíjí obor u **všech** textů, nejen u řídkých: „zdravotní sestra v důchodu“ a „zdravotní sestra, důchodkyně“ jsou Důchodci, „student lékařské fakulty“ Student, „učitelka na mateřské dovolené“ Rodičovská dovolená, „místostarosta, důchodce“ Důchodce. Dopad na top texty i tail: asi 830 zápisů, 1 200 kandidatur. „student“ se chytá jen jako celé slovo, aby „studentský klub“ nebyl student.
4. Opraveno „1. místostarosta“, „2. místostarosta města“ (číslování před funkcí), které po změně 3 vypadly z Veřejných funkcí.
5. `python3 src/occ_cards.py --check` pokrývá i tyto případy.

Aktuální čísla po těchto změnách (a po souběžném pravidle koordinátora, které přesouvá „státní zaměstnanec“, „zaměstnanec obce/města/úřadu“ z Nejasných do Ekonomiky, účetnictví a úřadů, asi 15 000 kandidatur): zařazeno 97,0 %, do oboru 67,0 %, nezařazeno 43 517 kandidatur, podle klíčových slov 9,6 %. Tabulka v (c) je stav před těmito změnami.

Poznámka k souběžnému pravidlu „státní zaměstnanec“: chytá i „státní zaměstnanec - policista“, „státní zaměstnanec pčr/ačr/- hasič“ (asi 120 kandidatur), které dřív byly správně u policie, armády a hasičů; a poznámka karty „Nejasně uvedené povolání“ v `NOTES` stále uvádí „státní zaměstnanec“ jako příklad. Nechal jsem to beze změny, protože pravidlo není moje; doporučuji vyloučit texty, které obsahují policii, hasiče nebo armádu, a upravit příklad v poznámce.
