import requests
base = 'http://127.0.0.1:8001'
sid = 'forecast_test'
for q in ['find dataset about gdp','predict next 5 years GDP']:
    resp = requests.get(f'{base}/ask', params={'question': q, 'session_id': sid})
    data = resp.json()
    print('QUESTION:', q)
    print('STATUS', resp.status_code)
    print('ANSWER', data.get('answer'))
    print('FORECAST_ERROR', data.get('forecast_error'))
    print('FORECAST_LEN', len(data.get('forecast', [])))
    print('FORECAST_CHART_PRESENT', data.get('forecast_chart') is not None)
    print('KEYS', list(data.keys()))
    print('---')
