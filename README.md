# GitHub Discord Notifier

Service Docker self-hosted pour surveiller ses dépôts GitHub et recevoir les événements utiles directement sur Discord.

## Fonctionnalités

- WebUI entièrement en français.
- Authentification locale intégrée.
- Connexion à GitHub par token personnel chiffré.
- Liste automatique des dépôts accessibles au compte.
- Sélection globale des dépôts avec **Tout sélectionner / Tout désélectionner**.
- Configuration globale des alertes et des destinations Discord appliquée à tous les dépôts surveillés.
- Réglages individuels facultatifs pour créer des exceptions dépôt par dépôt.
- Un ou plusieurs webhooks Discord.
- Plusieurs destinations Discord possibles pour un même dépôt.
- Alertes configurables :
  - nouvelles **Issues** ;
  - nouvelles **Pull Requests** ;
  - **GitHub Actions** terminées : échec, succès et/ou annulation ;
  - nouveaux **forks** ;
  - nouvelles **stars**.
- Option pour ignorer ses propres Pull Requests.
- Surveillance périodique des dépôts GitHub avec intervalle configurable.
- Intervalle réglable de 1 minute à 1 heure, 5 minutes recommandé.
- Journaux des alertes envoyées, ignorées et en erreur.
- La première vérification sert de référence : les anciens événements ne sont pas envoyés à Discord.

## Connexion GitHub

La WebUI demande un token GitHub personnel, vérifie le compte associé puis récupère les dépôts accessibles. Le token est chiffré dans SQLite et n'est plus affiché.

Créez de préférence un **[Fine-grained Personal Access Token](https://github.com/settings/personal-access-tokens/new)** :

1. choisissez les dépôts à surveiller ;
2. dans **Repository permissions**, accordez uniquement :
   - **Metadata: Read** ;
   - **Issues: Read** ;
   - **Pull requests: Read** ;
   - **Actions: Read** ;
3. générez le token puis collez-le dans la page **GitHub** de la WebUI.

L'application n'effectue aucune écriture sur GitHub.

## Alertes Discord

Les alertes sont envoyées sous forme d'embeds avec un lien direct vers GitHub.

### Issue

> <img src="app/static/octicons/issue-opened.svg" width="18" alt="Issue"> **Nouvelle issue #271**
>
> Start Guard fails with SSHFS mounts
>
> **Dépôt :** [Aerya/Dockge-Enhanced](https://github.com/Aerya/Dockge-Enhanced)
>
> **Auteur :** utilisateur
>
> **Labels :** bug, mounts
>
> Le titre de la notification Discord ouvre directement l'issue.

### Pull Request

> <img src="app/static/octicons/git-pull-request.svg" width="18" alt="Pull Request"> **Pull Request #272**
>
> Fix mount validation
>
> **Dépôt :** [Aerya/Dockge-Enhanced](https://github.com/Aerya/Dockge-Enhanced)
>
> **Auteur :** contributeur
>
> **Branches :** fix/mount → main
>
> Le titre de la notification Discord ouvre directement la Pull Request.

### GitHub Actions

> <img src="app/static/octicons/workflow.svg" width="18" alt="GitHub Actions"> **Build Docker — Échec**
>
> Workflow terminé : **Échec**
>
> **Dépôt :** [Aerya/Dockge-Enhanced](https://github.com/Aerya/Dockge-Enhanced)
>
> **Auteur :** Aerya
>
> **Branche :** main
>
> **Événement :** push
>
> Le titre de la notification Discord ouvre directement l'exécution du workflow.

### Fork

> <img src="app/static/octicons/repo-forked.svg" width="18" alt="Fork"> **Nouveau fork**
>
> Le dépôt a été forké vers **utilisateur/Dockge-Enhanced**.
>
> **Dépôt :** [Aerya/Dockge-Enhanced](https://github.com/Aerya/Dockge-Enhanced)
>
> **Auteur :** utilisateur
>
> Le titre de la notification Discord ouvre directement le dépôt forké.

### Star

> <img src="app/static/octicons/star.svg" width="18" alt="Star"> **Nouvelle étoile**
>
> **utilisateur** vient d'ajouter une étoile au dépôt.
>
> **Dépôt :** [Aerya/Dockge-Enhanced](https://github.com/Aerya/Dockge-Enhanced)
>
> **Auteur :** utilisateur
>
> Le titre ouvre la page des stargazers du dépôt.

## Sécurité

- mots de passe locaux hashés avec Argon2id ;
- token GitHub et webhooks Discord chiffrés dans SQLite ;
- protection CSRF ;
- cookies `HttpOnly` et `SameSite=Lax` ;
- CSP et anti-framing ;
- validation stricte des URLs Discord ;
- aucun secret écrit en clair dans les journaux ;
- aucune API d'administration exposée.

## Image Docker

Le workflow fourni teste le projet puis publie automatiquement l'image sur GHCR :

`ghcr.io/aerya/github-discord-notifier:latest`

## Licence

MIT
