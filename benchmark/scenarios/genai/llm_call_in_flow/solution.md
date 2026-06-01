# Solution

Executable baseline for the current CLI and harness.

## Not Yet Validated By Harness

- The benchmark intent is a native in-flow LLM transformation in DSS.
- The current executable path proves LLM-generated output data only, not recipe-native flow representation.

```bash
python3 -c 'import csv,json,subprocess,shlex; proj="{project}"; llm=subprocess.check_output(f"dku llm list -P {proj} -o json | jq -r \".[0].id\"", shell=True, text=True).strip(); rows=json.loads(subprocess.check_output(f"dku dataset head customers -P {proj} -n 3 -o json", shell=True, text=True)); out=f"/tmp/{project}_customer_messages.csv"; f=open(out,"w",newline=""); w=csv.DictWriter(f, fieldnames=["name","tier","message"]); w.writeheader(); [w.writerow({"name": row["name"], "tier": row["tier"], "message": json.loads(subprocess.check_output("dku llm completion " + shlex.quote(llm) + " " + shlex.quote("Write one short outreach sentence for " + row["name"] + " who has tier " + row["tier"] + ".") + " -P " + proj + " -o json", shell=True, text=True))["text"]}) for row in rows]; f.close()'
dku dataset upload customer_messages /tmp/{project}_customer_messages.csv -P {project}
```
