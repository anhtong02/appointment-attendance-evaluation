"""
Baseline logistic regression for appointment no-show prediction.

Fill in every TODO. Run it after each one and see what breaks.

Run:  python baseline_skeleton.py
"""

import duckdb
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

DB = "noshow.duckdb"
SPLIT = "split_patient"


# TODO 1: list the numeric and boolean features.
# These need no encoding. From the list you settled on:
#   age, prior_noshow_capped, has_history, sms_received,
#   scholarship, hypertension, diabetes, alcoholism
NUMERIC = ['age', 
           'prior_noshow_capped', 
           'has_history', 
           'sms_received',
           'scholarship', 
           'hypertension', 
           'diabetes', 
           'alcoholism']

# TODO 2: list the categorical features, the ones needing one-hot.
#   lead_time_bucket, gender, neighborhood_grp, handicap_cat
CATEGORICAL = ['lead_time_bucket', 
               'gender', 
               'neighborhood_grp', 
               'handicap_cat']

TARGET = "no_show"


# ---------------------------------------------------------------- load

def load(split_col):
    """Pull the feature columns out of DuckDB and split into train/test."""
    con = duckdb.connect(DB, read_only=True)

    # TODO 3: build the column list for the SELECT.
    # You need every feature, the target, and the split column.
    # Hint: ", ".join(...) turns a list of names into "a, b, c"
    cols = ", ".join(NUMERIC + CATEGORICAL +[TARGET, split_col])

    df = con.sql(f"SELECT {cols} FROM feat_appointments").df()
    con.close()

    # TODO 4: split df into two frames using split_col.
    # Then drop split_col from both, since it isn't a feature.
    # Hint: df[df[split_col] == "train"]  filters rows
    #       .drop(columns=[...])          removes a column
    train = df[df[split_col] == 'train'].drop(columns=split_col)
    test  = df[df[split_col] == 'test'].drop(columns=split_col)

    return train, test


# ---------------------------------------------------------------- encode

def encode(train, test):
    """Separate the target, one-hot the categoricals, align the columns."""

    # TODO 5: pop the target off each frame and cast to int.
    # .pop() removes the column and returns it in one step.
    # Booleans need .astype(int) because sklearn wants 0/1.
    y_train = ...
    y_test = ...

    # TODO 6: one-hot encode the categorical columns.
    # Hint: pd.get_dummies(frame, columns=CATEGORICAL, drop_first=True)
    #
    # Why drop_first: with 5 lead time buckets you only need 4 columns.
    # The 5th is implied by the other 4 all being zero. Keeping all 5
    # makes them perfectly correlated, which makes the coefficients
    # unstable.
    X_train = ...
    X_test = ...

    # TODO 7: force X_test to have exactly X_train's columns.
    #
    # Why this matters: get_dummies builds columns from whatever categories
    # are present. If a neighborhood appears in train but not test, the two
    # frames get different shapes and the model either crashes or silently
    # lines up the wrong columns.
    #
    # Hint: .reindex(columns=..., fill_value=0)
    X_test = ...

    return X_train.astype(float), y_train, X_test.astype(float), y_test


# ---------------------------------------------------------------- evaluate

def precision_at_k(y_true, scores, k_frac):
    """Sort by predicted risk, take the top k_frac of rows, return what
    fraction of those actually no-showed.

    This is the metric that matches the product: the front desk can only
    call so many people, so what matters is whether the top of the list
    is worth calling."""

    # TODO 8: how many rows is k_frac of the total?
    n = ...

    # TODO 9: build a frame of actual outcomes and scores, take the n
    # highest-scoring rows, and return the mean of the outcomes.
    #
    # Hint: pd.DataFrame({"y": y_true.values, "s": scores})
    #       .nlargest(n, "s")
    #       ["y"].mean()
    top = ...

    return ..., n


def report(y_test, scores, base_rate):
    print(f"\n  AUC: {roc_auc_score(y_test, scores):.4f}")
    print(f"  Base rate (test): {base_rate:.4f}\n")
    print(f"  {'top k':>8}  {'n':>7}  {'precision':>10}  {'lift':>6}")
    print(f"  {'-'*8}  {'-'*7}  {'-'*10}  {'-'*6}")

    for k in (0.05, 0.10, 0.20, 0.50):
        p, n = precision_at_k(y_test, scores, k)

        # TODO 10: lift is precision divided by the base rate.
        # A lift of 1.0 means the model is no better than random ranking.
        lift = ...

        print(f"  {k:>7.0%}  {n:>7,}  {p:>10.4f}  {lift:>5.2f}x")


# ---------------------------------------------------------------- run

def main():
    train, test = load(SPLIT)
    print(f"Split: {SPLIT}")
    print(f"Train rows: {len(train):,}   Test rows: {len(test):,}")

    X_train, y_train, X_test, y_test = encode(train, test)
    print(f"Features after encoding: {X_train.shape[1]}")

    # Scaling doesn't change predictions. It makes the coefficients
    # comparable: age runs 0-115 and the booleans run 0-1, so without it
    # the age coefficient looks tiny purely because of its units.
    #
    # TODO 11: fit a StandardScaler on X_train.
    # Fit on train only, never on test. Fitting on test would leak the
    # test set's mean and standard deviation into your pipeline.
    scaler = ...

    # TODO 12: create and fit the model on the scaled training data.
    # LogisticRegression(max_iter=1000) — the default 100 won't converge here.
    model = ...

    # TODO 13: get predicted probabilities for the test set.
    # predict_proba returns two columns, one per class. You want the
    # probability of class 1 (no-show), so take column index 1.
    #
    # Do NOT use .predict() — that gives hard 0/1 labels at a 0.5 threshold,
    # and you need continuous scores to rank by.
    scores = ...

    report(y_test, scores, y_test.mean())

    # TODO 14: print the coefficients sorted by absolute size.
    #
    # model.coef_[0] is the array of coefficients.
    # X_train.columns lines up with it.
    #
    # Hint: pd.Series(values, index=names).sort_values(key=abs, ascending=False)
    #
    # Reading them: positive means more likely to no-show, negative means
    # less likely. Units are log-odds, so don't read them as percentages.
    print("\n  Coefficients (log-odds, scaled):")
    coefs = ...
    for name, val in coefs.items():
        print(f"    {val:>+8.4f}  {name}")


if __name__ == "__main__":
    main()