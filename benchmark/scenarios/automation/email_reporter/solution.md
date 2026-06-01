# Solution

```bash
dku scenario create alerts_scenario -P {project}
python3 -c 'import json; payload={"reporters":[{"id":"mail_reporter","name":"Mail reporter","sendOn":"END","runCondition":"outcome != '\''SUCCESS'\''","messaging":{"type":"mail-scenario","configuration":{"recipient":"alerts@example.com","subject":"Scenario failed","message":"Scenario ${scenarioName} failed with outcome ${scenarioOutcome}"}}}]}; open("/tmp/{project}_reporter.json","w").write(json.dumps(payload))'
dku scenario set-definition alerts_scenario -P {project} -d @/tmp/{project}_reporter.json
```
