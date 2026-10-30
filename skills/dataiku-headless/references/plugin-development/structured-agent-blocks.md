# Structured-Agent Block Plugin Components

Start with [Plugin development](../plugin-development.md).

Use `python-structured-agent-blocks/<component-id>/block.json`. Its `pyClazzName`
names the implementation class, typically in `python-lib/`; the code does not
have to sit beside the descriptor. Follow the [block tutorial](https://developer.dataiku.com/latest/tutorials/plugins/structured-agent/generality/index.html).
Define which state keys the block reads and writes, where execution goes next, and
what the user sees. Test those behaviors, including missing state, in a small
Structured Visual Agent.
[TypeSafe AI](https://github.com/dataiku/dss-plugin-typesafe-ai) shows how the descriptor points to its implementation class.
