#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${REPO_NAME:-github-discord-notifier}"
REPO_OWNER="${REPO_OWNER:-Aerya}"
DESCRIPTION="${DESCRIPTION:-Notifications GitHub vers Discord, avec WebUI.}"
VISIBILITY="${VISIBILITY:-public}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Erreur : '$1' est requis." >&2
    exit 1
  }
}

need git
need gh

if ! gh auth status >/dev/null 2>&1; then
  echo "Erreur : GitHub CLI n'est pas authentifié. Lancez d'abord : gh auth login" >&2
  exit 1
fi

if [[ ! -f "compose.yml" || ! -d "app" ]]; then
  echo "Erreur : lancez ce script depuis la racine du projet." >&2
  exit 1
fi

FULL_REPO="${REPO_OWNER}/${REPO_NAME}"

if gh repo view "$FULL_REPO" >/dev/null 2>&1; then
  echo "Le dépôt $FULL_REPO existe déjà."
else
  echo "Création du dépôt public $FULL_REPO…"
  gh repo create "$FULL_REPO" \
    --"$VISIBILITY" \
    --description "$DESCRIPTION" \
    --disable-wiki
fi

if [[ ! -d ".git" ]]; then
  git init
fi

git branch -M "$DEFAULT_BRANCH"

if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "https://github.com/${FULL_REPO}.git"
else
  git remote set-url origin "https://github.com/${FULL_REPO}.git"
fi

git add -A

if git diff --cached --quiet; then
  echo "Aucun changement à commit."
else
  git commit -m "Initial public release"
fi

echo "Push vers GitHub…"
git push -u origin "$DEFAULT_BRANCH"

echo
echo "Le push sur '$DEFAULT_BRANCH' déclenche automatiquement le workflow Docker."
echo "Suivi du dernier run :"
gh run list --repo "$FULL_REPO" --workflow docker.yml --limit 1

echo
echo "Dépôt : https://github.com/${FULL_REPO}"
echo "Package : https://github.com/${REPO_OWNER}?tab=packages"
