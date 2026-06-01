# Solution

```bash
dku insight create "Revenue by Region" --type chart --dataset orders -P {project}
dku insight list -P {project} -o json | jq -r '.[] | select(.name=="Revenue by Region") | .id' > /tmp/{project}_chart_insight_id.txt
python3 -c 'import json,pathlib; iid=pathlib.Path("/tmp/{project}_chart_insight_id.txt").read_text().strip(); payload={"id":iid,"projectKey":"{project}","type":"chart","name":"Revenue by Region","listed":True,"params":{"engineType":"LINO","datasetSmartName":"orders","def":{"type":"grouped_columns","variant":"normal","name":"Revenue by Region","userEditedName":True,"genericDimension0":[{"column":"region","type":"ALPHANUM","isA":"dimension","maxValues":100,"filters":[],"sort":{"type":"NATURAL","sortAscending":True},"numParams":{"mode":"FIXED_NB","emptyBinsMode":"ZEROS"}}],"genericDimension1":[],"genericMeasures":[{"column":"amount","function":"SUM","type":"NUMERICAL","displayed":True,"isA":"measure","displayAxis":"axis1","displayType":"column","computeMode":"NORMAL"}],"facetDimension":[],"animationDimension":[],"filters":[],"xDimension":[],"yDimension":[],"tooltipMeasures":[],"showLegend":True,"colorOptions":{"singleColor":"#2678b2","transparency":0.75}},"refreshableSelection":{"selection":{"samplingMethod":"FULL","maxRecords":10000},"autoRefreshSample":False}}}; open("/tmp/{project}_chart.json","w").write(json.dumps(payload))'
dku insight set-definition "$(cat /tmp/{project}_chart_insight_id.txt)" -d @/tmp/{project}_chart.json -P {project}
dku insight validate "$(cat /tmp/{project}_chart_insight_id.txt)" -P {project}
```
