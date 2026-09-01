#!/usr/bin/env python3

from pathlib import PurePath
import errno
import json
import os
import shlex
import subprocess
import sys

def destdir_join(d1: str, d2: str) -> str:
    if not d1:
        return d2
    # c:\destdir + c:\prefix must produce c:\destdir\prefix
    return str(PurePath(d1, *PurePath(d2).parts[1:]))

introspect = os.environ.get('MESONINTROSPECT')
out = subprocess.run([*shlex.split(introspect), '--installed'],
                     stdout=subprocess.PIPE, check=True).stdout
for source, dest in json.loads(out).items():
    bundle_dest = destdir_join('qemu-bundle', dest)
    path = os.path.dirname(bundle_dest)
    try:
        os.makedirs(path, exist_ok=True)
    except BaseException as e:
        print(f'error making directory {path}', file=sys.stderr)
        raise e
    try:
        os.symlink(source, bundle_dest)
    except BaseException as e:
        if not isinstance(e, OSError) or e.errno != errno.EEXIST:
            if os.name == 'nt':
                # Windows without Developer Mode/admin cannot create
                # symlinks. Copy data files that already exist; skip
                # entries whose source has not been built yet.
                if not os.path.lexists(bundle_dest):
                    if os.path.isfile(source):
                        try:
                            import shutil
                            shutil.copyfile(source, bundle_dest)
                        except BaseException as copy_err:
                            print(f'warning: could not copy {dest}: {copy_err}',
                                  file=sys.stderr)
                continue
            print(f'error making symbolic link {dest}', file=sys.stderr)
            raise e
