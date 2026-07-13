# Commandes


## Création du virtualenv
```bash
python -m venv env
```

## Activation du virtualenv
```bash
source env/bin/activate
```

## Téléchargement des packages
```bash
pip install -r requirements.txt
```

## Connexion à Finary
```bash
python -m finary_uapi signing [MFA_CODE]
```

## Vérification de la connexion à Finary
```bash
python -m finary_uapi me
```

## Génération des fichiers CSV et commandes

### Génération d'un fichier CSV pour le compte PEA Trade Republic
```bash
python .\main.py '.\data\Exportation de transactions.csv' --decimals 2 --account PEA --keep-zero -o .\data\finary_PEA.csv
```

### Génération d'un fichier CSV pour le compte CTO Trade Republic
```bash
python .\main.py '.\data\Exportation de transactions.csv' --decimals 2 --account DEFAULT --keep-zero -o .\data\finary_CTO.csv
```

### Génération de la commande de mise à jour du compte CASH Trade Republic dans Finary
```bash
python main.py '.\data\Exportation de transactions.csv' --decimals 2 --cash --cash-account-id "77fda958-0f7d-4e73-81c6-2b2e3316c911" --cash-account-name "Trade Republic - Cash"
```

## Mise à jour des comptes Trade Republic dans Finary

### Mise à jour du compte CTO Trade Republic dans Finary
```bash
python -m finary_uapi import stocks_csv .\data\finary_PEA.csv --edit="Trade Republic - PEA"
```

### Mise à jour du compte CTO Trade Republic dans Finary
```bash
python -m finary_uapi import stocks_csv .\data\finary_CTO.csv --edit="Trade Republic - CTO"
```

### Mise à jour du compte CASH Trade Republic dans Finary
```bash
python -m finary_uapi holdings_accounts update "77fda958-0f7d-4e73-81c6-2b2e3316c911" "Trade Republic - Cash" xxx.xx
```# Trade_Republic_to_Finary
# Trade_Republic_to_Finary
