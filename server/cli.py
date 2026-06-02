# -*- coding: utf-8 -*-
"""Local admin CLI -- run INSIDE the container, calls server.app.admin/db directly.

Anti-cheat is block-by-id + hide-name ONLY (no general person-ban):
  --install <id>   block/unblock/erase ONE installation by its random install id
  --name <name>    hide/unhide/erase a chosen display name (moderation)
Neither is a durable person-ban: a source editor can mint a new install id.

Examples (inside the container, ADMIN_TOKEN in env):
    python -m server.cli ban    --install abc123 --reason cheating
    python -m server.cli ban    --name Bob          # hide the name 'Bob'
    python -m server.cli unban  --install abc123
    python -m server.cli delete --name Bob
    python -m server.cli list-bans

Reads ADMIN_TOKEN from the environment and verifies it (so the CLI follows the
same auth gate as the HTTP admin path). Stdlib argparse only.
"""

import argparse
import os
import sys


def _identity_args(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--install')
    group.add_argument('--name')


def _kind_value(args):
    if getattr(args, 'install', None):
        return 'install', args.install
    return 'name', args.name


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='server.cli',
                                     description='Telemetry admin CLI')
    sub = parser.add_subparsers(dest='command', required=True)

    p_ban = sub.add_parser('ban',
                           help='block an install id or hide a chosen name')
    _identity_args(p_ban)
    p_ban.add_argument('--reason', default=None)

    p_unban = sub.add_parser('unban',
                             help='unblock an install id or unhide a name')
    _identity_args(p_unban)

    p_delete = sub.add_parser('delete',
                              help='delete all submissions (GDPR erasure)')
    _identity_args(p_delete)

    sub.add_parser('list-bans', help='list current bans')

    args = parser.parse_args(argv)

    # Same auth gate as the HTTP path: require a configured ADMIN_TOKEN.
    from server.app import admin, db
    if not os.environ.get('ADMIN_TOKEN'):
        print('ADMIN_TOKEN not set in env -- refusing (fail closed).',
              file=sys.stderr)
        return 2
    db.init_db()

    if args.command == 'list-bans':
        for b in db.list_bans():
            print('{kind}\t{value}\t{reason}\t{ts}'.format(**b))
        return 0

    kind, value = _kind_value(args)
    if args.command == 'ban':
        print(admin.ban(kind, value, args.reason))
    elif args.command == 'unban':
        print(admin.unban(kind, value))
    elif args.command == 'delete':
        print(admin.delete(kind, value))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
