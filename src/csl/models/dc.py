import pandas as pd
import penaltyblog as pb
from penaltyblog.models import dixon_coles_weights
import os
from datetime import datetime

from csl.date_utils import parse_date_only_series


def fit_dixon_coles_model_from_csv(input_csv_path, xi=0.001):
    """
    Load league data, apply the standard 18-month filter and fit the project
    Dixon-Coles model. Returns the fitted penaltyblog model instance.
    """
    df = pd.read_csv(input_csv_path)
    raw_dates = df["Date"].copy()

    # Accept both legacy slash dates and the canonical YYYY-MM-DD format.
    df["Date"] = parse_date_only_series(df["Date"])
    bad_dates = df["Date"].isna()
    if bad_dates.any():
        bad_values = raw_dates.loc[bad_dates].astype(str).head(10).tolist()
        raise ValueError(f"Found unparseable Date values in {input_csv_path}: {bad_values}")

    # Drop rows where 'Home' or 'Away' teams are missing
    df = df.dropna(subset=["Home", "Away"])

    # Ensure team names are strings
    df["Home"] = df["Home"].astype(str)
    df["Away"] = df["Away"].astype(str)

    # The model is trained on expected-goal targets, so rows without a full
    # HExpG+/AExpG+ pair cannot be used yet (for example, when xG is delayed).
    df["HExpG+"] = pd.to_numeric(df["HExpG+"], errors="coerce")
    df["AExpG+"] = pd.to_numeric(df["AExpG+"], errors="coerce")

    # Filter to most recent 1.5 years of data only
    # Uses the latest match date in the dataset as the reference point
    cutoff_date = df["Date"].max() - pd.DateOffset(months=18)
    df = df[df["Date"] >= cutoff_date]

    df = df.dropna(subset=["HExpG+", "AExpG+"]).copy()
    if df.empty:
        raise ValueError("No training rows remain after dropping missing HExpG+/AExpG+ values")

    # Generate time-decay weights so recent matches matter more
    weights = dixon_coles_weights(df["Date"], xi=xi)

    clf = pb.models.ZeroInflatedPoissonGoalsModel(
        df["HExpG+"],
        df["AExpG+"],
        df["Home"],
        df["Away"],
        weights,
    )
    clf.fit()
    clf.get_params()
    return clf


def run_dixon_coles_model(input_csv_path, output_csv_path, xi=0.001):
    """
    Automates the Dixon-Coles model process: reading data, extracting teams, applying weights, fitting the model,
    extracting parameters, and saving results to a CSV file.

    Parameters:
        input_csv_path (str): Path to the input CSV file.
        output_csv_path (str): Path to save the output CSV file.
        xi (float): Decay factor for time weighting. Higher values down-weight older matches more
                    aggressively. Default is 0.001. Typical range: 0.0001 (slow decay) to 0.01 (fast decay).
    """
    # Step 1: Fit the shared Dixon-Coles model used across exports
    clf = fit_dixon_coles_model_from_csv(input_csv_path, xi=xi)

    # Step 2: Extract Parameters
    # Use clf.teams to guarantee team order matches the internal parameter array
    teams = clf.teams
    params = clf._params
    attack = params[:len(teams)]        # Attack values
    defense = params[len(teams):len(teams)*2]  # Defense values

    # Step 3: Create DataFrame for Team Statistics
    team_stats = pd.DataFrame({
        "Team": teams,
        "Attack": attack,
        "Defense": defense
    })
    team_stats["Date"] = datetime.now().strftime("%Y-%m-%d")

    # Step 4: Simulate Matches Between All Teams
    simulation_results = []
    for home_team in teams:
        for away_team in teams:
            if home_team != away_team:
                probs = clf.predict(home_team, away_team)
                results = {
                    "Home Team": home_team,
                    "Away Team": away_team,
                    "Home Win Probability": probs.asian_handicap("home", 0),
                    "Draw Probability": 1 - probs.asian_handicap("home", 0) - probs.asian_handicap("away", 0),
                    "Away Win Probability": probs.asian_handicap("away", 0),
                    "Home -1 Handicap": probs.asian_handicap("home", -1),
                    "Home -2 Handicap": probs.asian_handicap("home", -2),
                    "Away -1 Handicap": probs.asian_handicap("away", -1),
                    "Away -2 Handicap": probs.asian_handicap("away", -2),
                }
                simulation_results.append(results)

    match_simulations_df = pd.DataFrame(simulation_results)
    match_simulations_df["Date"] = datetime.now().strftime("%Y-%m-%d")

    # Reorder columns
    match_simulations_df = match_simulations_df[["Date", "Home Team", "Away Team", "Home Win Probability",
                                                 "Draw Probability", "Away Win Probability", "Home -1 Handicap",
                                                 "Home -2 Handicap", "Away -1 Handicap", "Away -2 Handicap"]]

    # Step 5: Save DataFrames to CSV
    team_stats.to_csv(output_csv_path, index=False)
    match_simulations_df.to_csv(output_csv_path.replace(".csv", "_match_simulations.csv"), index=False)

    print(f"Team stats and match simulation results successfully saved to: {output_csv_path}")
