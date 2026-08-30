import requests

API = "https://api.github.com"
API_VERSION = "2022-11-28"


class GitHubError(RuntimeError):
    def __init__(self, message, *, status=None, url=None, request_id=None, remaining=None, limit=None):
        super().__init__(message)
        self.status = status
        self.url = url
        self.request_id = request_id
        self.remaining = remaining
        self.limit = limit


def _headers(token, accept="application/vnd.github+json"):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "github-discord-notifier",
    }


def get_json(token, url, params=None, accept="application/vnd.github+json"):
    try:
        r = requests.get(
            url,
            headers=_headers(token, accept),
            params=params,
            timeout=15,
        )
    except requests.RequestException as exc:
        raise GitHubError(
            f"Erreur réseau GitHub: {exc}",
            url=url,
        ) from exc

    if r.status_code >= 400:
        message = ""
        try:
            payload = r.json()
            message = payload.get("message") or ""
        except Exception:
            message = (r.text or "").strip()[:300]

        request_id = r.headers.get("x-github-request-id")
        remaining = r.headers.get("x-ratelimit-remaining")
        limit = r.headers.get("x-ratelimit-limit")

        detail = f"GitHub HTTP {r.status_code}"
        if message:
            detail += f" — {message}"
        detail += f" — {r.url}"

        if remaining is not None and limit is not None:
            detail += f" — quota {remaining}/{limit}"
        if request_id:
            detail += f" — request {request_id}"

        raise GitHubError(
            detail,
            status=r.status_code,
            url=r.url,
            request_id=request_id,
            remaining=remaining,
            limit=limit,
        )

    return r.json(), r.headers


def authenticated_user(token):
    return get_json(token, f"{API}/user")


def list_repositories(token):
    repos = []
    page = 1

    while True:
        data, _ = get_json(
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


def recent_issues(token, full_name):
    data, _ = get_json(
        token,
        f"{API}/repos/{full_name}/issues",
        params={
            "state": "all",
            "sort": "created",
            "direction": "desc",
            "per_page": 20,
        },
    )
    return [x for x in data if "pull_request" not in x]


def recent_pulls(token, full_name):
    try:
        data, _ = get_json(
            token,
            f"{API}/repos/{full_name}/pulls",
            params={
                "state": "all",
                "sort": "created",
                "direction": "desc",
                "per_page": 20,
            },
        )
    except GitHubError as exc:
        if exc.status == 404:
            return []
        raise
    return data


def recent_forks(token, full_name):
    data, _ = get_json(
        token,
        f"{API}/repos/{full_name}/forks",
        params={"sort": "newest", "per_page": 20},
    )
    return data


def recent_stars(token, full_name):
    data, _ = get_json(
        token,
        f"{API}/repos/{full_name}/stargazers",
        params={"per_page": 20},
        accept="application/vnd.github.star+json",
    )
    return sorted(
        data,
        key=lambda x: x.get("starred_at") or "",
        reverse=True,
    )


def recent_workflow_runs(token, full_name):
    try:
        data, _ = get_json(
            token,
            f"{API}/repos/{full_name}/actions/runs",
            params={"per_page": 20},
        )
    except GitHubError as exc:
        if exc.status == 404:
            return []
        raise
    return data.get("workflow_runs", [])


def rate_limit(token):
    data, _ = get_json(token, f"{API}/rate_limit")
    return data.get("rate", {})
