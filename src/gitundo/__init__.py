"""
gitundo - the undo button git never had.

A non-invasive safety net for git repositories. Every snapshot is stored as an
ordinary git commit on the hidden ref ``refs/gitundo/checkpoints``, so it uses
git's own content-addressed object store: zero dependencies, no extra state to
corrupt, and every checkpoint is as durable as git itself.

Public API:
    gitundo.core.GitUndo    - programmatic access to all operations
    gitundo.guard           - destructive-command detection used by the shell guard
    gitundo.autowrap        - install/remove the auto-guard shell wrapper
"""

__title__ = "gitundo"
__version__ = "0.1.0"
__license__ = "MIT"
__author__ = "gitundo contributors"
__description__ = "The undo button git never had. Automatic safety-net snapshots for any git repo."

# The hidden ref (namespace) under which all checkpoints live. Nothing else in
# the repository is ever touched: the working tree, the index and branch refs
# are all left exactly as they were.
CHECKPOINT_REF = "refs/gitundo/checkpoints"
GUARD_ENV_DISABLE = "GITUNDO_DISABLE"

# Identity stamped on every snapshot commit so users can spot them instantly in
# ``git log`` / tooling and so snapshots never get signed or attributed to the
# user's real identity.
SNAPSHOT_AUTHOR = "gitundo"
SNAPSHOT_EMAIL = "gitundo@localhost"
