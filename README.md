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

L'application n'effectue aucune écriture sur GitHub. Pour les dépôts privés et GitHub Actions, le token doit disposer des droits de lecture correspondants.

## Alertes Discord

Les alertes sont envoyées sous forme d'embeds avec un lien direct vers GitHub.

### Issue

> 🐛 **Nouvelle issue #271**  
> Start Guard fails with SSHFS mounts  
> **Dépôt :** Aerya/Dockge-Enhanced  
> **Auteur :** utilisateur  
> **Labels :** bug, mounts

### Pull Request

> 🔀 **Nouvelle Pull Request #272**  
> Fix mount validation  
> **Dépôt :** Aerya/Dockge-Enhanced  
> **Auteur :** contributeur  
> **Branches :** fix/mount → main

### GitHub Actions

> ❌ **Action failure — Build Docker**  
> Workflow terminé : **failure**  
> **Dépôt :** Aerya/Dockge-Enhanced  
> **Auteur :** Aerya  
> **Branche :** main  
> **Événement :** push

Un succès utilise ✅ et une exécution annulée ⏹️.

### Fork

> 🍴 **Nouveau fork**  
> Le dépôt a été forké vers **utilisateur/Dockge-Enhanced**.  
> **Dépôt :** Aerya/Dockge-Enhanced  
> **Auteur :** utilisateur

### Star

> ⭐ **Nouvelle étoile**  
> **utilisateur** vient d'ajouter une étoile au dépôt.  
> **Dépôt :** Aerya/Dockge-Enhanced  
> **Auteur :** utilisateur

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
