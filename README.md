# 💸 Suivi virements salaires & CNSS — v5

App Streamlit de suivi/mise à jour/export des virements salaire et cotisations CNSS.
Base JSON incrémentale, persistée sur Google Drive, **authentification par mot de passe
avec rôles**, régularité calculée **au jour**, stockage durci (erreurs visibles, verrou
optimiste, rotation des backups).

## Nouveautés v5 (vs v4)
- **Authentification + rôles** (`auth.py`) : `superadmin` (lecture/écriture) et `user` (lecture + export). Mots de passe dans `st.secrets`.
- **Dates au jour** (`dates.py`) : `aujourdhui()` + fuseau Africa/Casablanca ; régularité basée sur `date_paiement` vs `date_echeance` (payer le 28 un dû le 10 = *retard*).
- **Champ technique `date_paiement`** (schéma passe à 9 champs ; export toujours 8 colonnes).
- **Stockage durci** (`storage.py`) : API Drive v3 + `google-auth` (fin d'`oauth2client`), scope `drive.file`, **erreurs non silencieuses → lecture seule**, **verrou optimiste** par révision, **rotation** des backups.
- **Sécurité** : HTML échappé, validation montant/mois à l'import, fusion qui **préserve le payé**, confirmation avant *Remplacer*.
- **Panneau Rappels** + ré-export **ICS** ; badge *en retard* distinct de *payé en retard*.
- **Tests** (`tests/test_logic.py`).

## Fichiers
| Fichier | Rôle |
|---|---|
| `app.py` | UI : porte d'auth, 4 panneaux, rendu conditionnel par rôle |
| `auth.py` | Mot de passe + rôles (`st.secrets`) |
| `dates.py` | Date courante (fuseau Casablanca) |
| `db_gen.py` | Génération de mois (barème, anti-doublon, renumérotation) |
| `integrity.py` | Réconciliation, régularité au jour, détection payé/non payé |
| `rapport.py` | Export Excel (8 colonnes) + ICS rappels |
| `storage.py` | Persistance Drive durcie + repli local |
| `tests/` | Tests logiques |

## Barème mensuel (8 500 DH)
10 → Salaire 2 500 · 10 → CNSS 1 500 · 20 → Salaire 2 500 · 30 (ou dernier jour) → Salaire 2 000.

## Lancer en local
```bash
pip install -r requirements.txt
streamlit run app.py
```
Renseigner au minimum le bloc `[auth]` dans `.streamlit/secrets.toml` (sinon connexion impossible). Sans `[gdrive]`, stockage **local** (`data.json` + `backups/`).

## Secrets (local : `.streamlit/secrets.toml` · cloud : Settings → Secrets)
```toml
[auth]
superadmin_password = "MOT_DE_PASSE_ADMIN"
user_password = "MOT_DE_PASSE_LECTEUR"

[gdrive]
folder_id = "ID_DU_DOSSIER_DRIVE"

[gdrive.service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"
```

### Reset d'un mot de passe
Les mots de passe vivent dans les secrets, pas dans une base. Pour en changer :
**Streamlit Cloud** → App → Settings → Secrets → modifier la valeur → Save (l'app redémarre).
**Local** → éditer `.streamlit/secrets.toml`. La « clé maîtresse » est l'accès au compte Streamlit Cloud / GitHub.

## Google Drive (service account)
1. Google Cloud → projet → activer **Google Drive API**.
2. **Service account** → clé **JSON**.
3. Drive → créer un dossier → **Partager** (Éditeur) avec l'email du compte de service → copier l'**ID** du dossier.
4. Coller la clé dans `[gdrive.service_account]` et l'ID dans `folder_id`.

## Déploiement Streamlit Cloud
Pousser le repo (le `.gitignore` exclut secrets, `data.json`, `backups/`), puis New app → `app.py` → coller les secrets.

## Tests
```bash
pip install pytest && pytest -q
```
