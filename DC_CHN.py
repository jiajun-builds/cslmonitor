import os

from csl.models.dc import run_dixon_coles_model
from csl.paths import data_output_dir, data_raw_dir

input_csv_path = os.path.join(data_raw_dir(), "CHN_Super League.csv")
output_csv_path = os.path.join(data_output_dir(), "CHN_team_stats.csv")

run_dixon_coles_model(input_csv_path, output_csv_path, xi=0.001)
