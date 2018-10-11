import os
import jinja2
import aiohttp_jinja2
import aiohttp_github_helpers as h
from aiohttp import web, ClientSession, BasicAuth, ClientTimeout

DRONE_SERVER = os.environ['DRONE_SERVER']
DRONE_TOKEN = os.environ['DRONE_TOKEN']
TOPICS = ["integration-level-5", "integration-level-4", "integration-level-3",
          "integration-level-2", "integration-level-1"]
ORG = "metwork-framework"
BRANCHES = ["integration", "master"]
GITHUB_USER = os.environ['GITHUB_USER']
GITHUB_PASS = os.environ['GITHUB_PASS']
TIMEOUT = ClientTimeout(total=20)
AUTH = BasicAuth(GITHUB_USER, GITHUB_PASS)
TEMPLATES_DIR = os.path.join(os.environ['MFSERV_CURRENT_PLUGIN_DIR'], 'main',
                             'templates')


async def drone_get_latest_status(client_session, owner, repo, branch):
    url = "%s/api/repos/%s/%s/builds" % (DRONE_SERVER, owner, repo)
    params = {"token": DRONE_TOKEN}
    async with client_session.get(url, params=params) as r:
        if r.status != 200:
            return None
        try:
            builds = await r.json()
            for build in builds:
                if build['event'] != 'push':
                    continue
                if build['branch'] != branch:
                    continue
                return {"status": build['status'], "number": build['number'],
                        "url": "%s/%s/%s/%i" % (DRONE_SERVER, owner,
                                                repo, build['number'])}
        except Exception:
            pass
    return None


async def handle(request):
    async with ClientSession(auth=AUTH, timeout=TIMEOUT) as session:
        ghrepos = []
        for topic in TOPICS:
            tmp = await h.github_get_org_repos_by_topic(session, ORG, [topic],
                                                        ["testrepo"])
            ghrepos = ghrepos + tmp
        repos = []
        for repo in ghrepos:
            tmp = {"name": repo, "url": "https://github.com/%s/%s" %
                   (ORG, repo), "branches": []}
            for branch in BRANCHES:
                commit_future = h.github_get_latest_commit(session, ORG, repo,
                                                           branch)
                status_future = drone_get_latest_status(session, ORG, repo,
                                                        branch)
                tmp['branches'].append({
                    "name": branch,
                    "commit_future": commit_future,
                    "status_future": status_future,
                    "github_link": "https://github.com/%s/%s/tree/%s" %
                    (ORG, repo, branch)
                })
            repos.append(tmp)
        for repo in repos:
            for branch in repo['branches']:
                commit = await branch['commit_future']
                if branch['name'] == 'master' and commit:
                    repo['master_sha'] = commit[0][0:7]
                else:
                    repo['master_sha'] = None
                sha = None
                age = None
                if commit:
                    sha = commit[0][0:7]
                    age = commit[1]
                branch['sha'] = sha
                branch['age'] = age
                del(branch['commit_future'])
                status = await branch['status_future']
                branch['drone_status'] = status
                del(branch['status_future'])
    context = {"REPOS": repos, "BRANCHES": BRANCHES}
    response = aiohttp_jinja2.render_template('home.html', request, context)
    return response

app = web.Application(debug=False)
aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATES_DIR))
app.router.add_get('/{tail:.*}', handle)
