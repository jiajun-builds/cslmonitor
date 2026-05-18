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

results = []
for xi in np.arange(0.000, 0.005, 0.0005):
    predictions = []
    observed = []

    for date in tqdm(run_dates, desc='Processing dates'):
        lookback = pd.Timestamp(date) - pd.DateOffset(years=1)
        train = df[(df['Date'] < date) & (df['Date'] >= lookback)]
        test = df[df['Date'] == date]

        if len(train) == 0:
            continue

        weights = pb.models.dixon_coles_weights(train["Date"], xi)
        clf = pb.models.ZeroInflatedPoissonGoalsModel(
            train['HExpG+'],
            train['AExpG+'],
            train['Home'],
            train['Away'],
            weights,
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

    result = {
        "decay": xi,
        "rps": pb.metrics.rps_average(predictions, observed),
        "total_predictions": len(predictions),
    }
    results.append(result)

x = [x["decay"] for x in results]
y = [x["rps"] for x in results]
plt.plot(x, y)
plt.xlabel("Decay")
plt.ylabel("RPS")
plt.title("Zero Inflated Poisson Model Test with Decay")
plt.show()