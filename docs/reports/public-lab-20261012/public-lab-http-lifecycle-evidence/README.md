# HTTP lifecycle evidence

The original plan was committed as `d9ac41e9a6b92e473c3f9dbbeb57ed74ea05c67c` before execution. A separately recorded amendment permits one original-ten-test run under explicit localhost execution permission. It does not rewrite the original plan or authorize random retries.

- `original-r2/`: exact copies of both historical nine-pass/one-Win10053 runs.
- `runs/gui-r5-pre-01/`: nine passes and one Win10013 failure on the initial `/state` request. This permission-blocked attempt did not reach the historical rejected POST.
- `runs/gui-r5-pre-02/`: the one controlled split-send probe. The original handler reads zero body bytes with two kernel bytes pending, yet the client receives a correct403 JSON response after shutdown. There is no Win10053. Its failure is the diagnostic's new body-consumption expectation, not the old HTTP status/security assertion.
- `prechange-server-source.py.txt` and `prechange-test-source.py.txt`: exact source bytes used by that probe, including its failed assertion. They are historical diagnostic evidence, not a claim that mandatory body consumption has been established as an HTTP acceptance gate.
- The matching XML files preserve actual test results; no failure is renamed or suppressed.

The controlled event barriers alter timing deliberately. The timestamp clock is coarse on this host; the trace supports event order, not nanosecond timing measurements. The result does not prove that unread bytes caused historical Win10053, and does not exclude an untested late-body race or another transient cause.

Production, original tests and their assertions remain unchanged. `runs/gui-r5-amended-03/` records the one authorized original-ten-test comparison:10 passed, no source change and no fourth HTTP run. This is not proof of the historical cause or a fix. The one-purpose probe is retained as exact historical source, not promoted to a permanent CI body-consumption gate. The main report and metadata seal link all actual outcomes. No fit, new scientific solve, source acquisition or network/security-settings change is part of this work.
