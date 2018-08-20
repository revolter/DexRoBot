import configparser
import os
import sys

from fabric import task
from invoke import env

try:
    config = configparser.ConfigParser()

    config.read('fabfile.cfg')

    env.hosts = [config.get('Fabric', 'Host')]
    env.user = config.get('Fabric', 'User')
    env.key_filename = config.get('Fabric', 'KeyFilename')

    env.project_path = config.get('Fabric', 'ProjectPath')
except configparser.Error as error:
    print('Config error: {}'.format(error))

    sys.exit(1)

env.project_name = 'DexRoBot'
env.source_filenames = [
    'main.py',
    'database.py',
    'utils.py',
    'analytics.py',
    'constants.py',

    'config.cfg'
]
env.meta_filenames = [
    'Pipfile',
    'Pipfile.lock'
]


@task
def config(context):
    context.user = env.user
    context.connect_kwargs.key_filename = os.path.expanduser(env.key_filename)


@task(pre=[config], hosts=env.hosts, help={'command': 'The shell command to execute on the server'})
def execute(context, command=None):
    if not command:
        return

    context.run(command)


@task(pre=[config], hosts=env.hosts)
def cleanup(context):
    context.run('rm -rf {.project_name}'.format(env))
    context.run('rm -rf {0.project_path}/{0.project_name}'.format(env))


@task(pre=[config, cleanup], hosts=env.hosts)
def setup(context):
    context.run('mkdir -p {0.project_path}/{0.project_name}'.format(env))
    context.run('ln -s {0.project_path}/{0.project_name} {0.project_name}'.format(env))

    context.run('python -m pip install --user pipenv')


@task(default=True, pre=[config], hosts=env.hosts, help={'filename': 'An optional filename to deploy to the server'})
def deploy(context, filename=None):
    if not filename:
        for source_filename in env.source_filenames:
            context.put('src/{}'.format(source_filename), '{.project_name}/'.format(env))

        for meta_filename in env.meta_filenames:
            context.put(meta_filename, '{.project_name}/'.format(env))

        with context.cd(env.project_name):
            context.run('python -m pipenv install --three')
    else:
        context.put('src/{}'.format(filename), '{.project_name}/'.format(env))
