# Solution

```bash
dku scenario create nightly_pipeline -P {project}
python3 -c 'import json; d={"reporters":[{"id":"fail_alert","name":"Failure alert","sendOn":"END","runCondition":"outcome != '\''SUCCESS'\''","messaging":{"type":"mail-scenario","configuration":{"recipient":"ops@example.com","subject":"Nightly pipeline failed","message":"Quality check failed"}}},{"id":"success_notify","name":"Success notification","sendOn":"END","runCondition":"outcome == '\''SUCCESS'\''","messaging":{"type":"mail-scenario","configuration":{"recipient":"team@example.com","subject":"Nightly pipeline complete","message":"Pipeline ran successfully"}}}]}; open("/tmp/nightly_reporters.json","w").write(json.dumps(d))'
dku scenario get-definition nightly_pipeline -P {project} -o json > /tmp/nightly_current.json
python3 -c 'import json; curr=json.load(open("/tmp/nightly_current.json")); reps=json.load(open("/tmp/nightly_reporters.json"))["reporters"]; curr["reporters"]=reps; open("/tmp/nightly_merged.json","w").write(json.dumps(curr))'
dku scenario set-definition nightly_pipeline -P {project} -d @/tmp/nightly_merged.json
```
