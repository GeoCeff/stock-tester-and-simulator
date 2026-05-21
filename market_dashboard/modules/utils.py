import pandas as pd

def compute_returns(close):
    if close is None or len(close) == 0:
        return pd.Series(dtype=float)

    returns = close.pct_change()
    return returns.replace([float("inf"), float("-inf")], pd.NA)


def correlation_matrix(returns):
    if returns is None or len(returns) == 0:
        return pd.DataFrame()

    return returns.dropna(how="all").corr()
