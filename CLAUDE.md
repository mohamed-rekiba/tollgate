# Rules for this project

- Draw every diagram as SVG with the `diagram` skill (`skills/diagram/SKILL.md`): a flat blueprint for steps and flows, an isometric scene for the big picture, a diagram drawn from the code when the code already says it. Never write a Mermaid block or an image of text. `tests/test_diagrams.py` enforces this.
- Use Tollgate's icons from `driver/icons.py`. For AWS, use the official AWS icons through `driver/aws.py`, unchanged, and never commit the AWS package to git.
