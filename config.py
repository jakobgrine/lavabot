import json
import os
import sys

config_path = os.path.join(os.path.dirname(__file__), 'config.json')
default_config = {
    'active_extensions': ['cogs.admin', 'cogs.music'],
    'command_prefix': '$',
    'discord_token': '',
    'lavalink_nodes': [{
        'host': '127.0.0.1',
        'identifier': 'MAIN',
        'password': 'youshallnotpass',
        'port': 2333,
        'region': 'eu_central',
        'rest_uri': 'http://127.0.0.1:2333'
    }],
    'dj_roles': {}
}


def load_config() -> dict:
    try:
        with open(config_path, 'r') as file:
            config = default_config
            config.update(json.load(file))
            return config
    except IOError:
        with open(config_path, 'w+') as file:
            json.dump(default_config, file, indent=2, sort_keys=True)
        sys.exit()
