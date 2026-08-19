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
import re
import smtplib
import sys
import unicodedata
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
        if evt.get("noMail"):
            continue  # rappel désactivé pour cette personne
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
    """Utilisé en mode test : l'événement réel le plus proche dans le temps (jour connu requis, rappel activé)."""
    candidats = [(prochaine_occurrence(e, aujourdhui), e) for e in evenements if e.get("jour") and not e.get("noMail")]
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


def envoyer_email(destinataires, sujet, corps):
    expediteur = os.environ["GMAIL_USER"]
    mot_de_passe = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEText(corps, "plain", "utf-8")
    msg["Subject"] = sujet
    msg["From"] = expediteur
    msg["To"] = ", ".join(destinataires)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as serveur:
        serveur.login(expediteur, mot_de_passe)
        serveur.sendmail(expediteur, destinataires, msg.as_string())


def caracteres_suspects(s):
    """Répertorie les caractères invisibles/inattendus (retour à la ligne, espace
    insécable, tabulation...) sans jamais révéler les caractères normaux du secret."""
    suspects = []
    for i, c in enumerate(s):
        cat = unicodedata.category(c)
        est_normal = c.isascii() and (c.isalnum() or c in " -_.@")
        if not est_normal:
            nom = unicodedata.name(c, f"U+{ord(c):04X}")
            suspects.append(f"position {i} : {nom} (catégorie {cat}, code U+{ord(c):04X})")
    return suspects


def resume_secret(nom_variable, valeur):
    lignes = [f"--- {nom_variable} ---"]
    if valeur is None:
        lignes.append("Absent de l'environnement (secret non défini côté GitHub).")
        return lignes
    lignes.append(f"Longueur brute : {len(valeur)} caractère(s)")
    lignes.append(f"Longueur après .strip() : {len(valeur.strip())}")
    sans_espaces = re.sub(r"\s+", "", valeur)
    lignes.append(f"Longueur sans aucun espace/saut de ligne : {len(sans_espaces)}")
    if valeur != valeur.strip():
        lignes.append("⚠️ Espace(s) ou retour(s) à la ligne en début/fin détecté(s).")
    if " " in valeur.strip():
        lignes.append("⚠️ Espace(s) au milieu de la valeur détecté(s).")
    suspects = caracteres_suspects(valeur)
    if suspects:
        lignes.append("⚠️ Caractère(s) non-standard détecté(s) :")
        lignes.extend(f"   - {s}" for s in suspects)
    else:
        lignes.append("Aucun caractère non-standard détecté.")
    if len(valeur) >= 4:
        lignes.append(f"Aperçu (2 premiers + 2 derniers caractères) : {valeur[:2]}···{valeur[-2:]}")
    return lignes


def tenter_connexion(expediteur, mot_de_passe, etiquette):
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as serveur:
            serveur.login(expediteur, mot_de_passe)
        return f"✅ Connexion réussie avec la variante « {etiquette} »."
    except smtplib.SMTPAuthenticationError as e:
        return f"❌ Échec avec la variante « {etiquette} » : {e.smtp_code} {e.smtp_error.decode('utf-8', 'replace')[:120]}"
    except Exception as e:
        return f"❌ Erreur inattendue avec la variante « {etiquette} » : {type(e).__name__} — {e}"


def diagnostiquer_gmail():
    print("=" * 60)
    print("DIAGNOSTIC GMAIL_USER / GMAIL_APP_PASSWORD")
    print("=" * 60)

    user_brut = os.environ.get("GMAIL_USER")
    pass_brut = os.environ.get("GMAIL_APP_PASSWORD")

    for ligne in resume_secret("GMAIL_USER", user_brut):
        print(ligne)
    print()
    for ligne in resume_secret("GMAIL_APP_PASSWORD", pass_brut):
        print(ligne)
    print()

    if user_brut and "@" not in user_brut:
        print("⚠️ GMAIL_USER ne contient pas de « @ » — ce n'est probablement pas une adresse e-mail valide.")

    if pass_brut:
        longueur_nette = len(re.sub(r"\s+", "", pass_brut))
        if longueur_nette != 16:
            print(f"⚠️ Un mot de passe d'application Google fait normalement 16 caractères "
                  f"une fois les espaces retirés ; ici : {longueur_nette}. "
                  f"Vérifie qu'il ne s'agit pas du mot de passe habituel du compte.")

    if not user_brut or not pass_brut:
        print("\nImpossible de tenter une connexion : au moins un des deux secrets est absent.")
        return

    print("\n--- Tentatives de connexion SMTP (login uniquement, aucun e-mail envoyé) ---")
    user_nettoye = user_brut.strip()
    pass_nettoye = re.sub(r"\s+", "", pass_brut)

    resultats = []
    resultats.append(tenter_connexion(user_brut, pass_brut, "valeurs brutes (telles que stockées)"))
    if (user_nettoye, pass_nettoye) != (user_brut, pass_brut):
        resultats.append(tenter_connexion(user_nettoye, pass_nettoye, "valeurs nettoyées (espaces/sauts de ligne retirés)"))

    for r in resultats:
        print(r)

    print("\n--- Interprétation ---")
    if any(r.startswith("✅") for r in resultats):
        print("Au moins une variante fonctionne : le problème vient bien d'un espace/caractère "
              "invisible dans le secret stocké sur GitHub. Recopie la valeur qui a réussi ci-dessus "
              "(nettoyée) comme secret GMAIL_APP_PASSWORD.")
    else:
        print("Aucune variante ne fonctionne : ce n'est probablement pas un problème de format. "
              "Causes les plus fréquentes : (1) le mot de passe d'application a été révoqué/régénéré "
              "depuis — il faut en créer un nouveau et remettre à jour le secret ; "
              "(2) la validation en 2 étapes n'est en réalité pas active sur ce compte Google ; "
              "(3) GMAIL_USER ne correspond pas au compte Google sur lequel ce mot de passe a été créé ; "
              "(4) le compte est un compte Google Workspace dont l'administrateur bloque l'accès SMTP.")


def lire_destinataires(donnees):
    """Lit la liste de destinataires, avec repli sur l'ancien format à une seule adresse
    (clé "destinataire") pour rester compatible avec un fichier JSON pas encore migré."""
    liste = donnees.get("destinataires")
    if liste:
        return [d.strip() for d in liste if d and d.strip()]
    ancien = donnees.get("destinataire")
    if ancien:
        return [ancien.strip()]
    secours = os.environ.get("DESTINATAIRE_SECOURS", "")
    return [secours] if secours else []


def main():
    if os.environ.get("DIAGNOSTIQUER_GMAIL", "false").strip().lower() == "true":
        diagnostiquer_gmail()
        return

    donnees = charger_donnees()
    destinataires = lire_destinataires(donnees)
    forcer_test = os.environ.get("FORCER_TEST", "false").strip().lower() == "true"

    if not destinataires:
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
        envoyer_email(destinataires, sujet, corps)
        print(f"[TEST] E-mail envoyé à {', '.join(destinataires)} (événement emprunté : {evt['nom']}).")
        return

    demain = date.today() + timedelta(days=1)
    matches = evenements_de_demain(donnees.get("evenements", []), demain)
    if not matches:
        print(f"Rien à signaler pour le {demain.isoformat()}.")
        return

    sujet, corps = construire_message(matches, demain)
    envoyer_email(destinataires, sujet, corps)
    print(f"E-mail envoyé à {', '.join(destinataires)} pour {len(matches)} événement(s).")


if __name__ == "__main__":
    main()
