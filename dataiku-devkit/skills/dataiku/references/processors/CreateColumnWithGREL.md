# CreateColumnWithGREL

**When:** Custom expressions that no dedicated processor handles. **THIS IS THE LAST RESORT.**

**CLI shortcut:** `dku recipe add-formula RECIPE --expr "upper(city)" --column city_upper -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `expression` | Yes | GREL expression |
| `column` | Yes | Output column name |

```json
{"expression": "if(price > 100, 'premium', 'standard')", "column": "tier"}
```

**Before using this, check:** Could `VisualIfRule`, `StringTransformer`, `DateParser`, `ColumnsConcat`, `BinnerProcessor`, or another processor do this instead?
