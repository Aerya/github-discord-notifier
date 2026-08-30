# GitHub Discord Notifier

Service Docker self-hosted qui reçoit les événements GitHub en temps réel et les envoie vers Discord.

## Fonctionnement

GitHub Discord Notifier fonctionne désormais en **webhooks entrants** :

```text
GitHub
  │
  │ webhook HTTPS
  ▼
Reverse proxy existant
  │
  ▼
GitHub Discord Notifier :8080
  │
  └── /webhook/github
          │
          ▼
       Discord
```

Il n'y a **aucun polling périodique** des dépôts.
GitHub pousse directement chaque événement vers l'application dès qu'il se produit.

Le reverse proxy **n'est pas intégré** au projet. L'application est simplement compatible avec Nginx Proxy Manager, Traefik, Caddy, Cloudflare Tunnel ou tout autre reverse proxy HTTPS.

## Fonctionnalités

- WebUI entièrement en français.
- Authentification locale.
- Fine-grained PAT GitHub chiffré dans SQLite.
- Synchronisation de la liste des dépôts accessibles.
- Sélection globale des dépôts.
- **Tout sélectionner / Tout désélectionner**.
- Installation automatique des webhooks GitHub sur les dépôts sélectionnés.
- Mise à jour automatique des hooks lorsque les alertes changent.
- Suppression du hook lorsqu'un dépôt n'est plus surveillé.
- Aucun polling GitHub.
- Notifications Discord quasi instantanées.
- Plusieurs webhooks Discord.
- Alertes :
  - nouvelles Issues ;
  - nouvelles Pull Requests ;
  - GitHub Actions terminées ;
  - forks ;
  - stars.
- Filtres Actions : échec, succès, annulation.
- Option pour ignorer ses propres PR.
- Octicons GitHub officiels dans la WebUI et les notifications Discord.
- Titres Discord cliquables vers l'Issue, la PR, le workflow ou le dépôt concerné.
- Nom du dépôt cliquable vers GitHub.
- Journaux des envois, erreurs et événements ignorés.

## Prérequis

- Docker / Docker Compose.
- Un sous-domaine HTTPS pointant vers votre reverse proxy.
- Le reverse proxy doit transférer le trafic vers le port `8080` du conteneur.
- Un webhook Discord.
- Un Fine-grained Personal Access Token GitHub.

## Reverse proxy

Le projet ne fournit et n'installe **aucun reverse proxy**.

Configurez simplement votre proxy existant pour envoyer :

```text
https://github-notifier.exemple.fr
        ↓
http://IP_DOCKER:8080
```

GitHub appellera ensuite :

```text
https://github-notifier.exemple.fr/webhook/github
```

Avec un proxy HTTPS, utilisez :

```yaml
APP_COOKIE_SECURE: "true"
APP_TRUST_PROXY: "true"
```

`APP_TRUST_PROXY=true` indique à Flask qu'il peut faire confiance aux en-têtes `X-Forwarded-*` ajoutés par votre reverse proxy.

## Fine-grained PAT GitHub

Créez un **[Fine-grained Personal Access Token](https://github.com/settings/personal-access-tokens/new)**.

1. Sélectionnez les dépôts que vous souhaitez surveiller.
2. Dans **Repository permissions**, accordez :
   - **Webhooks: Read and write**.
3. Générez le token.
4. Collez-le dans **GitHub** dans la WebUI.

Le PAT sert uniquement à :

- récupérer la liste des dépôts ;
- créer, modifier et supprimer les webhooks GitHub.

Il n'est pas utilisé pour scanner périodiquement les dépôts.

## Configuration GitHub

Dans la page **GitHub** de la WebUI :

1. connectez le Fine-grained PAT ;
2. saisissez l'URL publique de votre sous-domaine, par exemple :

```text
https://github-notifier.exemple.fr
```

L'application construit automatiquement l'endpoint :

```text
https://github-notifier.exemple.fr/webhook/github
```

Elle génère également automatiquement un secret webhook et le stocke chiffré dans SQLite.

Ensuite, lorsque vous sélectionnez des dépôts ou modifiez les types d'alertes, les webhooks GitHub sont resynchronisés automatiquement.

## Sécurité des webhooks GitHub

Chaque livraison GitHub est vérifiée grâce à la signature :

```text
X-Hub-Signature-256
```

L'application calcule la signature HMAC SHA-256 avec le secret enregistré et rejette toute livraison invalide.

L'endpoint `/webhook/github` est public par nécessité, mais il n'accepte pas les requêtes non signées correctement.

La WebUI reste protégée par l'authentification locale.

## Événements GitHub utilisés

Selon la configuration de chaque dépôt, l'application demande uniquement les événements nécessaires :

- `issues`
- `pull_request`
- `workflow_run`
- `fork`
- `star`

Pour `issues` et `pull_request`, seules les créations sont notifiées.

Pour `workflow_run`, seules les exécutions terminées correspondant aux statuts sélectionnés sont notifiées.

Pour `star`, seule l'action `created` est notifiée.

## Notifications Discord

Les notifications utilisent les Octicons GitHub officiels.

### Issue

**Nouvelle issue #271**

Titre de l'issue

**Dépôt :** lien direct vers le dépôt
**Auteur :** utilisateur
**Labels :** bug, mounts

Le titre ouvre directement l'issue GitHub.

### Pull Request

**Pull Request #272**

Titre de la PR

**Dépôt :** lien direct vers le dépôt
**Auteur :** contributeur
**Branches :** fix/mount → main

Le titre ouvre directement la Pull Request.

### GitHub Actions

**Build Docker — Échec**

**Dépôt :** lien direct vers le dépôt
**Branche :** main
**Événement :** push

Le titre ouvre directement l'exécution GitHub Actions.

### Fork

**Nouveau fork**

Le titre ouvre directement le dépôt forké.

### Star

**Nouvelle étoile**

Le titre ouvre la page des stargazers du dépôt.

## Docker Compose

```yaml
services:
  github-discord-notifier:
    image: ghcr.io/aerya/github-discord-notifier:latest
    container_name: github-discord-notifier
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      APP_SECRET_KEY: "CHANGE_ME_WITH_A_LONG_RANDOM_VALUE"
      APP_ENCRYPTION_KEY: "CHANGE_ME_WITH_A_FERNET_KEY"
      APP_COOKIE_SECURE: "true"
      APP_TRUST_PROXY: "true"
    volumes:
      - ./data:/data
```

## Journaux

Les journaux indiquent notamment :

- hook GitHub installé ou en erreur ;
- livraison webhook reçue ;
- signature invalide ;
- événement ignoré par configuration ;
- notification Discord envoyée ;
- erreur Discord détaillée.

## Sécurité

- mots de passe locaux hashés avec Argon2id ;
- PAT GitHub chiffré dans SQLite ;
- secret webhook GitHub chiffré ;
- webhooks Discord chiffrés ;
- vérification HMAC SHA-256 des livraisons GitHub ;
- protection CSRF de la WebUI ;
- cookies `HttpOnly` et `SameSite=Lax` ;
- `Secure` recommandé derrière HTTPS ;
- CSP et anti-framing ;
- aucun secret écrit dans les journaux.

## Image Docker

```text
ghcr.io/aerya/github-discord-notifier:latest
```

## Licence

MIT
