---
name: prepare-currency-splitter
description: "Observed JSON patterns for the CurrencySplitter prepare/shaker processor."
---

# CurrencySplitter Processor

Split a currency-formatted string column into separate amount and currency code columns.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid input column name | Source column containing currency-formatted values. |
| `outColAmount` | yes | `string<column_name>` | Any valid output column name | Output column containing extracted numeric amount. |
| `outColCurrencyCode` | yes | `string<column_name>` | Any valid output column name | Output column containing extracted currency code. |
| `pristineAmount` | yes | `boolean` | `true` \| `false` | When `true`, preserves amount formatting as-is; when `false`, normalizes/parses amount value. |

## Canonical Variants

### Split currency string with parsed amount

```json
{
  "type": "CurrencySplitter",
  "params": {
    "inCol": "score_usd",
    "outColAmount": "score_usd_amount",
    "outColCurrencyCode": "score_usd_currency_code",
    "pristineAmount": false
  }
}
```

### Split currency string and keep pristine amount format

```json
{
  "type": "CurrencySplitter",
  "params": {
    "inCol": "score_usd",
    "outColAmount": "score_usd_amount_2",
    "outColCurrencyCode": "score_usd_currency_code_2",
    "pristineAmount": true
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `CurrencySplitter`.
3. Keep `outColAmount` and `outColCurrencyCode` names distinct from source and existing derived columns.
4. Choose `pristineAmount` based on downstream needs (raw formatting vs normalized numeric value).

## References

- Dataiku DSS: Split currencies in column (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/currency-splitter.html
