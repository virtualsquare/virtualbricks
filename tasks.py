# -*- coding: utf-8 -*-

import io
import os
import shlex
import shutil
import subprocess
import sys
import datetime
import tarfile
import textwrap

from invoke import task
from invoke.exceptions import Exit
from invoke.main import program
from invoke.util import cd
from pelican import main as pelican_main
from pelican.server import ComplexHTTPRequestHandler, RootedHTTPServer
from pelican.settings import DEFAULT_CONFIG, get_settings_from_file

OPEN_BROWSER_ON_SERVE = True
SETTINGS_FILE_BASE = 'pelicanconf.py'
SETTINGS = {}
SETTINGS.update(DEFAULT_CONFIG)
LOCAL_SETTINGS = get_settings_from_file(SETTINGS_FILE_BASE)
SETTINGS.update(LOCAL_SETTINGS)

CONFIG = {
    'settings_base': SETTINGS_FILE_BASE,
    'settings_publish': 'publishconf.py',
    # Output path. Can be absolute or relative to tasks.py. Default: 'output'
    'deploy_path': SETTINGS['OUTPUT_PATH'],
    # Github Pages configuration
    'github_pages_branch': 'gh-pages',
    'commit_message': "'Publish site on {}'".format(datetime.date.today().isoformat()),
    # Host and port for `serve`
    'host': 'localhost',
    'port': 8000,
}

@task
def clean(c):
    """Remove generated files"""
    if os.path.isdir(CONFIG['deploy_path']):
        shutil.rmtree(CONFIG['deploy_path'])
        os.makedirs(CONFIG['deploy_path'])

@task
def build(c):
    """Build local version of site"""
    pelican_run('-s {settings_base}'.format(**CONFIG))

@task
def rebuild(c):
    """`build` with the delete switch"""
    pelican_run('-d -s {settings_base}'.format(**CONFIG))

@task
def regenerate(c):
    """Automatically regenerate site upon file modification"""
    pelican_run('-r -s {settings_base}'.format(**CONFIG))

@task
def serve(c):
    """Serve site at http://$HOST:$PORT/ (default is localhost:8000)"""

    class AddressReuseTCPServer(RootedHTTPServer):
        allow_reuse_address = True

    server = AddressReuseTCPServer(
        CONFIG['deploy_path'],
        (CONFIG['host'], CONFIG['port']),
        ComplexHTTPRequestHandler)

    if OPEN_BROWSER_ON_SERVE:
        # Open site in default browser
        import webbrowser
        webbrowser.open("http://{host}:{port}".format(**CONFIG))

    sys.stderr.write('Serving at {host}:{port} ...\n'.format(**CONFIG))
    server.serve_forever()

@task
def reserve(c):
    """`build`, then `serve`"""
    build(c)
    serve(c)

@task
def preview(c):
    """Build production version of site"""
    pelican_run('-s {settings_publish}'.format(**CONFIG))

@task
def livereload(c):
    """Automatically reload browser tab upon file modification."""
    from livereload import Server

    def cached_build():
        cmd = '-s {settings_base} -e CACHE_CONTENT=True LOAD_CONTENT_CACHE=True'
        pelican_run(cmd.format(**CONFIG))

    cached_build()
    server = Server()
    theme_path = SETTINGS['THEME']
    watched_globs = [
        CONFIG['settings_base'],
        '{}/templates/**/*.html'.format(theme_path),
    ]

    content_file_extensions = ['.md', '.rst']
    for extension in content_file_extensions:
        content_glob = '{0}/**/*{1}'.format(SETTINGS['PATH'], extension)
        watched_globs.append(content_glob)

    static_file_extensions = ['.css', '.js']
    for extension in static_file_extensions:
        static_file_glob = '{0}/static/**/*{1}'.format(theme_path, extension)
        watched_globs.append(static_file_glob)

    for glob in watched_globs:
        server.watch(glob, cached_build)

    if OPEN_BROWSER_ON_SERVE:
        # Open site in default browser
        import webbrowser
        webbrowser.open("http://{host}:{port}".format(**CONFIG))

    server.serve(host=CONFIG['host'], port=CONFIG['port'], root=CONFIG['deploy_path'])


@task
def publish(c):
    """Publish to production via rsync"""
    pelican_run('-s {settings_publish}'.format(**CONFIG))
    c.run(
        'rsync --delete --exclude ".DS_Store" -pthrvz -c '
        '-e "ssh -p {ssh_port}" '
        '{} {ssh_user}@{ssh_host}:{ssh_path}'.format(
            CONFIG['deploy_path'].rstrip('/') + '/',
            **CONFIG))

@task
def gh_pages(c):
    """Publish to GitHub Pages"""
    preview(c)
    c.run('ghp-import -b {github_pages_branch} '
          '-m {commit_message} '
          '{deploy_path} -p'.format(**CONFIG))

# The help, the HTML of the user guide, and the pages of the Documentation
# are copies of those of a commit of develop, made by sync-docs: page 28 of
# develop's docs/redesign, section 7.
ROOT = os.path.dirname(os.path.abspath(__file__))
HELP_SOURCE = 'help/html/C'
HELP_PATH = os.path.join('content', 'help', 'C')
DOCUMENTATION_PATH = os.path.join('content', 'documentation')
# The address of the site, which the help and the pages of docs/ link in
# full, as the help installed with Virtualbricks needs; the copies here link
# within the site, so that a local build stays local.
SITE = 'https://www.virtualbricks.it/'


def git(*args):
    """What git writes, run in this checkout; Exit if it fails."""
    result = subprocess.run(('git',) + args, cwd=ROOT, capture_output=True)
    if result.returncode:
        raise Exit(result.stderr.decode().strip(), code=1)
    return result.stdout


def documentation_page(source, page):
    """
    A page of the Documentation, and its stylesheet, from the page of docs/
    in develop, source, and the page of the site: its head, the metadata of
    Pelican, kept; the body of source after its <style>, as it is; the
    <style> in the stylesheet.
    """
    head = page[:page.index('<body>\n') + len('<body>\n')]
    start = source.index('<style>\n') + len('<style>\n')
    end = source.index('</style>\n')
    body = source[end + len('</style>\n'):].lstrip('\n')
    return head + body + '</body>\n</html>\n', textwrap.dedent(source[start:end])


def within_site(data, path):
    """
    data, the file at path, a page of the site, with the links to the site
    relative to the folder of path.
    """
    if not path.endswith('.html'):
        return data
    up = os.path.relpath('content', os.path.dirname(path))
    return data.replace(('href="' + SITE).encode(),
                        ('href="' + up + '/').encode())


def read(path):
    """The bytes of path in this checkout, None if it isn't there."""
    try:
        with open(os.path.join(ROOT, path), 'rb') as file:
            return file.read()
    except FileNotFoundError:
        return None


def docs_of(ref):
    """
    The files of the help and of the Documentation as ref has them, by their
    path in the site: every file of help/html/C; for each page of the
    Documentation of the site, NAME.html, its docs/NAME.html. Their links to
    the site are relative.
    """
    files = {}
    try:
        tar = git('archive', '--format=tar', ref, HELP_SOURCE)
    except Exit:
        raise Exit('{} has no {}'.format(ref, HELP_SOURCE), code=1)
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        for member in archive.getmembers():
            if member.isfile():
                name = os.path.relpath(member.name, HELP_SOURCE)
                path = os.path.join(HELP_PATH, name)
                data = archive.extractfile(member).read()
                files[path] = within_site(data, path)
    for name in sorted(os.listdir(os.path.join(ROOT, DOCUMENTATION_PATH))):
        if not name.endswith('.html'):
            continue
        path = os.path.join(DOCUMENTATION_PATH, name)
        source = git('show', '{}:docs/{}'.format(ref, name)).decode('utf-8')
        page, css = documentation_page(source, read(path).decode('utf-8'))
        files[path] = within_site(page.encode('utf-8'), path)
        files[path[:-len('.html')] + '.css'] = css.encode('utf-8')
    return files


def help_files():
    """The paths of the files of the help in the site."""
    paths = []
    for folder, _, names in os.walk(os.path.join(ROOT, HELP_PATH)):
        for name in names:
            paths.append(os.path.relpath(os.path.join(folder, name), ROOT))
    return paths


@task(positional=['ref'], help={
    'ref': 'the commit of develop: develop, a tag or a hash',
    'check': 'change nothing: exit with 1 if the site differs from REF',
})
def sync_docs(c, ref, check=False):
    """Copy the help and the Documentation of a commit of develop"""
    try:
        commit = git('rev-parse', '--short', ref + '^{commit}').decode().strip()
    except Exit:
        raise Exit('{} is no commit of this repository: git fetch, or name '
                   'another'.format(ref), code=1)
    wanted = docs_of(ref)
    changed = [path for path in sorted(wanted) if read(path) != wanted[path]]
    gone = sorted(path for path in help_files() if path not in wanted)
    if check:
        for path in changed:
            state = 'missing' if read(path) is None else 'not as in'
            print('{}: {} {} {}'.format(path, state, ref, commit))
        for path in gone:
            print('{}: not in {} {}'.format(path, ref, commit))
        if changed or gone:
            raise Exit('The help and the Documentation differ from {} {}: '
                       'invoke sync-docs {}'.format(ref, commit, ref), code=1)
        print('The help and the Documentation are those of {} {}'.format(
            ref, commit))
        return
    for path in changed:
        print('{} {}'.format('added' if read(path) is None else 'updated', path))
        os.makedirs(os.path.dirname(os.path.join(ROOT, path)), exist_ok=True)
        with open(os.path.join(ROOT, path), 'wb') as file:
            file.write(wanted[path])
    for path in gone:
        print('removed {}'.format(path))
        os.remove(os.path.join(ROOT, path))
    for folder, folders, names in os.walk(os.path.join(ROOT, HELP_PATH),
                                          topdown=False):
        if not folders and not names:
            os.rmdir(folder)
    print('{} is {} in this repository: git fetch first for the published '
          'one.'.format(ref, commit))
    print('Commit as: Help and Documentation of {} {}'.format(ref, commit))


def pelican_run(cmd):
    cmd += ' ' + program.core.remainder  # allows to pass-through args to pelican
    pelican_main(shlex.split(cmd))