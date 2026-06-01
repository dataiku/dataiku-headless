# Solution

```bash
# Visual flow: spend per contract, then enrich with that contract's status/master data
dku recipe create-group compute_spend_by_contract -i erp_postings --output-ds spend_by_contract -k contract_ref --agg amount_eur:sum --no-global-count -P {project}
dku recipe run compute_spend_by_contract --wait --auto-update-schema -P {project}
dku recipe create-join enrich_savings -i spend_by_contract -i contracts --join-key 'contract_ref=contract_id' --join-type LEFT --output-ds contract_savings -P {project}
dku recipe run enrich_savings --wait --auto-update-schema -P {project}

# Nightly automation: scenario with a build step + a daily time trigger
dku scenario create nightly_contract_eval -P {project}
python3 -c 'import json; step={"id":"build_savings","type":"build_flowitem","name":"Rebuild contract savings","enabled":True,"runConditionType":"RUN_IF_STATUS_MATCH","runConditionStatuses":["SUCCESS","WARNING"],"params":{"builds":[{"type":"DATASET","itemId":"contract_savings","partitionsSpec":""}],"jobType":"NON_RECURSIVE_FORCED_BUILD"}}; open("/tmp/{project}_scn_steps.json","w").write(json.dumps({"params":{"steps":[step]}}))'
dku scenario set-definition nightly_contract_eval -d @/tmp/{project}_scn_steps.json -P {project}
dku scenario add-trigger nightly_contract_eval --trigger '{"active":true,"type":"temporal","params":{"frequency":"Daily","hour":2,"minute":0,"repeatFrequency":1,"timezone":"SERVER"}}' -P {project}
```
