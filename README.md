# Místník

Kandidátky komunálních voleb 2026 ve všech obcích a historie kandidátů od roku 2002: https://mistnik-cz.web.app

Kandidáti v datech ČSÚ nemají identifikátor napříč volbami. Místník spojuje kandidatury jednoho člověka podle jména, věku (data narození), obce a dalších shod. Jak přesně, popisuje [metodika](https://mistnik-cz.web.app/metodika) a `docs/parovani-kandidatu-v2.md`. Všechna spojení včetně nejistých jsou ke stažení jako [otevřená data](https://mistnik-cz.web.app/data).

## Postup

```
python3 src/linkage.py        # skóre párů kandidatur -> data/derived/linkage_edges.csv.gz
python3 src/cluster.py        # rozhodnutí a skládání osob -> cluster_edges / cluster_persons
python3 src/occ_cards.py      # třídění povolání -> data/mockup/povolani.html
python3 src/build_site.py     # statický web -> site/ (včetně otevřených dat)
python3 tests/test_match.py
```

Vstupní data (ČSÚ, četnosti jmen MV ČR) se do repozitáře nedávají; odkud je stáhnout, popisuje `data/README.md`. Dotazy na jazykové modely (Jev, Gemini) jdou přes OpenRouter a potřebují `OPENROUTER_API_KEY`.

Chyba nebo námitka: opravy@mistnik.cz
