# Solution

```bash
dku folder list -P {project} -o json
dku recipe create campaign_combined --type python --output-ds campaign_combined --connection filesystem_managed -P {project}
python3 -c "import os,dataikuapi; c=dataikuapi.DSSClient(os.environ['DKU_URL'],os.environ['DKU_API_KEY']); proj=c.get_project('{project}'); fid=next(f['id'] for f in proj.list_managed_folders() if f['name']=='campaign_files'); r=proj.get_recipe('campaign_combined'); s=r.get_settings(); s.add_input('main',fid); s.save()"
python3 -c "open('/tmp/recipe_code.py','w').write('import dataiku\nimport pandas as pd\n\nfolder = dataiku.Folder(\"campaign_files\")\noutput_ds = dataiku.Dataset(\"campaign_combined\")\n\ndfs = []\nfor path in folder.list_paths_in_partition():\n    if path.endswith(\".csv\"):\n        with folder.get_download_stream(path) as f:\n            dfs.append(pd.read_csv(f))\ndf = pd.concat(dfs, ignore_index=True)\noutput_ds.write_with_schema(df)\n')"
dku recipe set-code campaign_combined --code @/tmp/recipe_code.py -P {project}
dku recipe run campaign_combined --wait --auto-update-schema -P {project}
```
