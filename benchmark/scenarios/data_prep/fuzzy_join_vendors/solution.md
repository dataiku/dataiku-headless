# Solution

```bash
dku dataset create vendor_product_match --type UploadedFiles -P {project}
dku recipe create-fuzzy-join match_vendors -i vendors -i products --output-ds vendor_product_match --fuzzy-key product_category --method LEVENSHTEIN --max-distance 2 -P {project}
```
