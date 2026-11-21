# Lens: simplicity

You read a whole plan. For each part of it, ask three questions:

1. **Is it needed?** It serves something the task asks for. A part that serves a need nobody stated is a `major` finding.
2. **Does the code already have it?** Search the project. A part that rebuilds something the project has is a `major` finding. Name the file that has it.
3. **Is anything built for later?** Extension points, options, or layers with one user today are a `minor` finding, or `major` if they add a ticket.

A plan that could drop a whole ticket and still do the task gets a `blocking` finding.

Done when every ticket and every file in the plan has been asked all three questions.
