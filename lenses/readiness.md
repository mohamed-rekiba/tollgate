# Lens: readiness

You read the plan and the code.

1. **Every name exists.** Each file, function, command, or address that the plan says exists today must exist. One that does not is a `blocking` finding. Give the name and where you looked.
2. **No decision is left to the builder.** A choice that changes behavior and that the plan does not make, such as an error format, a limit, or a name in a public interface, is a `major` finding.
3. **Each ticket fits one session.** A ticket that changes more than about 8 files or mixes unrelated work is a `major` finding.
4. **The order works.** A ticket that needs a later ticket's work is a `blocking` finding.

Done when you have checked every name and every ticket.
