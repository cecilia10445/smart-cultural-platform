# Round 17C worktree convergence

`/home/lily/桌面/smart-cultural-platform` is the formal integration directory.
It was rebuilt from `origin/main` and the audited experimental commit was
cherry-picked before this business integration branch was created.

The earlier uncommitted Reasonix state was exported to a SHA-256 verified,
credential-free backup under
`/mnt/hgfs/share/smart-cultural-platform-old-workspace-backup/` before its
tracked source changes were precisely cleared. `.env`, virtual environments,
installed dependencies and historical artifacts were not deleted.

Keep both directories until the integration branch is reviewed and merged.
Archive or remove the remaining non-formal worktree only through a separate,
user-approved operation; never use `git clean` or destructive resets for that
convergence.
