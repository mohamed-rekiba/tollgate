# Lab cleanup

The experiments ran in this repository, because the session that built it could not create a separate one. That session could not delete branches or tags either. The owner deletes these:

| Kind | Name |
| --- | --- |
| Branch | `tg-lab/ci-red` |
| Branch | `tg-lab/e5-action` |
| Branch | `tg-lab/e1-run` |
| Branch | `tg-lab/e3-pr` |
| Branch | `tg-lab/s1-action` |
| Tag | `tg-lab/e1-44843991100` |

Pull requests 1 and 2 are closed.

```
git push origin --delete tg-lab/ci-red tg-lab/e5-action tg-lab/e1-run tg-lab/e3-pr tg-lab/s1-action
git push origin --delete refs/tags/tg-lab/e1-44843991100
```
