---
name: repo-state
description: Check where the code actually is before touching it — working tree, HEAD, and what the server is running. Use at the start of any session that will edit or deploy a repo, after any interruption, and before claiming a change is live.
---

# Where is the code, actually?

Three questions, asked before doing anything else. Each one costs real time
when it is assumed instead of checked.

## 1. What is uncommitted?

```sh
git status --porcelain
```

Not "is it clean" — **whose** changes are these. On a machine that may be running
more than one agent, an unexpected modified file is not yours and must not be
committed by you. If a file you did not touch is modified, stop and say so
before doing anything else.

## 2. What is HEAD, and who wrote it?

```sh
git log -5 --date=format:'%m-%d %H:%M' --pretty='%h %ad %an — %s'
git rev-list --left-right --count @{u}...HEAD    # behind/ahead of the remote
```

Read the **author and time**, not just the subject. Commits you did not make,
appearing between your own, mean another session is writing to this repo. That
changes what you may safely do; it does not mean the work is yours to build on.

## 3. Is the server behind?

```sh
git rev-parse --short HEAD
ssh <host> 'sudo -n docker ps --filter name=<project> --format "{{.Names}} {{.Image}}"'
```

Compare the deployed image tag against HEAD, **per service**. A green CI badge
says an image was built, not that anything pulled it. A bot can sit two commits
behind for days — one of them a real user-facing fix — while every dashboard
looks green.

## What to do with the answers

- **Uncommitted files you don't recognise** → do not commit, do not stash, do
  not rebase. Report it. Check `ps aux | grep -i claude` for other sessions.
- **Unfamiliar commits** → read their diffstat before building on them. Another
  session may be editing the same file you are about to.
- **Server behind HEAD** → say which services and by how many commits, and what
  is in the gap. "Deploy is behind" is not useful; "the bot is two commits
  behind and one of them fixes X" is.

## Say it plainly

Report the three answers before starting work, in one short block. If all three
are boring, one line is enough. The point is that the answer was measured, not
that it was long.

Never say a change is live because CI passed. Live means the running image's SHA
matches, and you looked.
