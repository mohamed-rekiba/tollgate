# Changelog

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
