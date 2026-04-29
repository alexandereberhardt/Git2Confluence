import json
import os
import ssl
import urllib.request
import urllib.parse
import urllib.error
import base64


def _ssl_context() -> ssl.SSLContext:
    # Homebrew CA bundle includes both standard CAs and corporate proxy CAs.
    # The env vars (SSL_CERT_FILE) may point to only the corporate CA, which
    # is insufficient on its own — so prefer the full bundle.
    ca_candidates = [
        '/opt/homebrew/etc/ca-certificates/cert.pem',
        '/etc/ssl/cert.pem',
    ]
    for ca in ca_candidates:
        if os.path.isfile(ca):
            return ssl.create_default_context(cafile=ca)
    return ssl.create_default_context()


class GitLabExtractor:
    ARTEFACT_MAP = {
        'README.md': 'readme',
        '.gitlab-ci.yml': 'gitlab_ci',
        'Dockerfile': 'dockerfile',
        'docker-compose.yml': 'docker_compose',
        'package.json': 'package_json',
        'pom.xml': 'pom_xml',
        'requirements.txt': 'requirements_txt',
        'build.gradle': 'build_gradle',
        'CHANGELOG.md': 'changelog',
        'jest.config.js': 'jest_config',
        'jest.config.ts': 'jest_config',
        'cypress.config.ts': 'cypress_config',
        'cypress.config.js': 'cypress_config',
        'pytest.ini': 'pytest_config',
        'pyproject.toml': 'pyproject',
    }

    ARTEFACT_DIRS = ['terraform', 'helm', 'charts', 'monitoring', 'alerting', '.github', 'openapi', 'swagger']

    def __init__(self, host: str, token: str):
        self.base_url = f"https://{host}/api/v4"
        self.token = token
        self._ssl_ctx = _ssl_context()

    def _api_get(self, path: str, params: dict | None = None) -> list | dict:
        url = f"{self.base_url}{path}"
        if params:
            query = '&'.join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"
        req = urllib.request.Request(url, headers={'PRIVATE-TOKEN': self.token})
        with urllib.request.urlopen(req, timeout=30, context=self._ssl_ctx) as resp:
            return json.loads(resp.read())

    def discover_repos(self, group_id: int, product_config: dict) -> list[dict]:
        projects = self._api_get(f"/groups/{group_id}/projects",
                                 {'per_page': '100', 'include_subgroups': 'true',
                                  'order_by': 'last_activity_at', 'sort': 'desc'})
        exclude = product_config.get('exclude_patterns', [])
        min_activity = product_config.get('min_activity', '2000-01-01')
        result = []
        for p in projects:
            ns = p.get('path_with_namespace', '')
            activity = (p.get('last_activity_at') or '')[:10]
            if any(ex in ns for ex in exclude):
                continue
            if activity < min_activity:
                continue
            result.append(p)
        return result

    def discover_repos_by_subgroup(self, subgroup_id: int) -> list[dict]:
        return self._api_get(f"/groups/{subgroup_id}/projects",
                             {'per_page': '100', 'include_subgroups': 'true'})

    def get_file(self, project_id: int, file_path: str, branch: str) -> str | None:
        encoded_path = urllib.parse.quote(file_path, safe='')
        try:
            data = self._api_get(f"/projects/{project_id}/repository/files/{encoded_path}",
                                 {'ref': branch})
            return base64.b64decode(data['content']).decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def get_tree(self, project_id: int, branch: str, path: str = '', recursive: bool = False) -> list[dict]:
        params = {'ref': branch, 'per_page': '100'}
        if path:
            params['path'] = path
        if recursive:
            params['recursive'] = 'true'
        try:
            return self._api_get(f"/projects/{project_id}/repository/tree", params)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise

    def scan_repo(self, project: dict) -> dict:
        project_id = project['id']
        branch = project.get('default_branch', 'main')
        ns = project.get('path_with_namespace', '')

        tree = self.get_tree(project_id, branch, recursive=True)
        tree_paths = [item['path'] for item in tree]

        result = {'project': ns, 'project_id': project_id, 'branch': branch}

        for file_path, key in self.ARTEFACT_MAP.items():
            if file_path in tree_paths:
                content = self.get_file(project_id, file_path, branch)
                if content:
                    result[key] = content

        for dir_name in self.ARTEFACT_DIRS:
            dir_files = [p for p in tree_paths if p.startswith(f"{dir_name}/")]
            if dir_files:
                result[f'{dir_name}_files'] = dir_files
                for f in dir_files[:10]:
                    if f.endswith(('.yaml', '.yml', '.json', '.tf', '.toml')):
                        content = self.get_file(project_id, f, branch)
                        if content:
                            result.setdefault(f'{dir_name}_contents', {})[f] = content

        # OpenAPI specs (common locations)
        for candidate in ['openapi.yaml', 'openapi.json', 'swagger.yaml', 'swagger.json',
                         'api/openapi.yaml', 'docs/openapi.yaml']:
            if candidate in tree_paths:
                content = self.get_file(project_id, candidate, branch)
                if content:
                    result['openapi'] = content
                    break

        return result
