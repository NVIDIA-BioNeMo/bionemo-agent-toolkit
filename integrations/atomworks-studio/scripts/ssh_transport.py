"""Data-plane SSH never delegates to a provider command that can start a VM."""
from pathlib import Path
import re

import registry


def access(cfg, run, *, trust_on_first_use=False):
    brev = cfg.get('kind') == 'brev'
    if trust_on_first_use and not brev:
        raise ValueError('Automatic first-use trust is supported only during Brev access refresh')
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
               '-o', 'StrictHostKeyChecking=' + ('accept-new' if trust_on_first_use else 'yes'), '-o', 'ForwardAgent=no',
               '-o', 'ControlMaster=no', '-o', 'ControlPath=none']
    if brev:
        # Brev-generated aliases discard host keys. Use the user's established
        # trust store instead. Only explicit access refresh can enroll a new key;
        # changed keys fail in both modes. Jobs/copies always use strict checking.
        options += ['-o', 'UserKnownHostsFile=' + str(Path.home() / '.ssh/known_hosts'),
                    '-o', 'GlobalKnownHostsFile=/etc/ssh/ssh_known_hosts']
    return alias, options


def execute(cfg, command, run, timeout, *, trust_on_first_use=False):
    alias, options = access(cfg, run, trust_on_first_use=trust_on_first_use)
    return run(['ssh', *options, '--', alias, command], timeout)


def copy(cfg, source, destination, download, run, timeout):
    alias, options = access(cfg, run)
    paths = ([f'{alias}:{source}', str(destination)] if download
             else [str(source), f'{alias}:{destination}'])
    return run(['scp', '-r', *options, '--', *paths], timeout)
