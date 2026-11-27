# Rules for this project

- Draw every diagram with the `diagram` skill (`skills/diagram/SKILL.md`): a flow in the standard flowchart shapes, a UML sequence diagram or state machine, a C4 diagram, a UML use case or class diagram, an ER diagram, or an isometric scene for the big picture. Write every word for a person: no ids, tag names, or code names in a picture, except where the reader types the name, like the icon sheet. Never write a Mermaid block or a picture of text. `tests/test_diagrams.py` enforces this.
- This repo draws its diagrams with `python3 docs/diagrams/build.py`, which adds the banner and the icon sheet.
- For AWS, use the official AWS icons through `diagram/aws.py`, unchanged, and never commit the AWS package to git.
