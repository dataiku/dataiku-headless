---
name: prepare-currency-converter-processor
description: "Observed JSON patterns for the CurrencyConverterProcessor prepare/shaker processor."
---

# CurrencyConverterProcessor Processor

Convert numeric amounts from one currency to another using exchange rates at a selected reference date.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inputColumn` | yes | `string<column_name>` | Any valid numeric input column name | Amount column to convert. |
| `outputColumn` | yes | `string<column_name>` | Any valid output column name | Column containing converted amount. |
| `outputCurrency` | yes | `string<currency_code>` | See `Supported Currency Codes` below | Target currency. |
| `isCurrencyFromColumn` | yes | `boolean` | `true` \| `false` | `true` uses per-row source currency from `refCurrencyColumn`; `false` uses fixed `inputCurrency`. |
| `inputCurrency` | yes | `string<currency_code>` | See `Supported Currency Codes` below | Fixed source currency when `isCurrencyFromColumn=false` (still present in live payloads when true). |
| `refCurrencyColumn` | conditional | `string<column_name>` | Any valid currency-code column name | Required when `isCurrencyFromColumn=true`. |
| `dateInput` | yes | `enum` | `LATEST` \| `COLUMN` \| `CUSTOM` | Exchange-rate reference date mode. |
| `refDateColumn` | conditional | `string<column_name>` | Any valid date column name | Required when `dateInput=COLUMN`; may appear in `CUSTOM` payloads. |
| `refDateCustom` | conditional | `string<date>` | Date string in `YYYY-MM-DD` format | Required when `dateInput=CUSTOM`. |
| `decimalNumber` | yes | `integer` | Any integer `>= 0` | Decimal precision for converted amounts. |

## Supported Currency Codes

- `AED` (United Arab Emirates Dirham)
- `AUD` (Australian Dollar)
- `BGN` (Bulgarian Lev)
- `BND` (Brunei Dollar)
- `BRL` (Brazilian Real)
- `BWP` (Botswana Pula)
- `CAD` (Canadian Dollar)
- `CHF` (Swiss Franc)
- `CLP` (Chilean Peso)
- `CNY` (Chinese Yuan)
- `CYP` (Cypriot Pound)
- `CZK` (Czech Koruna)
- `DKK` (Danish Krone)
- `DZD` (Algerian Dinar)
- `EEK` (Estonian Kroon)
- `EUR` (Euro)
- `GBP` (British Pound Sterling)
- `HKD` (Hong Kong Dollar)
- `HRK` (Croatian Kuna)
- `HUF` (Hungarian Forint)
- `IDR` (Indonesian Rupiah)
- `ILS` (Israeli Shekel)
- `INR` (Indian Rupee)
- `ISK` (Icelandic Krona)
- `JPY` (Japanese Yen)
- `KRW` (South Korean Won)
- `KWD` (Kuwaiti Dinar)
- `LTL` (Lithuanian Litas)
- `LVL` (Latvian Lats)
- `MTL` (Maltese Lira)
- `MUR` (Mauritian Rupee)
- `MXN` (Mexican Peso)
- `MYR` (Malaysian Ringgit)
- `NOK` (Norwegian Krone)
- `NZD` (New Zealand Dollar)
- `OMR` (Omani Rial)
- `PEN` (Peruvian Sol)
- `PHP` (Philippine Peso)
- `PLN` (Polish Zloty)
- `QAR` (Qatari Riyal)
- `ROL` (Romanian Leu (Old))
- `RON` (Romanian Leu (New))
- `RUB` (Russian Ruble)
- `SAR` (Saudi Riyal)
- `SEK` (Swedish Krona)
- `SGD` (Singapore Dollar)
- `SIT` (Slovenian Tolar)
- `SKK` (Slovak Koruna)
- `THB` (Thai Baht)
- `TRL` (Turkish Lira (Old))
- `TRY` (Turkish Lira (New))
- `TTD` (Trinidad and Tobago Dollar)
- `USD` (United States Dollar)
- `UYU` (Uruguayan Peso)
- `ZAR` (South African Rand)

## Canonical Variants

### Fixed source currency with latest known rates

```json
{
  "type": "CurrencyConverterProcessor",
  "params": {
    "outputCurrency": "EUR",
    "inputCurrency": "USD",
    "isCurrencyFromColumn": false,
    "outputColumn": "score_euros",
    "decimalNumber": 2,
    "inputColumn": "score",
    "dateInput": "LATEST"
  }
}
```

### Fixed source currency with rate date from column

```json
{
  "type": "CurrencyConverterProcessor",
  "params": {
    "outputCurrency": "DKK",
    "inputCurrency": "CAD",
    "isCurrencyFromColumn": false,
    "outputColumn": "score_dkk",
    "decimalNumber": 2,
    "refDateColumn": "signup_date",
    "inputColumn": "score",
    "dateInput": "COLUMN"
  }
}
```

### Source currency from column with custom reference date

```json
{
  "type": "CurrencyConverterProcessor",
  "params": {
    "outputCurrency": "BRL",
    "refCurrencyColumn": "currency",
    "inputCurrency": "BRL",
    "isCurrencyFromColumn": true,
    "outputColumn": "score_brl",
    "decimalNumber": 2,
    "refDateCustom": "2025-12-31",
    "refDateColumn": "signup_date",
    "inputColumn": "score",
    "dateInput": "CUSTOM"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `CurrencyConverterProcessor`.
3. Keep source-currency settings coherent: use `inputCurrency` for fixed mode, `refCurrencyColumn` for per-row mode.
4. Keep date settings coherent with `dateInput` (`LATEST`, `COLUMN`, or `CUSTOM`).
5. Verify `decimalNumber` matches downstream precision expectations.

## References

- Dataiku DSS: Convert currencies (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/currency-converter.html
