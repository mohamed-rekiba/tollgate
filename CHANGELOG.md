# Changelog

## [0.11.0](https://github.com/tollgate-ai/tollgate/compare/v0.10.0...v0.11.0) (2026-11-26)


### Features

* **setup:** the project's checks are hooks of its own pre-commit config ([#152](https://github.com/tollgate-ai/tollgate/issues/152)) ([9c746af](https://github.com/tollgate-ai/tollgate/commit/9c746af488f10212aa666445f5c558a177219e6a))

## [0.10.0](https://github.com/tollgate-ai/tollgate/compare/v0.9.2...v0.10.0) (2026-11-25)


### Features

* **diagram:** moving dots on every arrow, and one Tollgate hook run from setup/ ([#150](https://github.com/tollgate-ai/tollgate/issues/150)) ([088b120](https://github.com/tollgate-ai/tollgate/commit/088b1203559aace06a093d1c9783695c2ce2317c))

## [0.9.2](https://github.com/tollgate-ai/tollgate/compare/v0.9.1...v0.9.2) (2026-11-25)


### Bug Fixes

* **tests:** start the tests without the git location variables ([#147](https://github.com/tollgate-ai/tollgate/issues/147)) ([8e15561](https://github.com/tollgate-ai/tollgate/commit/8e1556105f400bccfa6f1fe7759c31285e4f54ea))

## [0.9.1](https://github.com/tollgate-ai/tollgate/compare/v0.9.0...v0.9.1) (2026-11-25)


### Bug Fixes

* **init:** run Tollgate's checks from one script, and keep the project's checks as plain hooks ([425af0b](https://github.com/tollgate-ai/tollgate/commit/425af0ba3548dc9fbd284bbb1a08fc45157295e7))

## [0.9.0](https://github.com/tollgate-ai/tollgate/compare/v0.8.2...v0.9.0) (2026-11-25)


### Features

* **init:** run the project's checks side by side before a push ([#144](https://github.com/tollgate-ai/tollgate/issues/144)) ([5f26250](https://github.com/tollgate-ai/tollgate/commit/5f26250019200c97ffa7215d1c6108d548057201))


### Bug Fixes

* **init:** run the hook checks with uv ([#143](https://github.com/tollgate-ai/tollgate/issues/143)) ([442ea27](https://github.com/tollgate-ai/tollgate/commit/442ea279c77ebc4d1da7a89e0d96d6b829b1805f))
* **plan:** send a plan that breaks a rule back to the planner, not stop the task ([#141](https://github.com/tollgate-ai/tollgate/issues/141)) ([0f02602](https://github.com/tollgate-ai/tollgate/commit/0f02602a323b2dd3bfc52d6c9b726bf89c2310f3))

## [0.8.2](https://github.com/tollgate-ai/tollgate/compare/v0.8.1...v0.8.2) (2026-11-25)


### Bug Fixes

* **analysis:** let a fact about a missing item cite its folder, and say how to fix a refused analysis ([#139](https://github.com/tollgate-ai/tollgate/issues/139)) ([7319177](https://github.com/tollgate-ai/tollgate/commit/73191773cb6a163b91a2d5717f2a491769aea1dc))

## [0.8.1](https://github.com/tollgate-ai/tollgate/compare/v0.8.0...v0.8.1) (2026-11-25)


### Bug Fixes

* **init:** write the settings from a draft file, so the guard stays closed ([#137](https://github.com/tollgate-ai/tollgate/issues/137)) ([db81be9](https://github.com/tollgate-ai/tollgate/commit/db81be93bd750a0dab90b7b2ba707f3a497ab2d8))

## [0.8.0](https://github.com/tollgate-ai/tollgate/compare/v0.7.0...v0.8.0) (2026-11-25)


### Features

* **docs:** make a task write what it adds into the spec docs ([#135](https://github.com/tollgate-ai/tollgate/issues/135)) ([cc1c2c9](https://github.com/tollgate-ai/tollgate/commit/cc1c2c9560530ff50446d9a58c4fbe0860ccacba))

## [0.7.0](https://github.com/tollgate-ai/tollgate/compare/v0.6.0...v0.7.0) (2026-11-24)


### ⚠ BREAKING CHANGES

* **gate:** add the spec setting, and remove signers and owners ([#130](https://github.com/tollgate-ai/tollgate/issues/130))

### Features

* **docs:** add the decision record step, and close gaps in the spec rules ([#132](https://github.com/tollgate-ai/tollgate/issues/132)) ([176cd00](https://github.com/tollgate-ai/tollgate/commit/176cd004a4f7b8a989a3d1af2b8de7fefb7feea8))
* **gate:** add the spec setting, and remove signers and owners ([#130](https://github.com/tollgate-ai/tollgate/issues/130)) ([bda3ac5](https://github.com/tollgate-ai/tollgate/commit/bda3ac5abf9fe7e78b31ea1e14d1083b8bde8684))


### Bug Fixes

* **checks:** stop the local git settings from changing the checks and the tests ([#133](https://github.com/tollgate-ai/tollgate/issues/133)) ([8136b0f](https://github.com/tollgate-ai/tollgate/commit/8136b0f5e94c8553e0703bb97f4641790a688550))

## [0.6.0](https://github.com/tollgate-ai/tollgate/compare/v0.5.0...v0.6.0) (2026-11-23)


### Features

* **brainstorm:** turn a rough idea into a brief ([#128](https://github.com/tollgate-ai/tollgate/issues/128)) ([5f1a844](https://github.com/tollgate-ai/tollgate/commit/5f1a8448f1fc4a35adbbd087e7b2156d957af1e5))


### Bug Fixes

* **diagram:** draw pre-commit as its own object, and keep one meaning for each object ([#127](https://github.com/tollgate-ai/tollgate/issues/127)) ([e9a87e9](https://github.com/tollgate-ai/tollgate/commit/e9a87e9f471048041384e899c823939628e3d432))
* **task:** send back a plan that leaves the required README missing, and replay it ([#126](https://github.com/tollgate-ai/tollgate/issues/126)) ([8f6d87a](https://github.com/tollgate-ai/tollgate/commit/8f6d87a6741110d37483c684f101ffb20a522bc5))

## [0.5.0](https://github.com/tollgate-ai/tollgate/compare/v0.4.0...v0.5.0) (2026-11-23)


### Features

* **diagram:** draw C4, use case, class, and ER diagrams, and a C4 context as a scene ([#122](https://github.com/tollgate-ai/tollgate/issues/122)) ([31313e1](https://github.com/tollgate-ai/tollgate/commit/31313e19b75f95265bc3e8ae49c12d3af6ce4470))
* **setup:** check the words drawn in a diagram against the word list ([#124](https://github.com/tollgate-ai/tollgate/issues/124)) ([556a87b](https://github.com/tollgate-ai/tollgate/commit/556a87b10a33d4fcf6d83f6b94d38309d9211749))


### Bug Fixes

* **session:** log each event once on a replay, and let existing tests cover a kept behavior ([#125](https://github.com/tollgate-ai/tollgate/issues/125)) ([edbeb06](https://github.com/tollgate-ai/tollgate/commit/edbeb06a29ec65e4c7c3ffe3d2a04bd4f78aa7bf))

## [0.4.0](https://github.com/tollgate-ai/tollgate/compare/v0.3.0...v0.4.0) (2026-11-23)


### ⚠ BREAKING CHANGES

* **tickets:** ask each ticket for the kinds of test it needs ([#121](https://github.com/tollgate-ai/tollgate/issues/121))

### Features

* **settings:** run background roles in Docker's Claude Code image by default ([#118](https://github.com/tollgate-ai/tollgate/issues/118)) ([86d96cf](https://github.com/tollgate-ai/tollgate/commit/86d96cfc3c0d48334bc05a1b0acb09d2c26b4a67))
* **tickets:** ask each ticket for the kinds of test it needs ([#121](https://github.com/tollgate-ai/tollgate/issues/121)) ([bddd463](https://github.com/tollgate-ai/tollgate/commit/bddd463fdd17766cfac78dc58980c7bcc15cdce9))


### Bug Fixes

* **driver:** never let two drivers hold one run lock ([#120](https://github.com/tollgate-ai/tollgate/issues/120)) ([479642d](https://github.com/tollgate-ai/tollgate/commit/479642daa6f532c33f22de940f08b59cc6789799))

## [0.3.0](https://github.com/tollgate-ai/tollgate/compare/v0.2.0...v0.3.0) (2026-11-22)


### ⚠ BREAKING CHANGES

* **driver:** run Tollgate's roles as subagents in your own session ([#115](https://github.com/tollgate-ai/tollgate/issues/115))

### Features

* **agents:** ship each role as a Claude Code subagent ([#111](https://github.com/tollgate-ai/tollgate/issues/111)) ([4728621](https://github.com/tollgate-ai/tollgate/commit/4728621a80a27fe8c5fd2efe31e8dfc59b9000b9))
* **driver:** run Tollgate's roles as subagents in your own session ([#115](https://github.com/tollgate-ai/tollgate/issues/115)) ([db50916](https://github.com/tollgate-ai/tollgate/commit/db50916f88751370a26dbe28ea618a1587af8c1e))
* **hooks:** apply each role's rules by agent type, and let your session push a branch ([#113](https://github.com/tollgate-ai/tollgate/issues/113)) ([72a6148](https://github.com/tollgate-ai/tollgate/commit/72a614848a6741942b6b26fdc97e6b1c0e4654a1))


### Bug Fixes

* **setup:** stop a home from showing a change each time a project moves on ([#114](https://github.com/tollgate-ai/tollgate/issues/114)) ([970a3d3](https://github.com/tollgate-ai/tollgate/commit/970a3d34c0681e3978627a118e56da998a4d337a))

## [0.2.0](https://github.com/tollgate-ai/tollgate/compare/v0.1.1...v0.2.0) (2026-11-22)


### Features

* **diagram:** draw UML sequence diagrams and state machines ([#109](https://github.com/tollgate-ai/tollgate/issues/109)) ([ad9722b](https://github.com/tollgate-ai/tollgate/commit/ad9722b1aa559fdd9e4774d7eda7d64d0f824e2a))

## [0.1.1](https://github.com/tollgate-ai/tollgate/compare/v0.1.0...v0.1.1) (2026-11-22)


### Bug Fixes

* **setup:** skip CHANGELOG.md in the writing check ([#108](https://github.com/tollgate-ai/tollgate/issues/108)) ([b0e0cbb](https://github.com/tollgate-ai/tollgate/commit/b0e0cbb0f95a388046404f51a02217500643ea3b))
* **setup:** skip pip requirements files in the writing check ([#104](https://github.com/tollgate-ai/tollgate/issues/104)) ([e9a17a2](https://github.com/tollgate-ai/tollgate/commit/e9a17a2ce35285317c6db18ac891e7821457360d))
* **skills:** run the plugin's Python code, not a project package of the same name ([#107](https://github.com/tollgate-ai/tollgate/issues/107)) ([0207f33](https://github.com/tollgate-ai/tollgate/commit/0207f33823f0c39eba08c286e244642b711f0fbe))

## 0.1.0 (2026-11-22)


### Features

* **diagram:** draw diagrams as SVG, in light and dark ([b3b5d0f](https://github.com/tollgate-ai/tollgate/commit/b3b5d0f72d590a2acd50908375a382fc5d2e74a5))
* **driver:** analyze, plan, and build each ticket until it passes ([6d95ad0](https://github.com/tollgate-ai/tollgate/commit/6d95ad0fb33de727f64e34499e41ba86bcb55b6d))
* **driver:** the builder writes a diagram's spec, and Tollgate draws it ([#98](https://github.com/tollgate-ai/tollgate/issues/98)) ([3a5ea13](https://github.com/tollgate-ai/tollgate/commit/3a5ea133454b0ecf56c3afd65d98292c3adc4815))
* **gate:** the gate, the store, and the formats it reads ([d7a0ec9](https://github.com/tollgate-ai/tollgate/commit/d7a0ec92888de7f2c1a55475c7e02a66e1f9af06))
* **hooks:** the guard and the policy of each role ([d37a9b5](https://github.com/tollgate-ai/tollgate/commit/d37a9b5f0a4a862b63b413372afcde4511744dc1))
* **setup:** set up a project, and check each commit with pre-commit ([16a6b07](https://github.com/tollgate-ai/tollgate/commit/16a6b0755fcdf1e81012fb266e0126d6d3b74d0f))
* **skills:** the commands you type in Claude Code ([a8d32b2](https://github.com/tollgate-ai/tollgate/commit/a8d32b2db613b09bd72e4312a2848f66bbcf40c1))


### Bug Fixes

* **diagram:** pin each label to the center of its part ([#97](https://github.com/tollgate-ai/tollgate/issues/97)) ([b28372a](https://github.com/tollgate-ai/tollgate/commit/b28372a53192c9a73925b1c735f92dea9012b14a))
* **gate:** read citations and checklist marks without slow backtracking ([#101](https://github.com/tollgate-ai/tollgate/issues/101)) ([f240334](https://github.com/tollgate-ai/tollgate/commit/f240334c8668b64557f19de27684dc4f55381648))
