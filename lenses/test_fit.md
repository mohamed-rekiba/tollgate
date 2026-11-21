# Lens: test fit

You read a ticket and its new tests, before they are locked. For each test, confirm three things:

1. **It fits its item.** The test checks what the item says, at a seam, and its name holds the item id.
2. **It can fail.** Name one plain change to the code that would make it fail. A test that passes whatever the code does is blocking.
3. **Its expected result comes from the ticket.** An expected value copied from the code under test is blocking.

Also blocking: a must-have item with no test, and a test that fails now for a reason other than missing behavior, such as an import error.

Done when every test has an answer for all three points. Put one entry per test under `items`:

```json
{"test": "test_c1_retries_twice", "item": "C1", "fits": true, "can_fail_by": "remove the retry loop", "expected_from_ticket": true}
```
