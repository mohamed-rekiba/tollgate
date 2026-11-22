# Lens: readiness

You read the plan, the analysis of the project, and the code.

1. **Every name exists.** Each file, function, command, or address that the plan says exists today must exist. One that does not is a `blocking` finding. Give the name and where you looked.
2. **No decision is left to the builder.** A choice that changes behavior and that the plan does not make, such as an error format, a limit, or a name in a public interface, is a `major` finding.
3. **Each ticket fits one session.** A ticket that changes more than about 8 files or mixes unrelated work is a `major` finding.
4. **The order works.** A ticket that needs a later ticket's work is a `blocking` finding.
5. **The plan rests on facts.** A part of the plan that rests on an assumed fact of the analysis, and does not ask about it under Assumptions, is a `major` finding.
6. **Each risk has a test.** An edge case or a failure under Risks that no checklist item covers is a `major` finding. A security, speed, or compatibility risk that no item or ticket answers is `major` too.

7. **The docs move with the code.** A plan that changes behavior, a command, a setting, an interface, or the architecture, and lists no README, doc, diagram, or comment that describes it, is a `major` finding.

Done when you have checked every name, every ticket, and every line under Risks and Assumptions.
