from csl.models.dc import run_dixon_coles_model

input_csv_path = "/Users/jordan/Projects/Chinese Super League Prediction/data/raw_data/CHN_Super League.csv"
output_csv_path = "/Users/jordan/Projects/Chinese Super League Prediction/data/output_data/CHN_team_stats.csv"

run_dixon_coles_model(input_csv_path, output_csv_path, xi=0.001)