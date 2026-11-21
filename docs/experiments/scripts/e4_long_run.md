# E4, the part that needs a real session

1. In Claude Code, inside a project, run: `setsid -f sh -c 'while true; do date >> /tmp/e4.out; sleep 10; done' >/dev/null 2>&1 </dev/null`
2. Close Claude Code.
3. Wait one minute, then run `tail -3 /tmp/e4.out`.
4. Pass if the last line is less than 20 seconds old. Then stop the loop with `pkill -f e4.out`.
