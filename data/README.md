# Komunální volby ČR, data

Zdroj: ČSÚ, https://volby.gov.cz/opendata/opendata.htm (volby.cz přesměrovává na volby.gov.cz).
Staženo 2026-10-08 do `raw/kvYYYY/`. Ročníky 2002–2026 (1994 a 1998 v open datech nejsou).

Používat `csv_od/` (UTF-8, čárka). `csv/` je MS varianta se středníkem.

| soubor | obsah | klíč |
|---|---|---|
| `kvrzcoco` | registr zastupitelstev (obec/MČ, mandáty, počet obyvatel, ORP, obvody) | `KODZASTUP` |
| `kvros` | kandidátní listiny (strana, složení, hlasy, mandáty) | `KODZASTUP`+`POR_STR_HL` |
| `kvrk` | kandidáti (jméno, věk, povolání, bydliště, příslušnost, hlasy, `MANDAT`) | +`PORCISLO` |
| `kvt3` | okrsky: voliči, obálky, platné hlasy | `ID_OKRSKY`, `OBEC`+`OKRSEK` |
| `kvhl` | okrsky × listina: hlasy pro stranu + `HLASY_01..70` per kandidát | +`POR_STR_HL` |
| `cvs`, `cpp`, `cns`, `cvs_slozeni` | číselníky stran (volební / příslušnost / navrhující) | |
| `kvcoco`, `cnumnuts`, `kvdatumvoleb` | zastupitelstva, okresy/kraje, termíny voleb | |

Pasti:
- Data 2002–2022 obsahují i dodatečné/opakované volby a soudní rozhodnutí (`DATUMVOLEB`, `TYPDUVODU`). Filtrovat na řádný termín.
- `kvrzcoco` má víc řádků na zastupitelstvo, když má volební obvody (`COBVODU`).
- Kandidáti nemají ID napříč ročníky, párování jen přes jméno + věk + bydliště.
- Ve stejném okrsku se v Praze/Brně/Ostravě/Plzni volí obec i MČ (`TYPZASTUP` 1/2).
- KV2026 (9.–10. 10. 2026): zatím jen registry. Okrsková data až po zpracování.
  Živé XML: `https://volby.gov.cz/appdata/kv2026/20261009/odata/` (`vysledky.xml`, `okresy/`, `zastup/vysledky_obec_<KODZASTUP>.xml`, dávky `okrsky/` a `obce_d/` po 5 min).
  Živé XML se po volbách nearchivuje (2022 vrací 404), stahovat průběžně.
- Hranice okrsků: 2022 v `raw/kv2022/vol_okrsky_2022g100`, 2026 na geodata.csu.gov.cz.
