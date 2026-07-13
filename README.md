# Trade Republic → Finary

Script Python qui convertit l'export CSV de transactions **Trade Republic** en fichiers directement importables dans **Finary** via la librairie [`finary_uapi`](https://github.com/lasconic/finary_uapi).

Trade Republic n'étant pas agrégeable automatiquement dans Finary (pas de connecteur Powens fonctionnel), ce script reconstruit les positions à partir du journal de transactions et génère :

- un **CSV de positions** (`isin_code, description, quantity, price, currency`) au format `stocks_csv`, avec le PRU (prix de revient unitaire moyen pondéré) ;
- la **commande de mise à jour du solde espèces** prête à coller.

---

## Sommaire

- [Fonctionnement](#fonctionnement)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration Finary](#configuration-finary)
- [Export des transactions Trade Republic](#export-des-transactions-trade-republic)
- [Utilisation](#utilisation)
  - [Options](#options)
  - [Générer les positions (PEA / CTO)](#générer-les-positions-pea--cto)
  - [Générer la commande de solde cash](#générer-la-commande-de-solde-cash)
- [Import dans Finary](#import-dans-finary)
- [Workflow complet](#workflow-complet)
- [Traitement des catégories Trade Republic](#traitement-des-catégories-trade-republic)
- [Limitations connues](#limitations-connues)

---

## Fonctionnement

Le format attendu par `finary_uapi import stocks_csv` est une liste de **positions agrégées**, et non de transactions. Le script parcourt donc le journal Trade Republic et, pour chaque ISIN :

1. accumule les achats (`TRADING/BUY`) → quantité + base de coût (frais inclus) ;
2. déduit les ventes (`TRADING/SELL`) au PRU courant ;
3. applique les opérations sur titres (`CORPORATE_ACTION` : splits, fusions, bonus) en ajustant uniquement la quantité ;
4. calcule le PRU final = coût total restant / quantité détenue.

Le résultat est écrit dans un CSV importable tel quel.

---

## Prérequis

- Python 3.8+
- Un compte Finary avec les comptes cibles **déjà créés manuellement** (ex. `Trade Republic - PEA`, `Trade Republic - CTO`, `Trade Republic - Cash`)
- L'export CSV natif des transactions Trade Republic

---

## Installation

```bash
git clone https://github.com/n-milleret/Trade_Republic_to_Finary.git
cd Trade_Republic_to_Finary
```

Création et activation du virtualenv :

```bash
python -m venv env
source env/bin/activate        # Linux / macOS
.\env\Scripts\activate         # Windows
```

Installation des dépendances :

```bash
pip install -r requirements.txt
```

---

## Configuration Finary

Créer un fichier `credentials.json` à la racine :

```json
{
    "email": "myemail@provider.tld",
    "password": "mypassword"
}
```

> ⚠️ Ce fichier contient vos identifiants en clair. Il est ignoré par `.gitignore` — ne le committez jamais.

Connexion (un code MFA vous est envoyé par email) :

```bash
python -m finary_uapi signin [MFA_CODE]
```

Vérification que la session est active :

```bash
python -m finary_uapi me
```

Récupérer les UUID de vos comptes (nécessaire pour le mode `--cash`) :

```bash
python -m finary_uapi holdings_accounts
```

---

## Export des transactions Trade Republic

Depuis l'application Trade Republic : **Profil → Relevés / Transactions → Exporter**.
Placez le fichier obtenu (ex. `Exportation de transactions.csv`) dans un dossier `data/`.

Colonnes utilisées par le script : `category`, `type`, `asset_class`, `symbol` (ISIN), `name`, `account_type`, `currency`, `shares`, `price`, `fee`, `amount`.

---

## Utilisation

```bash
python main.py <fichier_transactions.csv> [options]
```

### Options

| Option | Défaut | Description |
|---|---|---|
| `input` | *(requis)* | Chemin du CSV de transactions Trade Republic |
| `-o`, `--output` | `stdout` | Fichier CSV de sortie |
| `--account` | `DEFAULT` | Comptes à inclure : `DEFAULT` (CTO), `PEA`, ou `ALL` |
| `--asset-class` | `STOCK FUND` | Classes d'actifs : `STOCK`, `FUND`, `CRYPTO`, ou `ALL` |
| `--keep-zero` | *(off)* | Conserver les positions soldées (quantité ≈ 0) |
| `--decimals` | `8` | Nombre de décimales pour la quantité et le PRU |
| `--verbose` | *(off)* | Affiche les catégories ignorées sur `stderr` |
| `--cash` | *(off)* | Mode solde espèces : calcule le cash et génère la commande de mise à jour |
| `--cash-account-id` | — | UUID du compte espèces Finary — **obligatoire avec `--cash`** |
| `--cash-account-name` | — | Nom du compte espèces Finary — **obligatoire avec `--cash`** |

> `--decimals 2` est recommandé pour l'import Finary (`stocks_csv`), et `--keep-zero` permet de faire remonter à zéro les lignes soldées côté Finary plutôt que de les laisser figées.

### Générer les positions (PEA / CTO)

Compte **PEA** :

```bash
python main.py './data/Exportation de transactions.csv' \
    --decimals 2 --account PEA --keep-zero \
    -o ./data/finary_PEA.csv
```

Compte **CTO** (`DEFAULT` chez Trade Republic) :

```bash
python main.py './data/Exportation de transactions.csv' \
    --decimals 2 --account DEFAULT --keep-zero \
    -o ./data/finary_CTO.csv
```

Sortie (`finary_PEA.csv`) :

```csv
isin_code,description,quantity,price,currency
IE00B4L5Y983,iShares Core MSCI World,12.5,89.42,EUR
US0378331005,Apple Inc.,3,168.11,EUR
```

### Générer la commande de solde cash

Le solde espèces est la somme de tous les champs `amount`, **tous comptes confondus**.

```bash
python main.py './data/Exportation de transactions.csv' \
    --decimals 2 --cash \
    --cash-account-id "77fda958-0f7d-4e73-81c6-2b2e3316c911" \
    --cash-account-name "Trade Republic - Cash"
```

Le script affiche le solde sur `stderr` et la commande prête à exécuter sur `stdout` :

```
# Solde cash Trade Republic (tous comptes) : 1234.56 EUR
python -m finary_uapi holdings_accounts update "77fda958-0f7d-4e73-81c6-2b2e3316c911" "Trade Republic - Cash" 1234.56
```

---

## Import dans Finary

Mise à jour du **PEA** :

```bash
python -m finary_uapi import stocks_csv ./data/finary_PEA.csv --edit="Trade Republic - PEA"
```

Mise à jour du **CTO** :

```bash
python -m finary_uapi import stocks_csv ./data/finary_CTO.csv --edit="Trade Republic - CTO"
```

Mise à jour du **compte espèces** (coller la commande générée par `--cash`) :

```bash
python -m finary_uapi holdings_accounts update "77fda958-0f7d-4e73-81c6-2b2e3316c911" "Trade Republic - Cash" 1234.56
```

> La valeur passée à `--edit` doit correspondre **exactement** au nom du compte tel qu'il existe dans Finary.

---

## Workflow complet

```bash
# 1. Activer l'environnement
source env/bin/activate

# 2. Se connecter à Finary
python -m finary_uapi signin [MFA_CODE]

# 3. Générer les CSV de positions
python main.py './data/Exportation de transactions.csv' --decimals 2 --account PEA     --keep-zero -o ./data/finary_PEA.csv
python main.py './data/Exportation de transactions.csv' --decimals 2 --account DEFAULT --keep-zero -o ./data/finary_CTO.csv

# 4. Importer les positions
python -m finary_uapi import stocks_csv ./data/finary_PEA.csv --edit="Trade Republic - PEA"
python -m finary_uapi import stocks_csv ./data/finary_CTO.csv --edit="Trade Republic - CTO"

# 5. Mettre à jour le solde espèces
python main.py './data/Exportation de transactions.csv' --decimals 2 --cash \
    --cash-account-id "<UUID>" --cash-account-name "Trade Republic - Cash"
# puis exécuter la commande affichée
```

---

## Traitement des catégories Trade Republic

| Catégorie | Type | Traitement |
|---|---|---|
| `TRADING` | `BUY` | Ajoute des parts, augmente la base de coût (frais inclus) |
| `TRADING` | `SELL` | Retire des parts en réduisant la base de coût au PRU courant |
| `TRADING` | *autre* | Ajustement de quantité seul |
| `CORPORATE_ACTION` | split, fusion, bonus | Ajustement de quantité sans cash (le PRU se dilue) |
| `DELIVERY` | `FREE_RECEIPT` / `FREE_DELIVERY` | **Entièrement ignoré** (voir ci-dessous) |
| `CASH` | dividendes, virements, `STOCKPERK` | Ignoré pour les positions ; comptabilisé en mode `--cash` |

### Pourquoi `DELIVERY` est ignoré

Les lignes `DELIVERY` sont des transferts internes neutres (générés notamment par la migration des comptes français de Trade Republic en février 2025). Elles arrivent **par paires** (`-x` puis `+x`) sur le même ISIN et se compensent.

Les appliquer naïvement **détruit la base de coût** : la ligne `-x` fait tomber la quantité à zéro, ce qui remet le coût — donc le PRU — à zéro, et la ligne `+x` rétablit la quantité sans prix. Ces lignes ne portant aucune information de position, elles sont écartées intégralement.

---

## Limitations connues

- **Fusions (`MERGER`)** : Trade Republic génère deux lignes (ancien ISIN `-qty`, nouvel ISIN `+qty`). Chacune étant traitée sur sa propre clé ISIN, l'ancien titre tombe à 0 et le **nouveau démarre avec un coût nul** (PRU = 0). Un ajustement manuel est nécessaire dans Finary après une fusion.
- **`STOCKPERK`** (actions offertes) : le CSV ne fournit pas de champ `shares`, ces lignes sont donc ignorées pour le calcul du PRU.
- Le PRU est un **coût moyen pondéré** incluant les frais ; il ne correspond pas nécessairement au calcul fiscal officiel.
- Le solde cash est global (tous comptes confondus) et n'est pas ventilé par compte.

---

## Licence

Usage personnel. Projet non affilié à Trade Republic ni à Finary.