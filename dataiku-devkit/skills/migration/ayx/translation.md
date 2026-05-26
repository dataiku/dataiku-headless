# Alteryx tool to Dataiku recipe translation

Use this entrypoint to choose the relevant Alteryx translation reference.

| Source pattern | Read |
|---|---|
| TextInput, DbFile, Formula, Select, Filter, Sort, Sample, Unique | `tools-core.md` |
| Join, JoinMultiple, AppendFields, Union, Summarize, CrossTab, Transpose | `tools-join-reshape.md` |
| MultiRowFormula, RunningTotal, RecordID, TextToColumns, RegEx, DynamicRename, DateTime, GenerateRows, JSONParse | `tools-state-parsing.md` |
| Download, FindReplace, Spatial, PearsonCorrelation, Macros, Dynamic Input, YXDB, Email, Excel, Analytic Apps, Predictive Tools | `tools-io-apps-ml.md` |
| Range joins, conditional reroutes, component-stat chains, recurring collapse patterns | `workflow-patterns.md` |

Read `overview.md` first for the migration process and `semantics.md` when values disagree.
