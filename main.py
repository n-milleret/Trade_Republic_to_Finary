#!/usr/bin/env python3
"""
Trade Republic transactions CSV  ->  finary_uapi stocks_csv (positions/holdings)

Le format cible attendu par `finary_uapi import stocks_csv` est une liste de
POSITIONS agrégées, pas de transactions :
    isin_code, description, quantity, price, currency
où `quantity` = quantité totale détenue et `price` = PRU (prix de revient unitaire).

Ce script lit le journal de transactions Trade Republic, reconstruit chaque
position (quantité nette + PRU moyen pondéré sur les achats) puis écrit un CSV
importable tel quel.

Usage:
    python tr_to_finary.py transactions.csv -o finary_positions.csv
    python tr_to_finary.py transactions.csv --account DEFAULT --asset-class STOCK FUND
    python tr_to_finary.py transactions.csv --account PEA -o pea.csv
    python tr_to_finary.py transactions.csv --keep-zero --verbose
"""

import argparse
import csv
import sys
from collections import OrderedDict
from decimal import Decimal, InvalidOperation


def D(value: str) -> Decimal:
    """Parse robuste en Decimal ('' -> 0)."""
    if value is None:
        return Decimal("0")
    value = value.strip()
    if value == "":
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal("0")


class Position:
    __slots__ = ("isin", "name", "asset_class", "currency", "qty", "cost")

    def __init__(self, isin, name, asset_class, currency):
        self.isin = isin
        self.name = name
        self.asset_class = asset_class
        self.currency = currency
        self.qty = Decimal("0")    # quantité nette détenue
        self.cost = Decimal("0")   # coût total restant (base du PRU)

    def buy(self, shares: Decimal, price: Decimal, fee: Decimal):
        """Achat : ajoute des parts, augmente la base de coût (frais inclus)."""
        if shares <= 0:
            return
        self.qty += shares
        self.cost += shares * price + fee

    def sell(self, shares: Decimal):
        """Vente : retire des parts en réduisant la base de coût au PRU courant."""
        shares = abs(shares)
        if shares <= 0 or self.qty <= 0:
            self.qty -= shares
            return
        pru = self.cost / self.qty
        self.qty -= shares
        self.cost -= pru * shares
        if self.qty <= 0:
            self.qty = Decimal("0")
            self.cost = Decimal("0")

    def adjust_qty(self, shares: Decimal):
        """Ajustement de quantité sans cash (split, bonus) : PRU se dilue seul."""
        self.qty += shares
        if self.qty <= 0:
            self.qty = Decimal("0")
            self.cost = Decimal("0")

    @property
    def pru(self) -> Decimal:
        if self.qty <= 0:
            return Decimal("0")
        return self.cost / self.qty


# Catégories du CSV TR à ignorer totalement pour les positions titres :
# mouvements de cash pur, cartes, intérêts, dividendes, versements PEA, etc.
CASH_CATEGORIES = {"CASH", "DELIVERY"}  # DELIVERY = transferts internes neutres (paires -/+)

# Types de trades qui augmentent/diminuent une position
BUY_TYPES = {"BUY"}
SELL_TYPES = {"SELL"}


def process(rows, account_filter=None, asset_classes=None, verbose=False):
    positions = OrderedDict()  # clé = (account_type, isin)

    for r in rows:
        category = r.get("category", "").strip()
        ttype = r.get("type", "").strip()
        asset_class = r.get("asset_class", "").strip()
        isin = r.get("symbol", "").strip()
        name = r.get("name", "").strip()
        account = r.get("account_type", "").strip()
        currency = r.get("currency", "").strip() or "EUR"

        # Filtre compte (DEFAULT / PEA)
        if account_filter and account not in account_filter:
            continue

        # On ne garde que les lignes rattachées à un titre identifiable par ISIN/symbole
        if not isin:
            continue

        # Filtre classe d'actif si demandé (STOCK, FUND, CRYPTO...)
        if asset_classes and asset_class not in asset_classes:
            continue

        shares = D(r.get("shares"))
        price = D(r.get("price"))
        fee = abs(D(r.get("fee")))

        key = (account, isin)
        pos = positions.get(key)
        if pos is None:
            pos = Position(isin, name, asset_class, currency)
            positions[key] = pos
        else:
            # garder un nom lisible si une ligne l'a et pas l'autre
            if not pos.name and name:
                pos.name = name

        if category == "TRADING":
            if ttype in BUY_TYPES:
                pos.buy(shares, price, fee)
            elif ttype in SELL_TYPES:
                pos.sell(shares)
            else:
                # autre type de trading inattendu : on ajuste la quantité
                pos.adjust_qty(shares)

        elif category == "CORPORATE_ACTION":
            # STOCK_SPLIT, MERGER, BONUS_ISSUE : ajustement de quantité sans cash.
            # Les mergers TR génèrent 2 lignes (ancien ISIN -qty, nouvel ISIN +qty),
            # chacune traitée sur sa propre clé ISIN => l'ancien tombe à 0, le
            # nouveau démarre à qty avec un coût nul. Voir note d'avertissement.
            pos.adjust_qty(shares)

        elif category == "DELIVERY":
            # FREE_RECEIPT / FREE_DELIVERY : transferts internes neutres qui
            # arrivent en paire (-x puis +x) sur le même ISIN. La somme est nulle
            # mais les appliquer via adjust_qty DÉTRUIT la base de coût : la ligne
            # -x fait tomber la quantité à 0, ce qui remet le coût (donc le PRU) à
            # zéro, et la ligne +x le rétablit sans prix. On les ignore donc
            # complètement : elles ne portent aucune information de position.
            continue

        elif category == "CASH":
            # STOCKPERK attribue parfois une action gratuite rattachée à un ISIN.
            if ttype == "STOCKPERK":
                # action offerte : +0 en quantité de parts ici (le CSV ne donne pas
                # de 'shares' pour le stockperk cash), on ignore pour le PRU.
                pass
            # DIVIDEND, CUSTOMER_INBOUND, TRANSFER_*, etc. : pas d'impact position.
            continue

        else:
            # catégorie inconnue : ignorée
            if verbose:
                print(f"[skip] catégorie inconnue: {category}/{ttype} {isin}",
                      file=sys.stderr)

    return positions


def main() -> int:
    p = argparse.ArgumentParser(
        description="Convertit un export de transactions Trade Republic "
                    "vers le format positions attendu par finary_uapi (stocks_csv).")
    p.add_argument("input", help="CSV de transactions Trade Republic")
    p.add_argument("-o", "--output", default=None,
                   help="CSV de sortie (défaut: stdout)")
    p.add_argument("--account", nargs="*", default=["DEFAULT"],
                   help="Comptes à inclure (ex: DEFAULT PEA). Défaut: DEFAULT. "
                        "Utiliser 'ALL' pour tout prendre.")
    p.add_argument("--asset-class", nargs="*", default=["STOCK", "FUND"],
                   help="Classes d'actifs à inclure (STOCK FUND CRYPTO). "
                        "Défaut: STOCK FUND.")
    p.add_argument("--keep-zero", action="store_true",
                   help="Garder aussi les positions soldées (quantité ~0).")
    p.add_argument("--decimals", type=int, default=8,
                   help="Décimales pour quantité et PRU (défaut 8).")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--cash", action="store_true",
                   help="Au lieu des positions, calcule le solde cash (somme de "
                        "tous les 'amount', tous comptes confondus) et affiche la "
                        "commande finary_uapi holdings_accounts update prête à coller.")
    p.add_argument("--cash-account-id", default=None,
                   help="UUID du compte espèces Trade Republic déjà présent dans "
                        "Finary (récupérable via 'finary_uapi holdings_accounts'). "
                        "Obligatoire avec --cash.")
    p.add_argument("--cash-account-name", default=None,
                   help="Nom du compte espèces dans Finary. Obligatoire avec --cash.")
    args = p.parse_args()

    if args.cash and (not args.cash_account_id or not args.cash_account_name):
        p.error("--cash requiert --cash-account-id ET --cash-account-name.")

    account_filter = None if "ALL" in args.account else set(args.account)
    asset_classes = None if "ALL" in args.asset_class else set(args.asset_class)

    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # --- Mode cash : solde = somme de tous les 'amount', tous comptes confondus ---
    if args.cash:
        balance = Decimal("0")
        for r in rows:
            balance += D(r.get("amount"))
        balance = balance.quantize(Decimal("0.01"))
        # Le compte cash existe déjà dans Finary : on met à jour son solde via
        #   holdings_accounts update <account_id> <account_name> [<account_balance>]
        cmd = (
            f'python -m finary_uapi holdings_accounts update '
            f'"{args.cash_account_id}" "{args.cash_account_name}" {balance}'
        )
        print(f"# Solde cash Trade Republic (tous comptes) : {balance} EUR",
              file=sys.stderr)
        print(cmd)
        return 0

    positions = process(rows, account_filter, asset_classes, args.verbose)

    q = Decimal(10) ** -args.decimals
    out_rows = []
    for (account, isin), pos in positions.items():
        if not args.keep_zero and pos.qty <= q:
            continue
        out_rows.append({
            "isin_code": isin,
            "description": pos.name,
            "quantity": str(pos.qty.quantize(q).normalize()),
            "price": str(pos.pru.quantize(q).normalize()),
            "currency": pos.currency,
        })

    # tri par description pour lisibilité
    out_rows.sort(key=lambda x: x["description"].lower())

    fieldnames = ["isin_code", "description", "quantity", "price", "currency"]
    out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    writer = csv.DictWriter(out, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for row in out_rows:
        writer.writerow(row)
    if args.output:
        out.close()
        print(f"{len(out_rows)} positions écrites dans {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())