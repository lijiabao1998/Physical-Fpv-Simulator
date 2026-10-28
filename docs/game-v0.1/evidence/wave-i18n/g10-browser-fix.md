First bilingual integration push40439527474 / PR40439531960: original117unit,
reference/build pass;47browser pass,3 newly added bilingual comparisons fail.
Exact source41b645e. Raw push log retained. Original artifact12705519512 remains:
https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/40439527474/artifacts/12705519512
SHA25631447d10fc24c76bc788c1cc5c5274309b7b6edc7cdcd3b2ae22076b6f78d6d4.
The new assertion compared body positions across asynchronous UI clicks while the
fresh disarmed world was still legitimately stepping/settling on ground. This
was a test wiring mistake, not evidence language changes physics. Use existing
native Pause before baseline snapshot, assert exact unchanged state thereafter.
No product, physical threshold, timeout, original tests or safety guard change.
