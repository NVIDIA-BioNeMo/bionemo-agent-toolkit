"""Validate apt's proposed effects against a reviewed compiler package manifest.

This is a preparation guard, not an installer or permission to mutate a host.
The eventual installation must revalidate under its package-manager lock.
"""
import re


def validate_plan(output, packages):
    """Return exact proposed package effects; fail closed on unexpected changes."""
    effects = {}
    for line in output.splitlines():
        if line.startswith(('Remv ', 'Purg ')):
            raise ValueError('Compiler setup must not remove packages: '+line)
        if not line.startswith(('Inst ', 'Conf ')):
            continue
        match = re.fullmatch(r'(Inst|Conf) ([A-Za-z0-9+.:_-]+)(?: \[[^\]]+\])? \(([^\s)]+)(?: .*)?\)(?: \[.*\])?', line)
        if not match:
            raise ValueError('Unrecognized package-manager change: '+line)
        action, name, version = match.groups()
        # Architecture-qualified names remain distinct; never silently normalize.
        if packages.get(name) != version:
            raise ValueError('Unreviewed compiler package or version: '+name+'='+version)
        previous = effects.setdefault(name, {'version':version, 'actions':[]})
        if action in previous['actions']:
            raise ValueError('Duplicate package-manager change: '+name)
        previous['actions'].append(action)
    return effects
