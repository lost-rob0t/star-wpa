"""Standalone sa-<actor/tool-name> commands sharing the effect adapter boundary."""
import json
from pathlib import Path

CORE_ACTORS = ('kismet', 'gpsd', 'listener', 'aircrack', 'deauth', 'trilateration', 'wardrive')
_TOOL_NAMES = [row['package'] for row in json.loads(
    (Path(__file__).parent / 'tool_catalog.json').read_text())['packages']]
COMMAND_ACTORS = {'sa-' + name: name for name in CORE_ACTORS}
# Keep the tool namespace explicit, including the two core/package collisions.
COMMAND_ACTORS.update({'sa-tool-' + name: 'tool-' + name for name in _TOOL_NAMES})
COMMAND_ACTORS.update({'sa-' + name: 'tool-' + name for name in _TOOL_NAMES if name not in CORE_ACTORS})


def _entry_point(command, actor):
    # Bind the route at installation/import time, never from argv[0]. Nix and
    # other launchers may rename or wrap the generated console scripts.
    def invoke(argv=None):
        from .__main__ import main as adapter_main
        return adapter_main(argv, actor=actor, prog=command)
    invoke.__name__ = 'run_' + command.replace('-', '_')
    invoke.__doc__ = f"Run {actor} through {command}."
    return invoke


for _command, _actor in COMMAND_ACTORS.items():
    _function = _entry_point(_command, _actor)
    globals()[_function.__name__] = _function
