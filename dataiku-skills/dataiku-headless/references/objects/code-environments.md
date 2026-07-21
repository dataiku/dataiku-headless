# Code environments

A code environment supplies a language runtime and installed dependencies for
Python, R, PySpark, ML analysis, and code-agent work.

An asset can name an environment, inherit a configured default, or use a built-in
environment. Matching the language alone does not prove package, runtime, or
system-library compatibility. Use `list_code_envs` to discover exact names, then
ground compatibility in the affected asset and its error or requirements. Do not
select an explicit environment solely because an import failed.
