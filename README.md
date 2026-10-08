# 💸 Suivi virements salaires & CNSS — Streamlit

App de **suivi, mise à jour et export** des virements salaires et cotisations CNSS.
Base **JSON incrémentale** (déclarée au fil de l'eau, durée non bornée), persistée sur
**Google Drive** (survie aux redéploiements Streamlit Cloud), avec import/maj par upload
JSON et contrôle d'intégrité au démarrage.

## Fichiers
| Fichier | Rôle |
|---|---|
| `app.py` | Interface : sidebar (mois courant figé · 3 panneaux · régularisation · import · diagnostic) |
| `db_gen.py` | Générateur de mois (barème, anti-doublon, renumérotation) |
| `integrity.py` | `reconcile()` : validation, dédoublonnage, détection payé/non payé |
| `rapport.py` | Export Excel du recap (8 colonnes + total) |
| `storage.py` | Persistance Google Drive + repli local |
| `requirements.txt` | Dépendances |
| `.streamlit/secrets.toml` | Modèle de configuration Drive (NON commité) |

## Barème mensuel (4 échéances = 8 500 DH)
- 10 — Salaire 1er versement : 2 500 DH
- 10 — CNSS : 1 500 DH
- 20 — Salaire 2e versement : 2 500 DH
- 30 (ou dernier jour) — Salaire 3e versement : 2 000 DH

## Lancer en local
```bash
pip install -r requirements.txt
streamlit run app.py
```
Sans secrets Drive, l'app tourne en **mode local** : `data.json` + `backups/` sur le disque.

## Persistance Google Drive (recommandé pour Streamlit Cloud)
1. **Google Cloud Console** → créer un projet → activer **Google Drive API**.
2. **Comptes de service** → créer un compte → générer une **clé JSON**.
3. Dans **Google Drive**, créer un dossier et le **partager** (Éditeur) avec l'email du
   compte de service (`...@...iam.gserviceaccount.com`). Noter l'**ID du dossier**
   (dans l'URL `https://drive.google.com/drive/folders/<ID>`).
4. Renseigner les secrets (voir `.streamlit/secrets.toml`) — en local dans ce fichier,
   sur le cloud via **App → Settings → Secrets** :
```toml
[gdrive]
folder_id = "ID_DU_DOSSIER"

[gdrive.service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"
```

## Déployer sur Streamlit Community Cloud
1. Pousser le dossier sur un dépôt GitHub (le `.gitignore` exclut secrets, `data.json`, `backups/`).
2. share.streamlit.io → **New app** → sélectionner le dépôt et `app.py`.
3. Coller les secrets Drive. L'app recrée/récupère `data.json` depuis Drive à chaque démarrage.

## Flux d'usage
- **1er lancement** : base vide → déclarer le **mois courant** (libre, pas de mois imposé).
- **Mois courant (figé)** : payer les échéances du mois système → tag *à temps*.
- **Régularisation** : déclarer/payer un mois **antérieur** (*retard*) ou **futur** (*avance*).
- **Récap & export** : KPIs + téléchargement Excel (payées / base complète).
- **Importer** : charger un `data.json` (Remplacer ou Fusionner) → persisté sur Drive.

## Récupération / anti-perte
- Chargement : **Drive principal → backup Drive → local → base vide**.
- Chaque sauvegarde écrit d'abord un **backup horodaté**, puis `data.json`.
- `reconcile()` répare doublons / rappels / schéma au démarrage et re-sauvegarde si besoin.
