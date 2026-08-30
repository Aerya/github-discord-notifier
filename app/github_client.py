import requests

API = "https://api.github.com"
API_VERSION = "2022-11-28"


class GitHubError(RuntimeError):
    def __init__(self, message, *, status=None, url=None):
        super().__init__(message)
        self.status = status
        self.url = url


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "github-discord-notifier",
    }


def request_json(method, token, url, *, params=None, payload=None):
    try:
        r = requests.request(
            method,
            url,
            headers=_headers(token),
            params=params,
            json=payload,
            timeout=15,
        )
    except requests.RequestException as exc:
        raise GitHubError(f"Erreur réseau GitHub: {exc}", url=url) from exc

    if r.status_code >= 400:
        try:
            message = (r.json() or {}).get("message") or ""
        except Exception:
            message = (r.text or "").strip()[:300]
        detail = f"GitHub HTTP {r.status_code}"
        if message:
            detail += f" — {message}"
        detail += f" — {r.url}"
        remaining = r.headers.get("x-ratelimit-remaining")
        limit = r.headers.get("x-ratelimit-limit")
        if remaining is not None and limit is not None:
            detail += f" — quota {remaining}/{limit}"
        raise GitHubError(detail, status=r.status_code, url=r.url)

    if r.status_code == 204 or not r.content:
        return None, r.headers
    return r.json(), r.headers


def authenticated_user(token):
    return request_json("GET", token, f"{API}/user")


def list_repositories(token):
    repos = []
    page = 1
    while True:
        data, _ = request_json(
            "GET",
            token,
            f"{API}/user/repos",
            params={
                "visibility": "all",
                "affiliation": "owner,collaborator,organization_member",
                "sort": "full_name",
                "per_page": 100,
                "page": page,
            },
        )
        repos.extend(data)
        if len(data) < 100:
            return repos
        page += 1


def rate_limit(token):
    data, _ = request_json("GET", token, f"{API}/rate_limit")
    return data.get("rate", {})


def list_repository_hooks(token, full_name):
    data, _ = request_json(
        "GET",
        token,
        f"{API}/repos/{full_name}/hooks",
        params={"per_page": 100},
    )
    return data


def _hook_payload(endpoint, secret, events):
    return {
        "name": "web",
        "active": True,
        "events": sorted(set(events)),
        "config": {
            "url": endpoint,
            "content_type": "json",
            "insecure_ssl": "0",
            "secret": secret,
        },
    }


def sync_repository_hook(token, full_name, endpoint, secret, events, known_hook_id=None):
    payload = _hook_payload(endpoint, secret, events)

    if known_hook_id:
        try:
            data, _ = request_json(
                "PATCH",
                token,
                f"{API}/repos/{full_name}/hooks/{known_hook_id}",
                payload=payload,
            )
            return data
        except GitHubError as exc:
            if exc.status != 404:
                raise

    for hook in list_repository_hooks(token, full_name):
        if (hook.get("config") or {}).get("url") == endpoint:
            data, _ = request_json(
                "PATCH",
                token,
                f"{API}/repos/{full_name}/hooks/{hook['id']}",
                payload=payload,
            )
            return data

    data, _ = request_json(
        "POST",
        token,
        f"{API}/repos/{full_name}/hooks",
        payload=payload,
    )
    return data


def delete_repository_hook(token, full_name, hook_id):
    try:
        request_json(
            "DELETE",
            token,
            f"{API}/repos/{full_name}/hooks/{hook_id}",
        )
    except GitHubError as exc:
        if exc.status != 404:
            raise
