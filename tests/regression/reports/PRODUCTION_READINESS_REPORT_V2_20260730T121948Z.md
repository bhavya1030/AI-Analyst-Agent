# Production Readiness Report v2

**Generated:** 2026-07-30T12:19:48.958222+00:00  
**Duration:** 9.0 minutes  
**API:** `http://127.0.0.1:8000`  
**User:** `prod-cert-v2`  
**Suite:** Production Certification v2  

---

## Executive Recommendation

### **Not Ready for production deployment**

| Metric | Value |
|--------|------:|
| **Deployment Score** | **7.14 / 10** |
| Pass rate | 81.7% (147/180) |
| Average latency | 2653 ms |
| P50 latency | 207 ms |
| P95 latency | 15563 ms |
| Forecast success | 100.0% |
| Conversation continuity | 75.0% |
| Internet full success | 16.7% |
| Internet graceful | 16.7% |
| Charts success | 87.5% |
| Sessions success | 100.0% |
| Cache hit rate | 80.0% |
| Warm avg response | 480 ms |
| Concurrent pass rate | 100.0% |
| Artifacts rate | 58.3% |
| Peak process RSS | 332 MB |
| Avg process RSS | 61 MB |
| Avg CPU (sample) | 25.0% |

### System resources

```json
{
  "mem_percent": 86.6,
  "mem_used_mb": 13647.2,
  "cpu_percent": 37.4
}
```

### Volume targets

| Suite | Target | Actual | Met |
|-------|-------:|-------:|:---:|
| local | 50 | 50 | yes |
| internet | 30 | 30 | yes |
| forecast | 20 | 20 | yes |
| memory | 20 | 20 | yes |
| cache | 20 | 20 | yes |
| concurrent | 10 | 10 | yes |

### Category pass rates

| Category | Pass rate | Count |
|----------|----------:|------:|
| cache | 100.0% | 20 |
| charts | 87.5% | 8 |
| concurrent | 100.0% | 10 |
| error | 75.0% | 8 |
| forecast | 100.0% | 20 |
| internet | 16.7% | 30 |
| local | 100.0% | 50 |
| memory | 75.0% | 20 |
| registry | 100.0% | 6 |
| session | 100.0% | 8 |

### Stage average latency (ms)

```json
{
  "intent": 0.1,
  "session": 411.7,
  "cache": 8.9,
  "serialization": 33.7,
  "response": 93.3,
  "total": 1941.9,
  "planner": 2.1,
  "retrieval": 1333.9,
  "download": 1055.8,
  "validation": 187.0,
  "profiling": 78.8,
  "eda": 108.3,
  "visualization": 170.9,
  "forecast": 162.2,
  "insights": 0.0,
  "forecast_training": 7.0,
  "forecast_prediction": 10.8,
  "forecast_chart": 428.8,
  "_codec_version": 1.0,
  "_encoded": 1.0
}
```

### Live /performance snapshot (if available)

```json
{
  "error": "HTTPConnectionPool(host='127.0.0.1', port=8000): Read timed out. (read timeout=30)"
}
```

---

## Remaining blockers

- **BLOCKER:** Overall pass rate 81.7% < 85%
- **BLOCKER:** Conversation continuity 75.0% < 80%
- **BLOCKER:** Deployment readiness score 7.14/10 < 7.5

## Risk assessment

- **RISK:** Internet full-pipeline success 16.7% is low (graceful degradation may still pass)

### Risk matrix (qualitative)

| Area | Risk | Notes |
|------|------|-------|
| Internet providers | High | Full pipeline 17%; graceful 17% |
| Forecast engine | Low | Success 100%; latency 450ms |
| Cache warm path | Low | Hit 80%; warm avg 480ms |
| Sessions | Low | Pass 100% |
| Concurrency | Low | 10-user pass 100% |
| Resource | Low | Peak RSS 332MB |

---

## Failures (first 40)

- **MEM04** [memory] HTTP=500 checks=`{"http_200": false, "no_reupload": true, "session_ok": true, "has_answer": true}` notes=[] err=
- **MEM05** [memory] HTTP=500 checks=`{"http_200": false, "no_reupload": true, "session_ok": true, "has_answer": true}` notes=[] err=
- **MEM06** [memory] HTTP=200 checks=`{"http_200": true, "no_reupload": false, "session_ok": true, "has_answer": true}` notes=['REUPLOAD_REQUESTED'] err=
- **MEM19** [memory] HTTP=500 checks=`{"http_200": false, "no_reupload": true, "session_ok": true, "has_answer": true}` notes=[] err=
- **MEM20** [memory] HTTP=200 checks=`{"http_200": true, "no_reupload": false, "session_ok": true, "has_answer": true}` notes=['REUPLOAD_REQUESTED'] err=
- **CH03** [charts] HTTP=200 checks=`{"http_200": true, "has_chart_or_forecast": false}` notes=[] err=
- **ERR04** [error] HTTP=0 checks=`{"no_crash": false, "responded": false, "not_500": false, "helpful": true}` notes=[] err=
- **ERR08** [error] HTTP=500 checks=`{"no_crash": false, "responded": true, "not_500": false, "helpful": true}` notes=[] err=
- **NET06** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": true, "full_pipeline": false}` notes=['client_timeout', 'graceful'] err=HTTPConnectionPool(host='127.0.0.1', port=8000): Read timed out. (read timeout=40)
- **NET07** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": true, "full_pipeline": false}` notes=['client_timeout', 'graceful'] err=HTTPConnectionPool(host='127.0.0.1', port=8000): Read timed out. (read timeout=40)
- **NET08** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET09** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET10** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET11** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET12** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET13** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET14** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET15** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET16** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET17** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET18** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET19** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET20** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET21** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET22** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET23** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET24** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET25** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET26** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET27** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET28** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET29** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall
- **NET30** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=['cascade_skip', 'server_stall'] err=cascade_skip_after_api_stall

---

## Results table (compact)

| ID | Cat | Pass | ms | Charts | FC | Cache |
|----|-----|:----:|---:|-------:|:--:|:-----:|
| LOC01 | local | PASS | 339 | 1 | False | None |
| LOC02 | local | PASS | 188 | 1 | False | None |
| LOC03 | local | PASS | 224 | 1 | False | None |
| LOC04 | local | PASS | 186 | 1 | False | None |
| LOC05 | local | PASS | 188 | 1 | False | None |
| LOC06 | local | PASS | 161 | 0 | False | None |
| LOC07 | local | PASS | 201 | 1 | False | None |
| LOC08 | local | PASS | 197 | 1 | False | None |
| LOC09 | local | PASS | 184 | 1 | False | None |
| LOC10 | local | PASS | 207 | 1 | False | None |
| LOC11 | local | PASS | 197 | 1 | False | None |
| LOC12 | local | PASS | 187 | 1 | False | None |
| LOC13 | local | PASS | 165 | 1 | False | None |
| LOC14 | local | PASS | 198 | 1 | False | None |
| LOC15 | local | PASS | 230 | 1 | False | None |
| LOC16 | local | PASS | 183 | 0 | False | None |
| LOC17 | local | PASS | 187 | 1 | False | None |
| LOC18 | local | PASS | 189 | 1 | False | None |
| LOC19 | local | PASS | 177 | 1 | False | None |
| LOC20 | local | PASS | 220 | 1 | False | None |
| LOC21 | local | PASS | 203 | 1 | False | None |
| LOC22 | local | PASS | 195 | 1 | False | None |
| LOC23 | local | PASS | 177 | 1 | False | None |
| LOC24 | local | PASS | 230 | 1 | False | None |
| LOC25 | local | PASS | 192 | 1 | False | None |
| LOC26 | local | PASS | 166 | 0 | False | None |
| LOC27 | local | PASS | 200 | 1 | False | None |
| LOC28 | local | PASS | 207 | 1 | False | None |
| LOC29 | local | PASS | 214 | 1 | False | None |
| LOC30 | local | PASS | 196 | 1 | False | None |
| LOC31 | local | PASS | 235 | 1 | False | None |
| LOC32 | local | PASS | 194 | 1 | False | None |
| LOC33 | local | PASS | 246 | 1 | False | None |
| LOC34 | local | PASS | 232 | 1 | False | None |
| LOC35 | local | PASS | 232 | 1 | False | None |
| LOC36 | local | PASS | 189 | 0 | False | None |
| LOC37 | local | PASS | 225 | 1 | False | None |
| LOC38 | local | PASS | 175 | 1 | False | None |
| LOC39 | local | PASS | 176 | 1 | False | None |
| LOC40 | local | PASS | 202 | 1 | False | None |
| LOC41 | local | PASS | 190 | 1 | False | None |
| LOC42 | local | PASS | 182 | 1 | False | None |
| LOC43 | local | PASS | 236 | 1 | False | None |
| LOC44 | local | PASS | 207 | 1 | False | None |
| LOC45 | local | PASS | 178 | 1 | False | None |
| LOC46 | local | PASS | 191 | 0 | False | None |
| LOC47 | local | PASS | 192 | 1 | False | None |
| LOC48 | local | PASS | 211 | 1 | False | None |
| LOC49 | local | PASS | 205 | 1 | False | None |
| LOC50 | local | PASS | 199 | 1 | False | None |
| FC01 | forecast | PASS | 230 | 0 | True | True |
| FC02 | forecast | PASS | 186 | 0 | True | True |
| FC03 | forecast | PASS | 273 | 0 | True | True |
| FC04 | forecast | PASS | 2228 | 0 | True | False |
| FC05 | forecast | PASS | 198 | 0 | True | True |
| FC06 | forecast | PASS | 177 | 0 | True | True |
| FC07 | forecast | PASS | 196 | 0 | True | True |
| FC08 | forecast | PASS | 176 | 0 | True | True |
| FC09 | forecast | PASS | 162 | 0 | True | True |
| FC10 | forecast | PASS | 3192 | 0 | True | False |
| FC11 | forecast | PASS | 265 | 0 | True | True |
| FC12 | forecast | PASS | 177 | 0 | True | True |
| FC13 | forecast | PASS | 184 | 0 | True | True |
| FC14 | forecast | PASS | 155 | 0 | True | True |
| FC15 | forecast | PASS | 208 | 0 | True | True |
| FC16 | forecast | PASS | 195 | 0 | True | True |
| FC17 | forecast | PASS | 177 | 0 | True | True |
| FC18 | forecast | PASS | 211 | 0 | True | True |
| FC19 | forecast | PASS | 240 | 0 | True | True |
| FC20 | forecast | PASS | 168 | 0 | True | True |
| MEM01 | memory | PASS | 206 | 1 | False | None |
| MEM02 | memory | PASS | 34818 | 1 | False | None |
| MEM03 | memory | PASS | 2602 | 1 | False | None |
| MEM04 | memory | FAIL | 1771 | 0 | False | None |
| MEM05 | memory | FAIL | 2055 | 0 | False | None |
| MEM06 | memory | FAIL | 3032 | 0 | False | None |
| MEM07 | memory | PASS | 742 | 0 | False | None |
| MEM08 | memory | PASS | 811 | 0 | False | None |
| MEM09 | memory | PASS | 778 | 0 | False | None |
| MEM10 | memory | PASS | 766 | 0 | False | None |
| MEM11 | memory | PASS | 1113 | 1 | False | None |
| MEM12 | memory | PASS | 1060 | 1 | False | None |
| MEM13 | memory | PASS | 979 | 1 | False | None |
| MEM14 | memory | PASS | 1246 | 1 | True | None |
| MEM15 | memory | PASS | 1087 | 1 | True | None |
| MEM16 | memory | PASS | 1332 | 1 | True | None |
| MEM17 | memory | PASS | 1653 | 1 | True | None |
| MEM18 | memory | PASS | 1743 | 1 | True | None |
| MEM19 | memory | FAIL | 912 | 0 | False | None |
| MEM20 | memory | FAIL | 3134 | 0 | False | None |
| CACH01 | cache | PASS | 212 | 1 | False | True |
| CACH02 | cache | PASS | 156 | 1 | False | True |
| CACH03 | cache | PASS | 232 | 1 | False | True |
| CACH04 | cache | PASS | 156 | 1 | False | True |
| CACH05 | cache | PASS | 188 | 1 | False | True |
| CACH06 | cache | PASS | 211 | 1 | False | True |
| CACH07 | cache | PASS | 186 | 1 | False | True |
| CACH08 | cache | PASS | 171 | 1 | False | True |
| CACH09 | cache | PASS | 290 | 1 | False | True |
| CACH10 | cache | PASS | 205 | 1 | False | True |
| CACH11 | cache | PASS | 213 | 1 | False | True |
| CACH12 | cache | PASS | 185 | 1 | False | True |
| CACH13 | cache | PASS | 1907 | 1 | False | False |
| CACH14 | cache | PASS | 207 | 1 | False | True |
| CACH15 | cache | PASS | 1894 | 1 | False | False |
| CACH16 | cache | PASS | 177 | 1 | False | True |
| CACH17 | cache | PASS | 1379 | 1 | False | False |
| CACH18 | cache | PASS | 185 | 1 | False | True |
| CACH19 | cache | PASS | 1282 | 1 | False | False |
| CACH20 | cache | PASS | 173 | 1 | False | True |
| CONC01 | concurrent | PASS | 13864 | 1 | False | None |
| CONC02 | concurrent | PASS | 3993 | 1 | False | None |
| CONC03 | concurrent | PASS | 15613 | 1 | False | None |
| CONC04 | concurrent | PASS | 12656 | 0 | True | None |
| CONC05 | concurrent | PASS | 13715 | 1 | False | None |
| CONC06 | concurrent | PASS | 14999 | 1 | False | None |
| CONC07 | concurrent | PASS | 15605 | 1 | False | None |
| CONC08 | concurrent | PASS | 15563 | 1 | False | None |
| CONC09 | concurrent | PASS | 15583 | 1 | False | None |
| CONC10 | concurrent | PASS | 14680 | 1 | False | None |
| SES01 | session | PASS | 218 | 0 | False | None |
| SES02 | session | PASS | 74 | 0 | False | None |
| SES03 | session | PASS | 55 | 0 | False | None |
| SES04 | session | PASS | 59 | 0 | False | None |
| SES05 | session | PASS | 63 | 0 | False | None |
| SES06 | session | PASS | 61 | 0 | False | None |
| SES07 | session | PASS | 67 | 0 | False | None |
| SES08 | session | PASS | 50 | 0 | False | None |
| CH01 | charts | PASS | 186 | 1 | False | None |
| CH02 | charts | PASS | 172 | 1 | False | None |
| CH03 | charts | FAIL | 151 | 0 | False | None |
| CH04 | charts | PASS | 214 | 1 | False | None |
| CH05 | charts | PASS | 174 | 1 | False | None |
| CH06 | charts | PASS | 205 | 1 | False | None |
| CH07 | charts | PASS | 196 | 0 | True | None |
| CH08 | charts | PASS | 218 | 1 | False | None |
| ERR01 | error | PASS | 10720 | 0 | False | None |
| ERR02 | error | PASS | 807 | 0 | False | None |
| ERR03 | error | PASS | 10590 | 0 | False | None |
| ERR04 | error | FAIL | 40019 | 0 | False | None |
| ERR05 | error | PASS | 10353 | 0 | False | None |
| ERR06 | error | PASS | 781 | 0 | False | None |
| ERR07 | error | PASS | 2720 | 0 | False | None |
| ERR08 | error | FAIL | 2347 | 0 | False | None |
| REG01 | registry | PASS | 1 | 0 | False | None |
| REG02 | registry | PASS | 1 | 0 | False | None |
| REG03 | registry | PASS | 1 | 0 | False | None |
| REG04 | registry | PASS | 1 | 0 | False | None |
| REG05 | registry | PASS | 1 | 0 | False | None |
| REG06 | registry | PASS | 1 | 0 | False | None |
| NET01 | internet | PASS | 9987 | 1 | False | None |
| NET02 | internet | PASS | 9210 | 1 | False | None |
| NET03 | internet | PASS | 6338 | 1 | False | None |
| NET04 | internet | PASS | 1507 | 1 | False | None |
| NET05 | internet | PASS | 2055 | 1 | False | None |
| NET06 | internet | FAIL | 40032 | 0 | False | None |
| NET07 | internet | FAIL | 40028 | 0 | False | None |
| NET08 | internet | FAIL | 0 | 0 | False | None |
| NET09 | internet | FAIL | 0 | 0 | False | None |
| NET10 | internet | FAIL | 0 | 0 | False | None |
| NET11 | internet | FAIL | 0 | 0 | False | None |
| NET12 | internet | FAIL | 0 | 0 | False | None |
| NET13 | internet | FAIL | 0 | 0 | False | None |
| NET14 | internet | FAIL | 0 | 0 | False | None |
| NET15 | internet | FAIL | 0 | 0 | False | None |
| NET16 | internet | FAIL | 0 | 0 | False | None |
| NET17 | internet | FAIL | 0 | 0 | False | None |
| NET18 | internet | FAIL | 0 | 0 | False | None |
| NET19 | internet | FAIL | 0 | 0 | False | None |
| NET20 | internet | FAIL | 0 | 0 | False | None |
| NET21 | internet | FAIL | 0 | 0 | False | None |
| NET22 | internet | FAIL | 0 | 0 | False | None |
| NET23 | internet | FAIL | 0 | 0 | False | None |
| NET24 | internet | FAIL | 0 | 0 | False | None |
| NET25 | internet | FAIL | 0 | 0 | False | None |
| NET26 | internet | FAIL | 0 | 0 | False | None |
| NET27 | internet | FAIL | 0 | 0 | False | None |
| NET28 | internet | FAIL | 0 | 0 | False | None |
| NET29 | internet | FAIL | 0 | 0 | False | None |
| NET30 | internet | FAIL | 0 | 0 | False | None |

---

## Certification gates

| Gate | Threshold | Observed | Status |
|------|-----------|----------|:------:|
| Pass rate | ≥ 85% | 81.7% | FAIL |
| Forecast success | ≥ 70% | 100.0% | PASS |
| Continuity | ≥ 80% | 75.0% | FAIL |
| P95 latency | ≤ 60s | 15.6s | PASS |
| Score | ≥ 7.5/10 | 7.14 | FAIL |
| Concurrent | ≥ 90% | 100.0% | PASS |

**Final recommendation: `Not Ready`**

_Artifacts: `production_certification_20260730T121948Z.json`, `PRODUCTION_READINESS_REPORT_V2_20260730T121948Z.md`_
