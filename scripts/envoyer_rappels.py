#!/usr/bin/env python3
"""
Vérifie s'il y a un anniversaire/fête demain et envoie un e-mail de rappel.
Exécuté quotidiennement par GitHub Actions (voir .github/workflows/verif-anniversaires.yml).

Variables d'environnement attendues :
  GMAIL_USER          adresse Gmail expéditrice
  GMAIL_APP_PASSWORD  mot de passe d'application Gmail (PAS le mot de passe normal)
  DESTINATAIRE_SECOURS (optionnel) utilisé si "destinataire" est vide dans le JSON
"""

import json
import os
import smtplib
import sys
from datetime import date, timedelta
from email.mime.text import MIMEText
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    DEMAIN = (date.today())  # date.today() suffit : le workflow tourne une fois/jour, TZ gérée par le cron
except ImportError:
    ZoneInfo = None

CHEMIN_JSON = Path(__file__).resolve().parent.parent / "data" / "anniversaires.json"

NOMS_MOIS = ["janvier","février","mars","avril","mai","juin","juillet",
             "août","septembre","octobre","novembre","décembre"]


def charger_donnees():
    with open(CHEMIN_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def evenements_de_demain(evenements, demain):
    resultats = []
    for evt in evenements:
        if not evt.get("jour"):
            continue  # date incomplète, ignoré tant qu'Henri n'a pas précisé le jour
        if evt["jour"] == demain.day and evt["mois"] == demain.month:
            resultats.append(evt)
    return resultats


def prochaine_occurrence(evt, aujourdhui):
    """Prochaine date (>= aujourd'hui) à laquelle tombe cet événement, ignorant l'année."""
    annee = aujourdhui.year
    candidate = date(annee, evt["mois"], evt["jour"])
    if candidate < aujourdhui:
        candidate = date(annee + 1, evt["mois"], evt["jour"])
    return candidate


def trouver_prochain_evenement(evenements, aujourdhui):
    """Utilisé en mode test : l'événement réel le plus proche dans le temps (jour connu requis)."""
    candidats = [(prochaine_occurrence(e, aujourdhui), e) for e in evenements if e.get("jour")]
    if not candidats:
        return None
    candidats.sort(key=lambda c: c[0])
    return candidats[0]  # (date_occurrence, evenement)


def construire_message(evenements_matches, demain):
    lignes = []
    for evt in evenements_matches:
        ligne = f"- {evt['nom']} : {evt['type']}"
        if evt.get("annee"):
            age = demain.year - evt["annee"]
            ligne += f" ({age} ans)"
        lignes.append(ligne)

    date_txt = f"{demain.day} {NOMS_MOIS[demain.month - 1]} {demain.year}"
    corps = f"Rappel : demain {date_txt}, c'est :\n\n" + "\n".join(lignes)
    sujet = f"🎂 Rappel — {', '.join(e['nom'] for e in evenements_matches)} demain"
    return sujet, corps


def envoyer_email(destinataire, sujet, corps):
    expediteur = os.environ["GMAIL_USER"]
    mot_de_passe = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEText(corps, "plain", "utf-8")
    msg["Subject"] = sujet
    msg["From"] = expediteur
    msg["To"] = destinataire

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as serveur:
        serveur.login(expediteur, mot_de_passe)
        serveur.sendmail(expediteur, [destinataire], msg.as_string())


def main():
    donnees = charger_donnees()
    destinataire = donnees.get("destinataire") or os.environ.get("DESTINATAIRE_SECOURS", "")
    forcer_test = os.environ.get("FORCER_TEST", "false").strip().lower() == "true"

    if not destinataire:
        print("Aucun destinataire configuré (ni dans le JSON, ni en secours). Abandon.")
        sys.exit(1 if forcer_test else 0)  # un test doit remonter en échec ; le cron quotidien reste silencieux

    if forcer_test:
        aujourdhui = date.today()
        trouve = trouver_prochain_evenement(donnees.get("evenements", []), aujourdhui)
        if not trouve:
            print("Mode test : aucun événement avec une date connue dans le fichier. Abandon.")
            sys.exit(1)
        date_occurrence, evt = trouve
        sujet, corps = construire_message([evt], date_occurrence)
        sujet = "[TEST] " + sujet
        corps = ("Ceci est un e-mail de TEST déclenché manuellement depuis l'app "
                  "(pas un vrai rappel).\nIl emprunte le prochain événement réel du "
                  "calendrier pour vérifier toute la chaîne : lecture du fichier, "
                  "mise en forme, envoi Gmail.\n\n") + corps
        envoyer_email(destinataire, sujet, corps)
        print(f"[TEST] E-mail envoyé à {destinataire} (événement emprunté : {evt['nom']}).")
        return

    demain = date.today() + timedelta(days=1)
    matches = evenements_de_demain(donnees.get("evenements", []), demain)
    if not matches:
        print(f"Rien à signaler pour le {demain.isoformat()}.")
        return

    sujet, corps = construire_message(matches, demain)
    envoyer_email(destinataire, sujet, corps)
    print(f"E-mail envoyé à {destinataire} pour {len(matches)} événement(s).")


if __name__ == "__main__":
    main()
