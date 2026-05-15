# Algeria Pharma Market Intelligence

Build: v4.5 modular-ui-responsive

## Structure

- `app.py` : point d'entrée Streamlit + navigation uniquement.
- `ui_theme.py` : design, CSS, responsive mobile/desktop, formatage visuel.
- `market_analysis_page.py` : page Analyse produit / DCI.
- `strategic_recommendations.py` : page Recommandations stratégiques.
- `market_engine.py` : moteur data/matching/exports.
- `data/` : fichiers Excel source.

## Modifier uniquement le design

Changer seulement :

```text
ui_theme.py
```

## Modifier uniquement la page Analyse de marché

Changer seulement :

```text
market_analysis_page.py
```

## Modifier uniquement la page Recommandations

Changer seulement :

```text
strategic_recommendations.py
```

## Lancer localement

```bash
pip install -r requirements.txt
streamlit run app.py
```
