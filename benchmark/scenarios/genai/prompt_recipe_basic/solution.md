# Solution

Executable baseline for the current CLI and harness.

## Not Yet Validated By Harness

- The benchmark intent is a prompt-recipe-style DSS GenAI workflow over the `products` dataset.
- The current executable path proves LLM-generated summaries persisted in an UploadedFiles dataset only, not as a native prompt recipe.

```bash
python3 -c 'import csv,json,subprocess,shlex; proj="{project}"; llm=subprocess.check_output(f"dku llm list -P {proj} -o json | jq -r \".[0].id\"", shell=True, text=True).strip(); rows=json.loads(subprocess.check_output(f"dku dataset head products -P {proj} -n 5 -o json", shell=True, text=True)); out=f"/tmp/{proj}_product_summaries.csv"; f=open(out,"w",newline=""); w=csv.DictWriter(f, fieldnames=["name","summary"]); w.writeheader(); [w.writerow({"name": row["name"], "summary": json.loads(subprocess.check_output("dku llm completion " + shlex.quote(llm) + " " + shlex.quote("Write one short product summary for " + row["name"] + " in category " + row["category"] + ".") + " -P " + proj + " -o json", shell=True, text=True))["text"]}) for row in rows]; f.close()'
dku dataset create product_summaries --type UploadedFiles -P {project}
dku dataset upload product_summaries /tmp/{project}_product_summaries.csv --overwrite -P {project}
```
