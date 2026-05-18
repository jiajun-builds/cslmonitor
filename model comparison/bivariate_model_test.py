import numpy as np
import pandas as pd
import penaltyblog as pb
import matplotlib.pyplot as plt
from tqdm import tqdm

df = pd.read_csv('/Users/jordan/Projects/Chinese Super League Prediction/data/raw_data/CHN_Super League.csv')
df['Date'] = pd.to_datetime(df['Date'])
df = df.sort_values('Date').set_index('Date', drop=False)

# Map result to numeric
res_map = {'H': 0, 'D': 1, 'A': 2}
df['res_numeric'] = df['Res'].map(res_map)

start_date = df.query('Season == 2025')['Date'].min()
run_dates = df['Date'][df['Date'] >= start_date].unique()
print(f'Start date: {start_date.date()}, Run dates: {len(run_dates)}')

predictions = []
observed = []

for date in tqdm(run_dates, desc='Processing dates'):
    lookback = pd.Timestamp(date) - pd.DateOffset(years=1)
    train = df[(df['Date'] < date) & (df['Date'] >= lookback)]
    test = df[df['Date'] == date]

    if len(train) == 0:
        continue

    clf = pb.models.BivariatePoissonGoalModel(
        train['HExpG+'],
        train['AExpG+'],
        train['Home'],
        train['Away'],
    )

    try:
        clf.fit()
        if len(test) > 0:
            homes = test['Home'].values
            aways = test['Away'].values
            outcomes = test['res_numeric'].values
            for i in range(len(test)):
                try:
                    prediction = clf.predict(homes[i], aways[i])
                    predictions.append(prediction.home_draw_away)
                    observed.append(outcomes[i])
                except Exception as e:
                    continue
    except Exception as e:
        continue

rps = pb.metrics.rps_average(predictions, observed)
print(f'\nTotal predictions made: {len(predictions)}')
print(f'DixonColes RPS (HExpG+ / AExpG+): {rps}')