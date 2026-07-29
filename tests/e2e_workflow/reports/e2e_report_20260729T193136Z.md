# AI Analytics Copilot — End-to-End Workflow Test Report

**Generated (UTC):** 2026-07-29T19:31:36.622188+00:00
**API:** `http://127.0.0.1:8000`
**User:** `e2e-tester`
**Readiness score:** **6.5 / 10**

## 1. Test Summary

| Metric | Value |
|--------|-------|
| Total tests | 33 |
| Passed | 29 |
| Failed | 4 |
| Pass rate | 87.9% |
| Local pass rate | 100.0% |
| Remote graceful pass rate | 100.0% |
| Remote full pipeline rate | 0.0% |
| Cache pass rate | 0.0% |
| Error handling pass rate | 100.0% |

### Health
```json
{
  "root": {
    "status_code": 200,
    "body": "{\"message\":\"AI Analyst Backend Running\"}"
  },
  "llm": {
    "status_code": 200,
    "body": {
      "ollama_installed": true,
      "ollama_running": true,
      "model_available": true,
      "configured_model": "qwen3:4b",
      "installed_models": [
        "qwen3:4b"
      ]
    }
  }
}
```

### Cache stats (before → after)
```json
{
  "before": {
    "exists": true,
    "tables": [
      "session_memory",
      "learned_datasets",
      "dataset_registry",
      "analysis_sessions",
      "session_messages",
      "session_artifacts",
      "analysis_cache",
      "session_fts",
      "session_fts_data",
      "session_fts_idx",
      "session_fts_content",
      "session_fts_docsize",
      "session_fts_config",
      "dataset_memory",
      "graph_checkpoints",
      "graph_checkpoint_writes",
      "users"
    ],
    "analysis_cache_rows": 30,
    "analysis_cache_total_hits": 3,
    "analysis_cache_avg_hits": 0.1,
    "sessions": 40,
    "messages": 43,
    "count_learned_datasets": 1,
    "count_dataset_registry": 0,
    "count_dataset_memory": 8
  },
  "after": {
    "exists": true,
    "tables": [
      "session_memory",
      "learned_datasets",
      "dataset_registry",
      "analysis_sessions",
      "session_messages",
      "session_artifacts",
      "analysis_cache",
      "session_fts",
      "session_fts_data",
      "session_fts_idx",
      "session_fts_content",
      "session_fts_docsize",
      "session_fts_config",
      "dataset_memory",
      "graph_checkpoints",
      "graph_checkpoint_writes",
      "users"
    ],
    "analysis_cache_rows": 81,
    "analysis_cache_total_hits": 3,
    "analysis_cache_avg_hits": 0.037,
    "sessions": 77,
    "messages": 117,
    "count_learned_datasets": 1,
    "count_dataset_registry": 2,
    "count_dataset_memory": 31
  }
}
```

## 2. Results by query

| ID | Cat | Pass | ms | Charts | Forecast | Insights | Source | Dataset |
|----|-----|------|----|--------|----------|----------|--------|---------|
| L01 | local | PASS | 1383 | 1 | False | False | local_file | user provided dataset |
| L02 | local | PASS | 705 | 1 | False | False | local_file | user provided dataset |
| L03 | local | PASS | 587 | 1 | False | False | local_file | user provided dataset |
| L04 | local | PASS | 675 | 1 | False | False | local_file | user provided dataset |
| L05 | local | PASS | 2499 | 1 | False | False | local_file | user provided dataset |
| L06 | local | PASS | 98514 | 0 | False | False | local_file | user provided dataset |
| L07 | local | PASS | 984 | 1 | False | False | local_file | user provided dataset |
| L08 | local | PASS | 1409 | 1 | False | False | local_file | user provided dataset |
| L09 | local | PASS | 104202 | 0 | True | False | local_file | user provided dataset |
| L10 | local | PASS | 93701 | 0 | True | False | local_file | user provided dataset |
| L11 | local | PASS | 90094 | 0 | True | False | local_file | user provided dataset |
| L12 | local | PASS | 850 | 1 | False | False | local_file | user provided dataset |
| L13 | local | PASS | 1007 | 1 | False | False | local_file | user provided dataset |
| L14 | local | PASS | 946 | 1 | False | False | local_file | user provided dataset |
| L15 | local | PASS | 1084 | 1 | False | False | local_file | user provided dataset |
| R01 | remote | PASS | 28513 | 0 | False | False | needs_user_data | electric vehicle sales world |
| R02 | remote | PASS | 6368 | 0 | False | False | needs_user_data | global co2 emissions time |
| R03 | remote | PASS | 6398 | 0 | False | False | needs_user_data | renewable energy production  |
| R04 | remote | PASS | 11179 | 0 | False | False | needs_user_data | world happiness index scores |
| R05 | remote | PASS | 7600 | 0 | False | False | needs_user_data | air quality index major citi |
| R06 | remote | PASS | 5718 | 0 | False | False | needs_user_data | inflation global |
| R07 | remote | PASS | 12469 | 0 | False | False | needs_user_data | bitcoin cryptocurrency |
| R08 | remote | PASS | 7793 | 0 | False | False | needs_user_data | olympic medal counts by coun |
| R09 | remote | PASS | 6862 | 0 | False | False | needs_user_data | global internet usage statis |
| R10 | remote | PASS | 7516 | 0 | False | False | needs_user_data | international tourism arriva |
| C01 | cache | FAIL | 553 | 1 | False | False | local_file | user provided dataset |
| C02 | cache | FAIL | 536 | 1 | False | False | local_file | user provided dataset |
| C03 | cache | FAIL | 534 | 1 | False | False | local_file | user provided dataset |
| C04 | cache | FAIL | 75544 | 0 | True | False | local_file | user provided dataset |
| E01 | error | PASS | 2425 | 0 | False | False | n/a | - |
| E02 | error | PASS | 2272 | 0 | False | False | n/a | - |
| E03 | error | PASS | 1096 | 0 | False | False | n/a | - |
| E04 | error | PASS | 10980 | 0 | False | False | n/a | - |

## 3. Detailed results

### L01 — local — PASS

- **Query:** Show monthly rainfall trends for Seattle weather
- **Session:** `e2e-local-L01-3e0c61d4`
- **HTTP:** 200
- **Time:** 1382.9 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\seattle_weather.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 6
- **Cache run:** cold
- **Answer preview:** Analyzed user provided dataset (120 rows, 5 columns). Charts were generated to illustrate the key trends. The line chart for Rainfall_in shows a relatively stable trend over time. Time series structure detected (Year with numeric measures) 
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'Show monthly rainfall trends for Seattle weather', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L02 — local — PASS

- **Query:** Analyze temperature trends in Seattle weather dataset
- **Session:** `e2e-local-L02-e3163831`
- **HTTP:** 200
- **Time:** 705.3 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\seattle_weather.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 4 | **Suggestions:** 6
- **Cache run:** cold
- **Answer preview:** Analyzed user provided dataset (120 rows, 5 columns). No missing values detected in the prepared frame. Average Year is 2019.5. Average Rainfall_in is 3.26. Patterns: High correlation detected between 'Rainfall_in' and 'Temp_F' (-0.93).; Hi
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'Analyze temperature trends in Seattle weather dataset', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L03 — local — PASS

- **Query:** Visualize wind distribution in Seattle weather
- **Session:** `e2e-local-L03-8a36efed`
- **HTTP:** 200
- **Time:** 587.0 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\seattle_weather.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 6
- **Cache run:** cold
- **Answer preview:** Analyzed user provided dataset (120 rows, 5 columns). Charts were generated to illustrate the key trends. The distribution is approximately symmetric. Time series structure detected (Year with numeric measures) — forecasting is available. S
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'Visualize wind distribution in Seattle weather', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L04 — local — PASS

- **Query:** Show population growth over years
- **Session:** `e2e-local-L04-b7e57367`
- **HTTP:** 200
- **Time:** 675.3 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\world_population.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 4 | **Suggestions:** 6
- **Cache run:** cold
- **Answer preview:** Analyzed user provided dataset (300 rows, 3 columns). No missing values detected in the prepared frame. Average Year is 2012.0. Average Population is 373866980.89. Patterns: Outliers detected in 'Population' with 50 extreme values.; Skewed 
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'Show population growth over years', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L05 — local — PASS

- **Query:** Compare population of India and China
- **Session:** `e2e-local-L05-097e805f`
- **HTTP:** 200
- **Time:** 2498.8 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\world_population.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 5
- **Cache run:** cold
- **Answer preview:** Compared POPULATION for India and China from 1960 to 2024. Latest (2024): China=1,408,975,000; India=1,450,935,791. A line chart of the trend is included. Suggested next steps: Forecast India for the next 10 years; Show the long-term trend 
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'Compare population of India and China', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L06 — local — PASS

- **Query:** What are the top 10 most populated countries in the latest year
- **Session:** `e2e-local-L06-4fd4744c`
- **HTTP:** 200
- **Time:** 98514.0 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\world_population.csv`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 5
- **Cache run:** cold
- **Answer preview:** Based on your dataset (300 rows, clean), the top 10 most populated countries in the latest year (2023) are: China, India, USA, Indonesia, Pakistan, Brazil, Nigeria, Bangladesh, Russia, and Japan.    **Key insights**: China and India dominat
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": false, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** No charts returned; session_meta={'message_count': 2, 'title': 'What are the top 10 most populated countries in the latest year', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L07 — local — PASS

- **Query:** Analyze India's GDP trend over time
- **Session:** `e2e-local-L07-2a659ee1`
- **HTTP:** 200
- **Time:** 984.5 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\india_gdp.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 4 | **Suggestions:** 6
- **Cache run:** cold
- **Answer preview:** Analyzed user provided dataset focused on India (25 rows, 3 columns). No missing values detected in the prepared frame. Average Year is 2012.0. Average GDP is 1780000000000.0. Patterns: Strong upward trend detected in 'GDP' over 'Year'.; Hi
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': "Analyze India's GDP trend over time", 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L08 — local — PASS

- **Query:** Compare GDP of India with United States
- **Session:** `e2e-local-L08-0ef50d81`
- **HTTP:** 200
- **Time:** 1409.2 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\world_gdp.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 6
- **Cache run:** cold
- **Answer preview:** Compared GDP for United States and India from 1960 to 2023. Latest (2023): India=3,549,918,918,778; United States=27,360,935,000,000. A line chart of the trend is included. Suggested next steps: Forecast United States for the next 10 years;
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'Compare GDP of India with United States', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L09 — local — PASS

- **Query:** Forecast India's GDP for next 5 years
- **Session:** `e2e-local-L09-42ea163d`
- **HTTP:** 200
- **Time:** 104202.2 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\india_gdp.csv`
- **Charts:** 0 | **Forecast:** True | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 6
- **Cache run:** cold
- **Answer preview:** **Executive Response**    1) **What the data shows**: Historical GDP for India (25 years) shows steady growth with a clear upward trend.    2) **Key insights**: Strong long-term growth trajectory, but the dataset covers only 25 years—insuff
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": false, "charts_strict": false, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** No charts returned; session_meta={'message_count': 2, 'title': "Forecast India's GDP for next 5 years", 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L10 — local — PASS

- **Query:** Analyze oil price trends and forecast next 5 years
- **Session:** `e2e-local-L10-30e828e0`
- **HTTP:** 200
- **Time:** 93701.2 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\oil_prices.csv`
- **Charts:** 0 | **Forecast:** True | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 4
- **Cache run:** cold
- **Answer preview:** **Executive Response**    1) **What the data shows**: Oil prices show a steady upward trend over 25 years (2000–2024), with minimal volatility.    2) **Key insights**: Short-term stability exists, but the dataset lacks historical context be
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": false, "charts_strict": false, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** No charts returned; session_meta={'message_count': 2, 'title': 'Analyze oil price trends and forecast next 5 years', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L11 — local — PASS

- **Query:** Show gold price trend and forecast next 3 years
- **Session:** `e2e-local-L11-50eae298`
- **HTTP:** 200
- **Time:** 90093.5 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\gold_prices.csv`
- **Charts:** 0 | **Forecast:** True | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 5
- **Cache run:** cold
- **Answer preview:** Based on your 25-row gold price dataset (Date, Year, Price), we observe a clear upward trend over the past few years with moderate volatility. However, the dataset is too small (only 25 data points) to reliably forecast beyond 1–2 years wit
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": false, "charts_strict": false, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** No charts returned; session_meta={'message_count': 2, 'title': 'Show gold price trend and forecast next 3 years', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L12 — local — PASS

- **Query:** EDA on India rainfall and visualize yearly pattern
- **Session:** `e2e-local-L12-cb58c9aa`
- **HTTP:** 200
- **Time:** 850.2 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\india_rainfall.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 3 | **Suggestions:** 5
- **Cache run:** cold
- **Answer preview:** Analyzed user provided dataset (25 rows, 2 columns). No missing values detected in the prepared frame. Average Year is 2012.0. Average Rainfall_mm is 948.4. Hypothesis: Consider comparing Year before and after the median Year to evaluate sh
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'EDA on India rainfall and visualize yearly pattern', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L13 — local — PASS

- **Query:** Analyze salary by department and show a chart
- **Session:** `e2e-local-L13-4d6f8767`
- **HTTP:** 200
- **Time:** 1007.4 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\employees.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 3 | **Suggestions:** 4
- **Cache run:** cold
- **Answer preview:** Analyzed user provided dataset (8 rows, 4 columns). No missing values detected in the prepared frame. Average Salary is 97875.0. Average Years is 4.25. Hypothesis: Validate whether Salary and Years maintain a consistent correlation across d
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'Analyze salary by department and show a chart', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L14 — local — PASS

- **Query:** Analyze India inflation trends
- **Session:** `e2e-local-L14-d7127676`
- **HTTP:** 200
- **Time:** 945.5 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\india_inflation.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 4 | **Suggestions:** 5
- **Cache run:** cold
- **Answer preview:** Analyzed user provided dataset focused on India (25 rows, 3 columns). No missing values detected in the prepared frame. Average Year is 2012.0. Average Inflation is 4.3. Hypothesis: Consider comparing Year before and after the median Year t
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'Analyze India inflation trends', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### L15 — local — PASS

- **Query:** Visualize India unemployment over years
- **Session:** `e2e-local-L15-875cf1c5`
- **HTTP:** 200
- **Time:** 1083.7 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\india_unemployment.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 4 | **Suggestions:** 5
- **Cache run:** cold
- **Answer preview:** Analyzed user provided dataset focused on India (25 rows, 3 columns). No missing values detected in the prepared frame. Average Year is 2012.0. Average Unemployment is 5.6. Hypothesis: Consider comparing Year before and after the median Yea
- **Error:** —
- **Checks:** `{"http_200": true, "has_answer": true, "has_charts": true, "charts_strict": true, "forecast_if_asked": true, "session_persisted": true, "no_crash": true, "dataset_loaded": true}`
- **Notes:** session_meta={'message_count': 2, 'title': 'Visualize India unemployment over years', 'dataset_name': 'user provided dataset', 'has_artifacts': True}

### R01 — remote — PASS

- **Query:** Analyze electric vehicle sales worldwide and show trends
- **Session:** `e2e-remote-R01-2b1d6916`
- **HTTP:** 200
- **Time:** 28512.8 ms
- **Dataset:** electric vehicle sales worldwide
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=vehicle+sales+electric+worldwide Suggested next steps: Upload a CSV/Excel file; Paste a direct .c
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=vehicle+sales+electric+worldwide
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze electric vehicle sales worldwide and show trends', 'dataset_name': 'electric vehicle sales worldwide', 'has_artifacts': True}; discovery={}

### R02 — remote — PASS

- **Query:** Analyze global CO2 emissions over time and visualize
- **Session:** `e2e-remote-R02-551c6932`
- **HTTP:** 200
- **Time:** 6367.7 ms
- **Dataset:** global co2 emissions time
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=global+emissions+co2+time Suggested next steps: Upload a CSV/Excel file; Paste a direct .csv / .j
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=global+emissions+co2+time
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze global CO2 emissions over time and visualize', 'dataset_name': 'global co2 emissions time', 'has_artifacts': True}; discovery={}

### R03 — remote — PASS

- **Query:** Analyze renewable energy production by country
- **Session:** `e2e-remote-R03-6d0d28ae`
- **HTTP:** 200
- **Time:** 6398.2 ms
- **Dataset:** renewable energy production by country
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=country+energy+production+renewable Suggested next steps: Upload a CSV/Excel file; Paste a direct
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=country+energy+production+renewable
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze renewable energy production by country', 'dataset_name': 'renewable energy production by country', 'has_artifacts': True}; discovery={}

### R04 — remote — PASS

- **Query:** Analyze World Happiness Index scores
- **Session:** `e2e-remote-R04-85d52958`
- **HTTP:** 200
- **Time:** 11179.4 ms
- **Dataset:** world happiness index scores
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=index+world+scores+happiness Suggested next steps: Upload a CSV/Excel file; Paste a direct .csv /
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=index+world+scores+happiness
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze World Happiness Index scores', 'dataset_name': 'world happiness index scores', 'has_artifacts': True}; discovery={}

### R05 — remote — PASS

- **Query:** Analyze Air Quality Index trends for major cities
- **Session:** `e2e-remote-R05-e76f74e5`
- **HTTP:** 200
- **Time:** 7600.3 ms
- **Dataset:** air quality index major cities
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=major+cities+index+quality+air Suggested next steps: Upload a CSV/Excel file; Paste a direct .csv
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=major+cities+index+quality+air
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze Air Quality Index trends for major cities', 'dataset_name': 'air quality index major cities', 'has_artifacts': True}; discovery={}

### R06 — remote — PASS

- **Query:** Analyze global inflation rates
- **Session:** `e2e-remote-R06-2687d2d6`
- **HTTP:** 200
- **Time:** 5717.9 ms
- **Dataset:** inflation global
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 404 for https://raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv Suggested next steps: Upload a CSV/Excel file; Paste a direct .
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 404 for https://raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze global inflation rates', 'dataset_name': 'inflation global', 'has_artifacts': True}; discovery={}

### R07 — remote — PASS

- **Query:** Analyze cryptocurrency prices for Bitcoin
- **Session:** `e2e-remote-R07-216177f9`
- **HTTP:** 200
- **Time:** 12469.3 ms
- **Dataset:** bitcoin cryptocurrency
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=cryptocurrency+bitcoin Suggested next steps: Upload a CSV/Excel file; Paste a direct .csv / .json
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=cryptocurrency+bitcoin
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze cryptocurrency prices for Bitcoin', 'dataset_name': 'bitcoin cryptocurrency', 'has_artifacts': True}; discovery={}

### R08 — remote — PASS

- **Query:** Analyze Olympic medal counts by country
- **Session:** `e2e-remote-R08-748d2ab2`
- **HTTP:** 200
- **Time:** 7792.9 ms
- **Dataset:** olympic medal counts by country
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=counts+country+olympic+medal Suggested next steps: Upload a CSV/Excel file; Paste a direct .csv /
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=counts+country+olympic+medal
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze Olympic medal counts by country', 'dataset_name': 'olympic medal counts by country', 'has_artifacts': True}; discovery={}

### R09 — remote — PASS

- **Query:** Analyze global internet usage statistics
- **Session:** `e2e-remote-R09-f2551788`
- **HTTP:** 200
- **Time:** 6862.2 ms
- **Dataset:** global internet usage statistics
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=internet+global+usage+statistics Suggested next steps: Upload a CSV/Excel file; Paste a direct .c
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=internet+global+usage+statistics
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze global internet usage statistics', 'dataset_name': 'global internet usage statistics', 'has_artifacts': True}; discovery={}

### R10 — remote — PASS

- **Query:** Analyze international tourism arrivals
- **Session:** `e2e-remote-R10-0bc4c546`
- **HTTP:** 200
- **Time:** 7516.5 ms
- **Dataset:** international tourism arrivals
- **Retrieval source:** needs_user_data
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 3
- **Cache run:** cold
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=tourism+international+arrivals Suggested next steps: Upload a CSV/Excel file; Paste a direct .csv
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=tourism+international+arrivals
- **Checks:** `{"http_200": true, "no_crash": true, "session_persisted": true, "retrieval_or_graceful": true, "dataset_discovered": false, "charts_or_graceful": true, "full_pipeline": false}`
- **Notes:** Partial pipeline: full download→EDA→chart path not confirmed; session_meta={'message_count': 2, 'title': 'Analyze international tourism arrivals', 'dataset_name': 'international tourism arrivals', 'has_artifacts': True}; discovery={}

### C01 — cache — FAIL

- **Query:** Analyze India's GDP trend over time
- **Session:** `e2e-cache-warm-C01-108225`
- **HTTP:** 200
- **Time:** 553.0 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\india_gdp.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 0
- **Cache run:** warm
- **Answer preview:** cold=555ms warm=553ms speedup=1.00x | Analyzed user provided dataset focused on India (25 rows, 3 columns). No missing values detected in the prepared frame. 
- **Error:** —
- **Checks:** `{"cold_ok": false, "warm_ok": false, "warm_not_slower_5x": true, "both_have_output": true}`
- **Notes:** cold_ms=555.0; warm_ms=553.0; speedup=1.004; cold_charts=1 warm_charts=1

### C02 — cache — FAIL

- **Query:** Show monthly rainfall trends for Seattle weather
- **Session:** `e2e-cache-warm-C02-d23a63`
- **HTTP:** 200
- **Time:** 536.2 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\seattle_weather.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 0
- **Cache run:** warm
- **Answer preview:** cold=496ms warm=536ms speedup=0.92x | Analyzed user provided dataset (120 rows, 5 columns). Charts were generated to illustrate the key trends. The line chart
- **Error:** —
- **Checks:** `{"cold_ok": false, "warm_ok": false, "warm_not_slower_5x": true, "both_have_output": true}`
- **Notes:** cold_ms=495.6; warm_ms=536.2; speedup=0.924; cold_charts=1 warm_charts=1

### C03 — cache — FAIL

- **Query:** Show population growth over years
- **Session:** `e2e-cache-warm-C03-db5889`
- **HTTP:** 200
- **Time:** 533.7 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\world_population.csv`
- **Charts:** 1 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 0
- **Cache run:** warm
- **Answer preview:** cold=538ms warm=534ms speedup=1.01x | Analyzed user provided dataset (300 rows, 3 columns). No missing values detected in the prepared frame. Average Year is 
- **Error:** —
- **Checks:** `{"cold_ok": false, "warm_ok": false, "warm_not_slower_5x": true, "both_have_output": true}`
- **Notes:** cold_ms=537.7; warm_ms=533.7; speedup=1.007; cold_charts=1 warm_charts=1

### C04 — cache — FAIL

- **Query:** Analyze oil price trends and forecast next 5 years
- **Session:** `e2e-cache-warm-C04-329e54`
- **HTTP:** 200
- **Time:** 75543.9 ms
- **Dataset:** user provided dataset
- **Retrieval source:** local_file
- **File path:** `C:\Users\abhis\projects\AI-Analyst-Agent\data\local_library\oil_prices.csv`
- **Charts:** 0 | **Forecast:** True | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 0
- **Cache run:** warm
- **Answer preview:** cold=78374ms warm=75544ms speedup=1.04x | **Executive Response**    1) **What the data shows**: Historical oil prices (25 data points) show a clear upward trend s
- **Error:** —
- **Checks:** `{"cold_ok": false, "warm_ok": false, "warm_not_slower_5x": true, "both_have_output": false}`
- **Notes:** cold_ms=78374.4; warm_ms=75543.9; speedup=1.037; cold_charts=0 warm_charts=0

### E01 — error — PASS

- **Query:** Analyze GDP of Atlantis
- **Session:** `e2e-err-E01-c8fb88a6`
- **HTTP:** 200
- **Time:** 2424.7 ms
- **Dataset:** —
- **Retrieval source:** n/a
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 0
- **Cache run:** 
- **Answer preview:** Analyzed gdp atlantis (13979 rows, 4 columns). No missing values detected in the prepared frame. Average Year is 1994.67. Average Value is 1207379525661.76. Patterns: Outliers detected in 'Value' with 2311 extreme values.; Skewed distributi
- **Error:** —
- **Checks:** `{"no_crash": true, "responded": true, "helpful_message": true, "not_500": true}`
- **Notes:** keys=['answer', 'artifact_ids', 'chart', 'chart_columns_used', 'chart_error', 'chart_explanation', 'charts', 'checkpoint_id', 'checkpoint_saved', 'columns', 'data_acquisition_options', 'dataset_discovery', 'dataset_explanation', 'dataset_learned', 'dataset_summary', 'dataset_topic', 'dataset_url', 'detected_patterns', 'error', 'error_type', 'forecast', 'forecast_chart', 'forecast_error', 'generated_charts', 'hypotheses', 'insights', 'learned_aliases', 'memory_hierarchy_loaded', 'message_id', 'needs_user_data', 'product_promise', 'question', 'recommended_next_steps', 'related_datasets', 'rows', 'search_queries', 'session_id', 'source', 'topic_via_llm', 'user_id']

### E02 — error — PASS

- **Query:** Analyze Unicorn Population worldwide
- **Session:** `e2e-err-E02-526ef20c`
- **HTTP:** 200
- **Time:** 2271.9 ms
- **Dataset:** —
- **Retrieval source:** n/a
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 0
- **Cache run:** 
- **Answer preview:** Analyzed population unicorn worldwide (17195 rows, 4 columns). No missing values detected in the prepared frame. Average Year is 1992.03. Average Value is 218237897.36. Patterns: Outliers detected in 'Value' with 3296 extreme values.; Skewe
- **Error:** —
- **Checks:** `{"no_crash": true, "responded": true, "helpful_message": true, "not_500": true}`
- **Notes:** keys=['answer', 'artifact_ids', 'chart', 'chart_columns_used', 'chart_error', 'chart_explanation', 'charts', 'checkpoint_id', 'checkpoint_saved', 'columns', 'data_acquisition_options', 'dataset_discovery', 'dataset_explanation', 'dataset_learned', 'dataset_summary', 'dataset_topic', 'dataset_url', 'detected_patterns', 'error', 'error_type', 'forecast', 'forecast_chart', 'forecast_error', 'generated_charts', 'hypotheses', 'insights', 'learned_aliases', 'memory_hierarchy_loaded', 'message_id', 'needs_user_data', 'product_promise', 'question', 'recommended_next_steps', 'related_datasets', 'rows', 'search_queries', 'session_id', 'source', 'topic_via_llm', 'user_id']

### E03 — error — PASS

- **Query:** Analyze Dragon Population trends
- **Session:** `e2e-err-E03-c0a75501`
- **HTTP:** 200
- **Time:** 1095.7 ms
- **Dataset:** —
- **Retrieval source:** n/a
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 0
- **Cache run:** 
- **Answer preview:** Analyzed population dragon (17195 rows, 4 columns). No missing values detected in the prepared frame. Average Year is 1992.03. Average Value is 218237897.36. Patterns: Outliers detected in 'Value' with 3296 extreme values.; Skewed distribut
- **Error:** —
- **Checks:** `{"no_crash": true, "responded": true, "helpful_message": true, "not_500": true}`
- **Notes:** keys=['answer', 'artifact_ids', 'chart', 'chart_columns_used', 'chart_error', 'chart_explanation', 'charts', 'checkpoint_id', 'checkpoint_saved', 'columns', 'data_acquisition_options', 'dataset_discovery', 'dataset_explanation', 'dataset_learned', 'dataset_summary', 'dataset_topic', 'dataset_url', 'detected_patterns', 'error', 'error_type', 'forecast', 'forecast_chart', 'forecast_error', 'generated_charts', 'hypotheses', 'insights', 'learned_aliases', 'memory_hierarchy_loaded', 'message_id', 'needs_user_data', 'product_promise', 'question', 'recommended_next_steps', 'related_datasets', 'rows', 'search_queries', 'session_id', 'source', 'topic_via_llm', 'user_id']

### E04 — error — PASS

- **Query:** Analyze XYZABC123 dataset completely
- **Session:** `e2e-err-E04-2e96c042`
- **HTTP:** 200
- **Time:** 10980.4 ms
- **Dataset:** —
- **Retrieval source:** n/a
- **File path:** `—`
- **Charts:** 0 | **Forecast:** False | **Insights:** False
- **Hypotheses:** 0 | **Suggestions:** 0
- **Cache run:** 
- **Answer preview:** Dataset download/acquisition failed: Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=completely+xyzabc123 Suggested next steps: Upload a CSV/Excel file; Paste a direct .csv / .json U
- **Error:** Download failed: Failed to download after 3 attempts: HTTP 403 for https://data.oecd.org/searchresults/?q=completely+xyzabc123
- **Checks:** `{"no_crash": true, "responded": true, "helpful_message": true, "not_500": true}`
- **Notes:** keys=['answer', 'artifact_ids', 'chart', 'chart_columns_used', 'chart_error', 'chart_explanation', 'charts', 'checkpoint_id', 'checkpoint_saved', 'columns', 'data_acquisition_options', 'dataset_discovery', 'dataset_explanation', 'dataset_learned', 'dataset_summary', 'dataset_topic', 'dataset_url', 'detected_patterns', 'error', 'error_type', 'forecast', 'forecast_chart', 'forecast_error', 'generated_charts', 'hypotheses', 'insights', 'learned_aliases', 'memory_hierarchy_loaded', 'message_id', 'needs_user_data', 'product_promise', 'question', 'recommended_next_steps', 'related_datasets', 'rows', 'search_queries', 'session_id', 'source', 'topic_via_llm', 'user_id']

## 4. Performance

- Local avg: 26576 ms (n=15)
- Local min/max: 587 / 104202 ms
- Remote avg: 10042 ms (n=10)
- Remote min/max: 5718 / 28513 ms

### Cache cold vs warm

- C01: cold_ms=555.0; warm_ms=553.0; speedup=1.004; cold_charts=1 warm_charts=1 pass=False
- C02: cold_ms=495.6; warm_ms=536.2; speedup=0.924; cold_charts=1 warm_charts=1 pass=False
- C03: cold_ms=537.7; warm_ms=533.7; speedup=1.007; cold_charts=1 warm_charts=1 pass=False
- C04: cold_ms=78374.4; warm_ms=75543.9; speedup=1.037; cold_charts=0 warm_charts=0 pass=False

## 5. Bugs discovered

- **C01** (cache): HTTP 200, error=``, checks={'cold_ok': False, 'warm_ok': False, 'warm_not_slower_5x': True, 'both_have_output': True}, preview=cold=555ms warm=553ms speedup=1.00x | Analyzed user provided dataset focused on India (25 rows, 3 co
- **C02** (cache): HTTP 200, error=``, checks={'cold_ok': False, 'warm_ok': False, 'warm_not_slower_5x': True, 'both_have_output': True}, preview=cold=496ms warm=536ms speedup=0.92x | Analyzed user provided dataset (120 rows, 5 columns). Charts w
- **C03** (cache): HTTP 200, error=``, checks={'cold_ok': False, 'warm_ok': False, 'warm_not_slower_5x': True, 'both_have_output': True}, preview=cold=538ms warm=534ms speedup=1.01x | Analyzed user provided dataset (300 rows, 3 columns). No missi
- **C04** (cache): HTTP 200, error=``, checks={'cold_ok': False, 'warm_ok': False, 'warm_not_slower_5x': True, 'both_have_output': False}, preview=cold=78374ms warm=75544ms speedup=1.04x | **Executive Response**    1) **What the data shows**: Hist

## 6. Root cause analysis

Failures typically fall into:
1. **Remote discovery gaps** — open-data search cannot find a clean downloadable CSV for niche topics.
2. **LLM latency / timeouts** — planner or agents exceed client timeout under load.
3. **Partial pipelines** — answer returned without charts/forecast when viz agent skipped.
4. **Cache timing variance** — warm path may still re-run LLM for natural language wrapping.

## 7. Recommended fixes

1. Strengthen dataset search ranking and known-source catalogs for common topics (EV, tourism, AQI).
2. Persist and surface stage-level timings (planner, retrieve, eda, viz, forecast) in `/v1/ask` response meta.
3. Ensure analysis cache short-circuits full graph on identical fingerprint+question.
4. For fictional topics, return a structured `not_found` discovery status with acquisition options (already partial).
5. Add registry dedupe checks after remote download.

## 8. Overall readiness: **6.5/10**

{
  "local_pass_rate": 1.0,
  "remote_graceful_pass_rate": 1.0,
  "remote_full_pipeline_rate": 0.0,
  "cache_pass_rate": 0.0,
  "error_pass_rate": 1.0,
  "cache_stats": {
    "exists": true,
    "tables": [
      "session_memory",
      "learned_datasets",
      "dataset_registry",
      "analysis_sessions",
      "session_messages",
      "session_artifacts",
      "analysis_cache",
      "session_fts",
      "session_fts_data",
      "session_fts_idx",
      "session_fts_content",
      "session_fts_docsize",
      "session_fts_config",
      "dataset_memory",
      "graph_checkpoints",
      "graph_checkpoint_writes",
      "users"
    ],
    "analysis_cache_rows": 81,
    "analysis_cache_total_hits": 3,
    "analysis_cache_avg_hits": 0.037,
    "sessions": 77,
    "messages": 117,
    "count_learned_datasets": 1,
    "count_dataset_registry": 2,
    "count_dataset_memory": 31
  }
}
