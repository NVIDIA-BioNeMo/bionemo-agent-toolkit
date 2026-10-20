"""Data-plane SSH never delegates to a provider command that can start a VM."""
from pathlib import Path
import re

import registry


def access(cfg, run):
    brev = cfg.get('kind') == 'brev'
    alias = cfg['instance'] if brev else cfg['ssh_host']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,200}', alias):
        raise ValueError('Invalid saved SSH alias')
    expected = cfg.get('ssh_access')
    if brev and not expected:
        raise ValueError('Refresh and verify this Brev machine’s SSH access in chat before connecting; no machine was started')
    if expected and expected.get('alias') != alias:
        raise ValueError('Saved SSH access belongs to a different alias; reconnect and verify this target')
    if expected:
        registry.verify_access(expected, run)
    options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'ForwardAgent=no',
               '-o', 'ControlMaster=no', '-o', 'ControlPath=none']
    if brev:
        # Brev-generated aliases discard host keys. Use the user's established
        # trust store instead; an unknown/changed key must fail, never auto-enroll.
        options += ['-o', 'UserKnownHostsFile=' + str(Path.home() / '.ssh/known_hosts'),
                    '-o', 'GlobalKnownHostsFile=/etc/ssh/ssh_known_hosts']
    return alias, options


def execute(cfg, command, run, timeout):
    alias, options = access(cfg, run)
    return run(['ssh', *options, '--', alias, command], timeout)


def copy(cfg, source, destination, download, run, timeout):
    alias, options = access(cfg, run)
    paths = ([f'{alias}:{source}', str(destination)] if download
             else [str(source), f'{alias}:{destination}'])
    return run(['scp', '-r', *options, '--', *paths], timeout)
