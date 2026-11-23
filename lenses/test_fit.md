# Lens: test fit

You read a ticket and its tests, before they are locked: the new tests, and the existing tests the test writer points an item at. For each test, confirm four things:

1. **It fits its item.** The test checks what the item says, at a seam. A new test's name holds the item id. An existing test keeps its own name, and it must really assert the item's claim: one that only runs near it is blocking.
2. **It can fail.** Name one plain change to the code that would make it fail. A test that passes whatever the code does is blocking.
3. **Its expected result comes from the ticket.** An expected value copied from the code under test is blocking.
4. **It is the kind its item claims.** A `boundary` test checks the limit and one step past it, an `integration` test crosses a real file, process, or database, and so on, as the test writer's role defines each kind. A test of another kind is blocking.

Also blocking: a must-have item with no test, and a test that fails now for a reason other than missing behavior, such as an import error.

Done when every test has an answer for all four points. Put one entry per test under `items`:

```json
{"test": "test_c1_retries_twice", "item": "C1", "fits": true, "can_fail_by": "remove the retry loop", "expected_from_ticket": true, "kind_fits": true}
```
