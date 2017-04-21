from fabric.api import cd, env, put, run

import configparser

try:
    config = configparser.ConfigParser()

    config.read('fabfile.cfg')

    env.hosts = [config.get('Fabric', 'Host')]
    env.user = config.get('Fabric', 'User')
    env.key_filename = config.get('Fabric', 'KeyFilename')

    env.project_path = config.get('Fabric', 'ProjectPath')
except configparser.Error as error:
    print('Config error: {}'.format(error))

    exit(1)

env.project_name = 'DexRoBot'
env.source_filenames = [
    'main.py',
    'analytics.py',
    'constants.py',

    'config.cfg',

    'requirements.txt'
]

env.colorize_errors=True
env.warn_only=True

def setup():
    run('mkdir -p {0.project_path}/{0.project_name}'.format(env))
    run('ln -s {0.project_path}/{0.project_name} ~/{0.project_name}'.format(env))

    with cd('~/{.project_name}'.format(env)):
        run('virtualenv -p python3 env')

def cleanup():
    run('rm -r ~/{.project_name}'.format(env))
    run('rm -r {0.project_path}/{0.project_name}'.format(env))

def deploy(filename=None):
    with cd('~/{.project_name}'.format(env)):
        if not filename:
            for source_filename in env.source_filenames:
                put('src/{}'.format(source_filename), '~/{.project_name}/'.format(env))

            run('source env/bin/activate; pip install -r requirements.txt')
        else:
            put('src/{}'.format(filename), '~/{.project_name}/'.format(env))
