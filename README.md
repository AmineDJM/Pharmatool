# Algeria Pharma Market Intelligence

Outil interne d'aide à la décision pour le marché pharmaceutique algérien.
Croise trois sources officielles — **IQVIA** (marché de ville), **PCH** (réceptions
hospitalières) et la **Nomenclature** (enregistrements, fabricants locaux vs
importateurs) — pour dimensionner les marchés, analyser la concurrence et
prioriser les opportunités produit.

> Build : `v5.0 · IQVIA 2026 · competition-suite`

## Ce que fait l'outil

L'application est organisée en **4 pages** :

1. **🏠 Vue d'ensemble** — tableau de bord du marché : taille totale (DZD/USD),
   croissance vs N-1, classes thérapeutiques porteuses, laboratoires leaders,
   concentration (HHI) et dynamique (top croissance / déclin).
2. **🔬 Analyse produit / DCI** — recherche stricte et *pharma-safe* par molécule,
   filtres connectés (dosage, forme, laboratoire, statut), marché ville + hospitalier,
   **paysage concurrentiel** (parts, croissance, fabricants locaux vs importateurs,
   HHI) et export Excel.
3. **🏟️ Analyse concurrentielle** — concurrence par **classe thérapeutique**
   (qui sont les acteurs, parts, croissance, concentration) ou par **laboratoire**
   (portefeuille, exposition, momentum).
4. **🧠 Opportunités stratégiques** — screening automatique des DCI à fort
   potentiel selon la taille de marché, la croissance et l'intensité concurrentielle
   locale. Met en avant les opportunités de **substitution aux importations**.

## Points clés techniques

- **Intégration IQVIA 2026 dynamique** : les colonnes de période (MAT / YTD / mois)
  et l'année sont détectées automatiquement — déposer un futur fichier (2027, …)
  dans `data/` suffit, aucun changement de code.
- **Chiffres réconciliés** : la valeur de marché est dédupliquée au niveau
  produit-présentation et correspond exactement aux totaux officiels IQVIA
  (la feuille molécule répète la valeur par molécule, ce qui est neutralisé).
- **Croissance agrégée robuste** : reconstruction de la valeur N-1 par ligne
  (insensible aux valeurs aberrantes), au lieu d'une moyenne de pourcentages.
- **Matching DCI sûr** : évite les confusions de molécules proches
  (ex. raltégravir ≠ dolutégravir).

## Structure du code

| Fichier | Rôle |
|---|---|
| `app.py` | Point d'entrée + navigation + réglages |
| `ui_theme.py` | Design, CSS responsive, formatage, composants (KPI, pills…) |
| `market_engine.py` | Chargement, normalisation, matching, analytics, exports |
| `market_overview_page.py` | Page Vue d'ensemble |
| `market_analysis_page.py` | Page Analyse produit / DCI |
| `competition_page.py` | Page Analyse concurrentielle |
| `strategic_recommendations.py` | Page Opportunités stratégiques |
| `data/` | Fichiers Excel source (IQVIA / PCH / Nomenclature) |

## Lancer localement

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Données

Placer dans `data/` :

- `Algeria IQVIA Data March 26.xlsx` (ou version plus récente) — marché de ville
- `Reception2025_copy.xlsx` — réceptions hospitalières PCH
- `NOMENCLATURE.VERSION.AVRIL_.2026-.xlsx` — nomenclature officielle

Les fichiers sont détectés automatiquement par motif de nom ; la version IQVIA
la plus récente (par année) est sélectionnée.
